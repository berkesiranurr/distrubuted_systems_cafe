import os
import socket
from typing import List


def primary_ip() -> str:
    """
    Best-effort: finds the IP of the default route interface.
    Works on Windows/Linux without external libs.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # connect() on UDP does not send packets, it just picks the route
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass
    return "127.0.0.1"


def local_ip_for_peer(peer_ip: str) -> str:
    """
    Returns the local interface IP that would be used to reach peer_ip.
    Very helpful if machine has multiple NICs.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((peer_ip, 9))
        ip = s.getsockname()[0]
        if ip:
            return ip
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass
    return primary_ip()


def guess_directed_broadcast(ip: str) -> str:
    # simple /24 heuristic (enough for most campus/home LANs)
    parts = ip.split(".")
    if len(parts) == 4 and not ip.startswith("127."):
        return ".".join(parts[:3] + ["255"])
    return "255.255.255.255"


def _is_single_pc_mode() -> bool:
    """Check if CAFEDS_SINGLE_PC env var is set."""
    return os.environ.get("CAFEDS_SINGLE_PC", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def discovery_targets() -> List[str]:
    """
    Build the list of IPs to send discovery / heartbeat broadcasts to.

    Multi-PC (default):
      - LAN /24 broadcast + global broadcast
      - 127.0.0.1 is EXCLUDED (prevents 'leader=127.0.0.1' self-connect bugs)

    Single-PC test (CAFEDS_SINGLE_PC=1):
      - Adds 127.0.0.1 so that nodes on the same machine can find each other
    """
    ip = primary_ip()
    targets: List[str] = []

    # LAN /24 broadcast if we have a real LAN IP
    if not ip.startswith("127."):
        targets.append(guess_directed_broadcast(ip))

    # global broadcast
    targets.append("255.255.255.255")

    # single-PC mode: add localhost so 3-terminal demo works
    if _is_single_pc_mode():
        targets.append("127.0.0.1")

    # deduplicate, preserve order
    out: List[str] = []
    for x in targets:
        if x not in out:
            out.append(x)
    return out
