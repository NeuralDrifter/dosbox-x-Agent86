// Copyright (c) 2026 Michael P. Burgus - https://github.com/NeuralDrifter
#pragma once

#include "callback.h"
#include "dos_inc.h"

#if defined(_WIN32) || defined(WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
typedef SOCKET bridge_socket_t;
static const bridge_socket_t InvalidBridgeSocket = INVALID_SOCKET;
static const int BridgeSocketError = SOCKET_ERROR;
#else
#include <arpa/inet.h>
#include <cerrno>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
typedef int bridge_socket_t;
static const bridge_socket_t InvalidBridgeSocket = -1;
static const int BridgeSocketError = -1;
#endif

class device_BRIDGE : public DOS_Device {
public:
	explicit device_BRIDGE(const uint16_t port)
	        : listen_port(port),
	          listen_socket(InvalidBridgeSocket),
	          connection_socket(InvalidBridgeSocket)
#if defined(_WIN32) || defined(WIN32)
	          , winsock_started(false)
#endif
	{
		SetName("BRIDGE");
	}
	device_BRIDGE(const device_BRIDGE &) = delete;
	device_BRIDGE &operator=(const device_BRIDGE &) = delete;

	~device_BRIDGE() override
	{
		Deactivate();
#if defined(_WIN32) || defined(WIN32)
		if (winsock_started)
			WSACleanup();
#endif
	}

	bool EnsureListening()
	{
		if (IsValidSocket(listen_socket))
			return true;
		if (listen_port == 0 || !StartSocketRuntime())
			return false;

		listen_socket = ::socket(AF_INET, SOCK_STREAM, 0);
		if (!IsValidSocket(listen_socket))
			return false;

		if (!ConfigureListener() || !BindListener() ||
		    ::listen(listen_socket, 1) == BridgeSocketError ||
		    !SetNonBlocking(listen_socket)) {
			CloseListener();
			return false;
		}
		return true;
	}

	void Deactivate()
	{
		Disconnect();
		CloseListener();
	}

	bool Read(uint8_t *data, uint16_t *size) override
	{
		if (!EnsureListening()) {
			*size = 0;
			return false;
		}

		const uint16_t requested = *size;
		uint16_t received = 0;
		while (received < requested) {
			if (!EnsureListening()) {
				*size = received;
				return false;
			}
			AcceptConnection();
			if (IsValidSocket(connection_socket)) {
				const int count = ::recv(connection_socket,
				                         reinterpret_cast<char *>(data) + received,
				                         requested - received,
				                         0);
				if (count > 0) {
					received += static_cast<uint16_t>(count);
					break;
				}
				if (count == 0 || !WouldBlock())
					Disconnect();
			}
			if (received == 0)
				CALLBACK_Idle();
		}
		*size = received;
		return true;
	}

	bool Write(const uint8_t *data, uint16_t *size) override
	{
		if (!EnsureListening()) {
			*size = 0;
			return false;
		}

		AcceptConnection();
		if (!IsValidSocket(connection_socket)) {
			*size = 0;
			return true;
		}

		uint16_t sent = 0;
		uint16_t wait_count = 0;
		while (sent < *size) {
			const int count = SendBytes(data + sent, *size - sent);
			if (count > 0) {
				sent += static_cast<uint16_t>(count);
				wait_count = 0;
				continue;
			}
			if (count == 0 || !WouldBlock() || ++wait_count > MaxWriteWaits) {
				Disconnect();
				*size = sent;
				return false;
			}
			CALLBACK_Idle();
		}
		return true;
	}

	bool Seek(uint32_t *position, uint32_t) override
	{
		*position = 0;
		return true;
	}
	bool Close() override { return true; }
	uint16_t GetInformation() override { return 0x80D3; }
	bool ReadFromControlChannel(PhysPt, uint16_t, uint16_t *) override
	{
		return false;
	}
	bool WriteToControlChannel(PhysPt, uint16_t, uint16_t *) override
	{
		return false;
	}

private:
	static constexpr uint16_t MaxWriteWaits = 1024;

	void Disconnect()
	{
		CloseSocket(connection_socket);
	}

	static bool IsValidSocket(const bridge_socket_t socket)
	{
		return socket != InvalidBridgeSocket;
	}

	static void CloseSocket(bridge_socket_t &socket)
	{
		if (!IsValidSocket(socket))
			return;
#if defined(_WIN32) || defined(WIN32)
		closesocket(socket);
#else
		close(socket);
#endif
		socket = InvalidBridgeSocket;
	}

	bool StartSocketRuntime()
	{
#if defined(_WIN32) || defined(WIN32)
		if (winsock_started)
			return true;
		WSADATA data = {};
		winsock_started = WSAStartup(MAKEWORD(2, 2), &data) == 0;
		return winsock_started;
#else
		return true;
#endif
	}

	bool ConfigureListener()
	{
		int enabled = 1;
#if defined(_WIN32) || defined(WIN32)
		return setsockopt(listen_socket,
		                  SOL_SOCKET,
		                  SO_EXCLUSIVEADDRUSE,
		                  reinterpret_cast<const char *>(&enabled),
		                  sizeof(enabled)) != BridgeSocketError;
#else
		return setsockopt(listen_socket,
		                  SOL_SOCKET,
		                  SO_REUSEADDR,
		                  &enabled,
		                  sizeof(enabled)) != BridgeSocketError;
#endif
	}

	bool BindListener()
	{
		sockaddr_in address = {};
		address.sin_family = AF_INET;
		address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
		address.sin_port = htons(listen_port);
		return bind(listen_socket,
		            reinterpret_cast<sockaddr *>(&address),
		            sizeof(address)) != BridgeSocketError;
	}

	static bool SetNonBlocking(const bridge_socket_t socket)
	{
#if defined(_WIN32) || defined(WIN32)
		u_long enabled = 1;
		return ioctlsocket(socket, FIONBIO, &enabled) != BridgeSocketError;
#else
		const int flags = fcntl(socket, F_GETFL, 0);
		return flags >= 0 &&
		       fcntl(socket, F_SETFL, flags | O_NONBLOCK) != BridgeSocketError;
#endif
	}

	static bool WouldBlock()
	{
#if defined(_WIN32) || defined(WIN32)
		return WSAGetLastError() == WSAEWOULDBLOCK;
#else
		return errno == EWOULDBLOCK || errno == EAGAIN;
#endif
	}

	void AcceptConnection()
	{
		if (IsValidSocket(connection_socket) ||
		    !IsValidSocket(listen_socket))
			return;

		bridge_socket_t candidate = ::accept(listen_socket, nullptr, nullptr);
		if (!IsValidSocket(candidate)) {
			if (!WouldBlock())
				CloseListener();
			return;
		}
		if (!SetNonBlocking(candidate)) {
			CloseSocket(candidate);
			return;
		}
		connection_socket = candidate;
	}

	int SendBytes(const uint8_t *data, const uint16_t size)
	{
#if defined(MSG_NOSIGNAL)
		return ::send(connection_socket,
		              reinterpret_cast<const char *>(data),
		              size,
		              MSG_NOSIGNAL);
#else
		return ::send(connection_socket,
		              reinterpret_cast<const char *>(data),
		              size,
		              0);
#endif
	}

	void CloseListener()
	{
		CloseSocket(listen_socket);
	}

	const uint16_t listen_port;
	bridge_socket_t listen_socket;
	bridge_socket_t connection_socket;
#if defined(_WIN32) || defined(WIN32)
	bool winsock_started;
#endif
};
