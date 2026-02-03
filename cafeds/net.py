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


def discovery_targets() -> List[str]:
    ip = primary_ip()
    targets = ["127.0.0.1", "255.255.255.255"]
    if not ip.startswith("127."):
        targets.append(guess_directed_broadcast(ip))
    # unique preserve order
    out = []
    for x in targets:
        if x not in out:
            out.append(x)
    return out
