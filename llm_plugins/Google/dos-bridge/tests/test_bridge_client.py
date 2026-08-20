# Copyright (c) 2026 Michael P. Burgus - https://github.com/NeuralDrifter

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import socket
import sys
import threading
import unittest
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from bridge_client import (  # noqa: E402
    BridgeError,
    DosBridgeClient,
    _encode_command,
    _encode_file_content,
    _validate_write_path,
)


class FakeBridgeServer:
    def __init__(
        self,
        oversized_output: bool = False,
        confirm_write: bool = True,
        confirm_preflight: bool = True,
    ):
        self.oversized_output = oversized_output
        self.confirm_write = confirm_write
        self.confirm_preflight = confirm_preflight
        self.connection_count = 0
        self.requests = []
        self._server_error = None
        self._stop = threading.Event()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(2)
        self._listener.settimeout(0.1)
        self.port = self._listener.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.close()

    def close(self):
        self._stop.set()
        self._listener.close()
        self._thread.join(timeout=1)
        if self._thread.is_alive():
            raise AssertionError("fake bridge server did not stop")
        if self._server_error:
            raise AssertionError("fake bridge server failed") from self._server_error

    def _serve(self):
        while not self._stop.is_set():
            try:
                connection, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError as error:
                if not self._stop.is_set():
                    self._server_error = error
                return
            self.connection_count += 1
            connection.settimeout(0.1)
            try:
                self._serve_connection(connection)
            except OSError as error:
                if not self._stop.is_set():
                    self._server_error = error
                return
            finally:
                connection.close()

    def _serve_connection(self, connection):
        request = bytearray()
        while not self._stop.is_set():
            try:
                chunk = connection.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                return
            request.extend(chunk)
            end_match = re.search(
                rb"echo (__DOSBRIDGE_END_[A-F0-9]+__)\r", bytes(request)
            )
            if not end_match:
                continue
            payload = bytes(request[: end_match.end()])
            del request[: end_match.end()]
            self.requests.append(payload)
            response = bytearray(b"DOS OUTPUT\r\n")
            if self.oversized_output:
                response.extend(b"X" * 256)
            preflight_match = re.search(
                rb"echo (__DOSBRIDGE_PREFLIGHT_OK_[A-F0-9]+__)\r", payload
            )
            if preflight_match and self.confirm_preflight:
                response.extend(preflight_match.group(1) + b"\r\n")
            success_match = re.search(
                rb"echo (__DOSBRIDGE_WRITE_OK_[A-F0-9]+__)\r", payload
            )
            if success_match and self.confirm_write:
                response.extend(success_match.group(1) + b"\r\n")
            response.extend(end_match.group(1) + b"\r\nA:\\>")
            connection.sendall(response)


class DosBridgeClientTests(unittest.TestCase):
    def test_reuses_one_connection_for_sequential_commands(self):
        with FakeBridgeServer() as server, DosBridgeClient(port=server.port) as client:
            self.assertIn("DOS OUTPUT", client.run_command("ver"))
            self.assertIn("DOS OUTPUT", client.run_command("dir A:\\"))
            self.assertEqual(server.connection_count, 1)
            self.assertEqual(len(server.requests), 2)

    def test_serializes_concurrent_commands(self):
        with FakeBridgeServer() as server, DosBridgeClient(port=server.port) as client:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(client.run_command, ("ver", "set")))

            self.assertEqual(len(results), 2)
            self.assertEqual(server.connection_count, 1)
            self.assertEqual(len(server.requests), 2)

    def test_rejects_output_over_configured_limit(self):
        with FakeBridgeServer(oversized_output=True) as server, DosBridgeClient(
            port=server.port, max_output_bytes=64
        ) as client:
            with self.assertRaisesRegex(BridgeError, "output exceeded"):
                client.run_command("ver")

    def test_write_requires_confirmed_success(self):
        with FakeBridgeServer(confirm_write=False) as server, DosBridgeClient(
            port=server.port
        ) as client:
            with self.assertRaisesRegex(BridgeError, "did not confirm"):
                client.write_file("A:\\GAME.C", "int main(void) { return 0; }")

    def test_write_accepts_confirmed_success(self):
        with FakeBridgeServer() as server, DosBridgeClient(port=server.port) as client:
            result = client.write_file("A:\\SRC\\GAME.C", "hello\n")
            self.assertIn("written successfully", result)

    def test_write_preflight_failure_never_sends_content(self):
        secret = "DEL A:" + chr(92) + "*.*"
        with FakeBridgeServer(confirm_preflight=False) as server, DosBridgeClient(
            port=server.port
        ) as client:
            with self.assertRaisesRegex(BridgeError, "cannot write"):
                client.write_file("A:" + chr(92) + "GAME.C", secret)
        sent = b"".join(server.requests)
        self.assertNotIn(secret.encode("cp437"), sent)
        self.assertNotIn(b"copy con", sent)

    def test_write_path_is_confined_to_allowed_83_drive(self):
        self.assertEqual(_validate_write_path("a:/src/game.c"), "A:\\src\\game.c")
        rejected = (
            "C:\\GAME.C",
            "A:\\..\\GAME.C",
            "A:\\LONGFILENAME.C",
            "A:\\GAME.C & DEL A:\\*.*",
        )
        for path in rejected:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    _validate_write_path(path)

    def test_write_drive_configuration_is_validated(self):
        with patch.dict(os.environ, {"DOS_BRIDGE_WRITE_DRIVES": "A,invalid"}):
            with self.assertRaisesRegex(BridgeError, "DOS_BRIDGE_WRITE_DRIVES"):
                _validate_write_path("A:\\GAME.C")

        with patch.dict(os.environ, {"DOS_BRIDGE_WRITE_DRIVES": "A,B"}):
            self.assertEqual(_validate_write_path("B:\\GAME.C"), "B:\\GAME.C")

    def test_constructor_rejects_invalid_network_limits(self):
        invalid_arguments = (
            {"port": 0},
            {"port": True},
            {"max_output_bytes": 0},
            {"max_output_bytes": True},
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                DosBridgeClient(**arguments)

    def test_configured_port_fails_closed(self):
        with patch.dict(os.environ, {"DOS_BRIDGE_PORT": "not-a-port"}):
            with self.assertRaisesRegex(BridgeError, "DOS_BRIDGE_PORT"):
                DosBridgeClient()

    def test_rejects_invalid_timeouts(self):
        with FakeBridgeServer() as server, DosBridgeClient(port=server.port) as client:
            for timeout in (0, -1, float("inf"), float("nan"), True):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    client.run_command("ver", timeout=timeout)

    def test_rejects_control_characters(self):
        for command in ("dir\nver", "dir\x1b", "dir\x7f"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                _encode_command(command)
        for content in ("hello\x00", "hello\x1a", "hello\x1b"):
            with self.subTest(content=content), self.assertRaises(ValueError):
                _encode_file_content(content)


if __name__ == "__main__":
    unittest.main()
