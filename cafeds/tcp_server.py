import socket
import threading
from typing import Dict, Any, Callable, List, Optional

from .tcp_stream import send_json_line, read_json_lines

class ClientConn:
    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.lock = threading.Lock()

    def send(self, msg: Dict[str, Any]) -> None:
        with self.lock:
            send_json_line(self.sock, msg)

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


class TCPServer:
    def __init__(self, host: str, port: int, on_msg: Callable[[ClientConn, Dict[str, Any]], None], on_log: Callable[[str], None]):
        self.host = host
        self.port = port
        self.on_msg = on_msg
        self.on_log = on_log

        self.sock: Optional[socket.socket] = None
        self.stop_event = threading.Event()

        self.clients: List[ClientConn] = []
        self.clients_lock = threading.Lock()

    def start(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(50)

        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()
        self.on_log(f"TCPServer listening on {self.host}:{self.port}")

    def _accept_loop(self) -> None:
        assert self.sock is not None
        while not self.stop_event.is_set():
            try:
                c, addr = self.sock.accept()
                conn = ClientConn(c, addr)
                with self.clients_lock:
                    self.clients.append(conn)
                self.on_log(f"TCP client connected: {addr}")

                rt = threading.Thread(target=self._client_reader, args=(conn,), daemon=True)
                rt.start()
            except Exception:
                continue

    def _client_reader(self, conn: ClientConn) -> None:
        try:
            read_json_lines(conn.sock, lambda m: self.on_msg(conn, m))
        except Exception:
            pass
        finally:
            with self.clients_lock:
                if conn in self.clients:
                    self.clients.remove(conn)
            self.on_log(f"TCP client disconnected: {conn.addr}")
            conn.close()

    def broadcast(self, msg: Dict[str, Any]) -> None:
        with self.clients_lock:
            targets = list(self.clients)
        for c in targets:
            try:
                c.send(msg)
            except Exception:
                pass

    def stop(self) -> None:
        self.stop_event.set()
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        with self.clients_lock:
            targets = list(self.clients)
            self.clients.clear()
        for c in targets:
            c.close()
