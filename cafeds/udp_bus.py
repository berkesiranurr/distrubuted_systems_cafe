import socket
from typing import Tuple


def make_udp_socket(port: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # broadcast enable (needed for 255.255.255.255)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind(("", port))
    s.settimeout(0.5)
    return s


def send_udp(sock: socket.socket, payload: bytes, ip: str, port: int) -> None:
    sock.sendto(payload, (ip, port))


def recv_udp(sock: socket.socket) -> Tuple[bytes, Tuple[str, int]]:
    return sock.recvfrom(65535)
