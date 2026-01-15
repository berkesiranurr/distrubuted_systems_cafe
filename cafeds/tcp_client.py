import socket
import threading
from typing import Dict, Any, Callable, Optional

from .tcp_stream import send_json_line, read_json_lines

class TCPClient:
    def __init__(self, on_msg: Callable[[Dict[str, Any]], None], on_log: Callable[[str], None]):
        self.on_msg = on_msg
        self.on_log = on_log

        self.sock: Optional[socket.socket] = None
        self.lock = threading.Lock()
        self.reader_thread: Optional[threading.Thread] = None

    def connect(self, host: str, port: int, timeout: float = 3.0) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.settimeout(None)
            self.sock = s

            self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.reader_thread.start()

            self.on_log(f"TCP connected to leader {host}:{port}")
            return True
        except Exception as e:
            self.on_log(f"TCP connect failed to {host}:{port} ({e})")
            self.close()
            return False

    def _reader_loop(self) -> None:
        assert self.sock is not None
        try:
            read_json_lines(self.sock, self.on_msg)
        except Exception:
            pass
        finally:
            self.on_log("TCP reader stopped (disconnected)")
            self.close()

    def send(self, msg: Dict[str, Any]) -> None:
        if not self.sock:
            return
        with self.lock:
            send_json_line(self.sock, msg)

    def close(self) -> None:
        with self.lock:
            try:
                if self.sock:
                    self.sock.close()
            except Exception:
                pass
            self.sock = None
