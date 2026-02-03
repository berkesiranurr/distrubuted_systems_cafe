import json
import socket
from typing import Any, Dict, Callable


def send_json_line(sock: socket.socket, msg: Dict[str, Any]) -> None:
    data = json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n"
    sock.sendall(data.encode("utf-8"))


def read_json_lines(
    sock: socket.socket, on_msg: Callable[[Dict[str, Any]], None]
) -> None:
    buffer = b""
    while True:
        try:
            data = sock.recv(4096)
            if not data:
                break
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                    on_msg(msg)
                except Exception:
                    continue
        except socket.timeout:
            continue
        except Exception:
            break
