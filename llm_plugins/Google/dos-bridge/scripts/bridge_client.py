# Copyright (c) 2026 Michael P. Burgus - https://github.com/NeuralDrifter
"""Serialized, bounded transport for the DOSBox-X CTTY BRIDGE device."""

from __future__ import annotations

import math
import os
import re
import secrets
import socket
import threading
import time
from types import TracebackType

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8090
CONNECT_TIMEOUT_SECONDS = 3.0
COMMAND_TIMEOUT_SECONDS = 60.0
WRITE_TIMEOUT_SECONDS = 30.0
MAX_COMMAND_BYTES = 4096
MAX_FILE_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
RECEIVE_CHUNK_BYTES = 4096
MARKER_RANDOM_BYTES = 12
DOS_COMPONENT = r"[A-Za-z0-9_-]{1,8}"
DOS_FILENAME = rf"{DOS_COMPONENT}(?:\.[A-Za-z0-9_-]{{1,3}})?"
DOS_PATH_PATTERN = re.compile(
    rf"^(?P<drive>[A-Za-z]):\\(?:{DOS_COMPONENT}\\)*{DOS_FILENAME}$"
)
DOS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]$")


class BridgeError(RuntimeError):
    """Raised when a bridge request cannot complete reliably."""


class DosBridgeClient:
    """Owns one persistent TCP stream and serializes complete DOS exchanges."""

    def __init__(
        self,
        port: int | None = None,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
    ) -> None:
        self._port = _validate_port(port if port is not None else _configured_port())
        self._max_output_bytes = _validate_positive_limit(
            "max_output_bytes", max_output_bytes
        )
        self._socket: socket.socket | None = None
        self._lock = threading.Lock()

    def __enter__(self) -> DosBridgeClient:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()

    def run_command(
        self, command: str, timeout: float = COMMAND_TIMEOUT_SECONDS
    ) -> str:
        command_bytes = _encode_command(command)
        end_marker = _new_marker("END")
        payload = command_bytes + b"\r" + f"echo {end_marker}\r".encode("ascii")
        return self._exchange(payload, end_marker, timeout)

    def write_file(
        self, filename: str, content: str, timeout: float = WRITE_TIMEOUT_SECONDS
    ) -> str:
        normalized_path = _validate_write_path(filename)
        staging_path = _sibling_temp_path(normalized_path)
        target_name = normalized_path.rpartition("\\")[2]

        # Pre-flight on a throwaway sibling file, never on the target. This
        # proves the drive is mounted and the directory is writable before any
        # caller-supplied content is sent: if the destination is bad, COMMAND.COM
        # executes that content as commands instead of storing it.
        probe_success = _new_marker("PREFLIGHT_OK")
        probe_failure = _new_marker("PREFLIGHT_FAIL")
        probe_end = _new_marker("END")
        probe_payload = (
            f"copy nul {staging_path} > nul\r".encode("ascii")
            + f"if exist {staging_path} echo {probe_success}\r".encode("ascii")
            + f"if not exist {staging_path} echo {probe_failure}\r".encode("ascii")
            + f"echo {probe_end}\r".encode("ascii")
        )
        probe_output = self._exchange(probe_payload, probe_end, timeout)
        if _contains_marker(probe_output, probe_failure) or not _contains_marker(
            probe_output, probe_success
        ):
            raise BridgeError(
                f"DOS cannot write to {normalized_path}; confirm the drive is "
                f"mounted and the directory exists.\n{probe_output}"
            )

        # Stage the content, then rename over the target only after the staged
        # file is confirmed on disk. The target is never removed until a
        # replacement exists, so a failed write cannot destroy the original.
        content_bytes = _encode_file_content(content)
        success_marker = _new_marker("WRITE_OK")
        failure_marker = _new_marker("WRITE_FAIL")
        end_marker = _new_marker("END")
        payload = (
            f"copy con {staging_path}\r".encode("ascii")
            + content_bytes
            + b"\x1a\r"
            + f"if not exist {staging_path} echo {failure_marker}\r".encode("ascii")
            + f"if exist {staging_path} del {normalized_path} > nul\r".encode("ascii")
            + f"if exist {staging_path} ren {staging_path} {target_name}\r".encode(
                "ascii"
            )
            + f"if exist {normalized_path} echo {success_marker}\r".encode("ascii")
            + f"if not exist {normalized_path} echo {failure_marker}\r".encode("ascii")
            + f"echo {end_marker}\r".encode("ascii")
        )
        output = self._exchange(payload, end_marker, timeout)
        if _contains_marker(output, failure_marker) or not _contains_marker(
            output, success_marker
        ):
            raise BridgeError(f"DOS did not confirm writing {normalized_path}")
        return f"File {normalized_path} written successfully.\n{output}"

    def _exchange(self, payload: bytes, end_marker: str, timeout: float) -> str:
        request_timeout = _validate_timeout(timeout)
        with self._lock:
            try:
                connection = self._ensure_connected_unlocked()
                self._discard_pending_prompt_unlocked(connection)
                connection.sendall(payload)
                return self._receive_until_marker_unlocked(
                    connection, end_marker, request_timeout
                )
            except BridgeError:
                self._close_unlocked()
                raise
            except OSError as error:
                self._close_unlocked()
                raise BridgeError(f"DOS bridge transport failed: {error}") from error

    def _ensure_connected_unlocked(self) -> socket.socket:
        if self._socket is None:
            try:
                self._socket = socket.create_connection(
                    (DEFAULT_HOST, self._port), CONNECT_TIMEOUT_SECONDS
                )
            except OSError as error:
                raise BridgeError(
                    f"Could not connect to DOSBox-X at {DEFAULT_HOST}:{self._port}: {error}"
                ) from error
        return self._socket

    def _discard_pending_prompt_unlocked(self, connection: socket.socket) -> None:
        connection.setblocking(False)
        try:
            while True:
                chunk = connection.recv(RECEIVE_CHUNK_BYTES)
                if not chunk:
                    raise BridgeError("DOSBox-X closed the bridge connection")
        except BlockingIOError:
            pass
        finally:
            connection.setblocking(True)

    def _receive_until_marker_unlocked(
        self, connection: socket.socket, marker: str, timeout: float
    ) -> str:
        deadline = time.monotonic() + timeout
        output = bytearray()
        marker_bytes = marker.encode("ascii")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BridgeError(f"DOS command timed out after {timeout:g} seconds")
            connection.settimeout(remaining)
            try:
                chunk = connection.recv(RECEIVE_CHUNK_BYTES)
            except socket.timeout as error:
                raise BridgeError(
                    f"DOS command timed out after {timeout:g} seconds"
                ) from error
            if not chunk:
                raise BridgeError("DOSBox-X closed the bridge connection")
            output.extend(chunk)
            if len(output) > self._max_output_bytes:
                raise BridgeError(
                    f"DOS command output exceeded {self._max_output_bytes} bytes"
                )
            marker_match = _find_marker(bytes(output), marker_bytes)
            if marker_match:
                return bytes(output[: marker_match.start()]).decode(
                    "cp437", errors="replace"
                )

    def _close_unlocked(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None


def _configured_port() -> int:
    raw_port = os.getenv("DOS_BRIDGE_PORT", str(DEFAULT_PORT))
    try:
        return _validate_port(int(raw_port))
    except ValueError as error:
        raise BridgeError(
            "DOS_BRIDGE_PORT must be an integer between 1 and 65535"
        ) from error


def _validate_port(port: int) -> int:
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValueError("port must be an integer")
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return port


def _validate_positive_limit(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _validate_timeout(timeout: float) -> float:
    if isinstance(timeout, bool) or not isinstance(timeout, int | float):
        raise ValueError("timeout must be a positive finite number")
    numeric_timeout = float(timeout)
    if numeric_timeout <= 0 or not math.isfinite(numeric_timeout):
        raise ValueError("timeout must be a positive finite number")
    return numeric_timeout


def _encode_command(command: str) -> bytes:
    _require_text("command", command)
    if not command or not command.strip():
        raise ValueError("command must not be empty")
    if _contains_disallowed_control_character(command, allow_tab=True):
        raise ValueError("command must contain exactly one DOS command line")
    try:
        encoded = command.encode("cp437")
    except UnicodeEncodeError as error:
        raise ValueError("command contains characters unavailable in DOS CP437") from error
    if len(encoded) > MAX_COMMAND_BYTES:
        raise ValueError(f"command exceeds {MAX_COMMAND_BYTES} encoded bytes")
    return encoded


def _validate_write_path(filename: str) -> str:
    _require_text("filename", filename)
    normalized_path = filename.replace("/", "\\")
    match = DOS_PATH_PATTERN.fullmatch(normalized_path)
    if not match:
        raise ValueError(
            "filename must be an absolute DOS 8.3 path such as A:\\SOURCE\\GAME.C"
        )
    allowed_drives = _configured_write_drives()
    drive = match.group("drive").upper()
    if drive not in allowed_drives:
        raise ValueError(
            f"writes to drive {drive}: are disabled; allowed drives: "
            + ", ".join(sorted(allowed_drives))
        )
    return drive + normalized_path[1:]


def _sibling_temp_path(normalized_path: str) -> str:
    """Return a throwaway 8.3 path in the same directory as the target."""
    directory = normalized_path.rpartition("\\")[0]
    if not directory or directory.endswith(":"):
        directory = normalized_path[:2]
    return f"{directory}\\BR{secrets.token_hex(3).upper()}.TMP"


def _configured_write_drives() -> frozenset[str]:
    drive_names = tuple(
        drive.strip()
        for drive in os.getenv("DOS_BRIDGE_WRITE_DRIVES", "A").split(",")
        if drive.strip()
    )
    if not drive_names or any(
        not DOS_DRIVE_PATTERN.fullmatch(drive) for drive in drive_names
    ):
        raise BridgeError(
            "DOS_BRIDGE_WRITE_DRIVES must contain comma-separated drive letters"
        )
    return frozenset(drive.upper() for drive in drive_names)


def _encode_file_content(content: str) -> bytes:
    _require_text("content", content)
    if _contains_disallowed_control_character(
        content, allow_tab=True, allow_newlines=True
    ):
        raise ValueError("content contains unsupported control characters")
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    try:
        encoded = normalized.replace("\n", "\r\n").encode("cp437")
    except UnicodeEncodeError as error:
        raise ValueError("content contains characters unavailable in DOS CP437") from error
    if len(encoded) > MAX_FILE_BYTES:
        raise ValueError(f"content exceeds {MAX_FILE_BYTES} encoded bytes")
    if encoded and not encoded.endswith(b"\r\n"):
        encoded += b"\r\n"
    return encoded


def _new_marker(kind: str) -> str:
    return (
        f"__DOSBRIDGE_{kind}_"
        f"{secrets.token_hex(MARKER_RANDOM_BYTES).upper()}__"
    )


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")


def _contains_disallowed_control_character(
    value: str,
    *,
    allow_tab: bool,
    allow_newlines: bool = False,
) -> bool:
    allowed = {"\t"} if allow_tab else set()
    if allow_newlines:
        allowed.update(("\r", "\n"))
    return any(
        (ord(character) < 32 or ord(character) == 127)
        and character not in allowed
        for character in value
    )


def _find_marker(output: bytes, marker: bytes) -> re.Match[bytes] | None:
    return re.search(rb"(?:^|\r?\n)" + re.escape(marker) + rb"\r?\n", output)


def _contains_marker(output: str, marker: str) -> bool:
    return (
        re.search(
            rf"(?:^|\r?\n){re.escape(marker)}(?:\r?\n|$)", output
        )
        is not None
    )
