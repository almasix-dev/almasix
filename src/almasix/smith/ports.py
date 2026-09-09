"""Helpers for ``python smith serve`` port selection."""

from __future__ import annotations

import socket

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3000
MAX_PORT = 3099


class NoFreePortError(RuntimeError):
    """Raised when no free port is available in the discovery range."""


def is_port_free(host: str, port: int) -> bool:
    """Return True if ``host:port`` can be bound."""
    family = socket.AF_INET6 if ":" in host and not host.startswith(":") else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_available_port(
    host: str = DEFAULT_HOST,
    start: int = DEFAULT_PORT,
    end: int = MAX_PORT,
) -> int:
    """Find the first free TCP port in ``[start, end]`` inclusive."""
    if start > end:
        raise ValueError(f"start port {start} is greater than end port {end}")

    for port in range(start, end + 1):
        if is_port_free(host, port):
            return port

    raise NoFreePortError(f"No free port found on {host} between {start} and {end}.")
