import json
import socket
from typing import Any, Dict, Callable

def send_json_line(sock: socket.socket, msg: Dict[str, Any]) -> None:
    data = json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n"
    sock.sendall(data.encode("utf-8"))

def read_json_lines(sock: socket.socket, on_msg: Callable[[Dict[str, Any]], None]) -> None:
    f = sock.makefile("r", encoding="utf-8", newline="\n")
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            on_msg(msg)
        except Exception:
            # bozuk satiri ignore
            continue
