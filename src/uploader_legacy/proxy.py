"""Loopback relay that adds Basic auth to an upstream HTTP proxy."""

from __future__ import annotations

import base64
import os
import select
import socket
import threading


class ProxyRelay(threading.Thread):
    def __init__(self, host: str, port: str, user: str, password: str):
        super().__init__(daemon=True)
        self.upstream = (host, int(port))
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self._authorization = f"Proxy-Authorization: Basic {token}"
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(32)
        self.port = self._server.getsockname()[1]
        self._stopped = False

    def run(self) -> None:
        while not self._stopped:
            try:
                client, _ = self._server.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def stop(self) -> None:
        self._stopped = True
        try:
            self._server.close()
        except OSError:
            pass

    def _handle(self, client: socket.socket) -> None:
        upstream = None
        try:
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = client.recv(4096)
                if not chunk:
                    return
                request += chunk
            header, _, body = request.partition(b"\r\n\r\n")
            first_line = header.split(b"\r\n", 1)[0]
            method, target, _ = first_line.split(b" ", 2)
            upstream = socket.create_connection(self.upstream, timeout=30)

            if method.upper() == b"CONNECT":
                target_text = target.decode("ascii", errors="replace")
                upstream.sendall(
                    f"CONNECT {target_text} HTTP/1.1\r\n"
                    f"Host: {target_text}\r\n{self._authorization}\r\n\r\n".encode()
                )
                response = self._read_headers(upstream)
                if response.split(b"\r\n", 1)[0].find(b" 200 ") >= 0:
                    client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                    self._pipe(client, upstream)
                else:
                    client.sendall(response)
            else:
                injected = header.replace(
                    b"\r\n", f"\r\n{self._authorization}".encode(), 1
                )
                upstream.sendall(injected + b"\r\n\r\n" + body)
                self._pipe(client, upstream)
        except (OSError, ValueError):
            pass
        finally:
            for connection in (client, upstream):
                if connection:
                    try:
                        connection.close()
                    except OSError:
                        pass

    @staticmethod
    def _read_headers(connection: socket.socket) -> bytes:
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = connection.recv(4096)
            if not chunk:
                break
            response += chunk
        return response

    @staticmethod
    def _pipe(left: socket.socket, right: socket.socket) -> None:
        try:
            idle_timeout = float(os.environ.get("UPLOADER_LEGACY_PROXY_IDLE_TIMEOUT", "1800"))
        except ValueError:
            idle_timeout = 1800.0
        while True:
            try:
                readable, _, _ = select.select([left, right], [], [], idle_timeout)
            except (OSError, ValueError):
                return
            if not readable:
                return
            for source in readable:
                destination = right if source is left else left
                try:
                    data = source.recv(8192)
                    if not data:
                        return
                    destination.sendall(data)
                except OSError:
                    return
