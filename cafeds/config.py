# ---- Networking ----
DISCOVERY_PORT = 37020
NODE_UDP_BASE = 37100

# Backward-compat: node.py may import this symbol.
# Actual runtime discovery uses cafeds.net.discovery_targets().
DISCOVERY_TARGETS = ["127.0.0.1", "255.255.255.255"]

# ---- Timings ----
DISCOVERY_INTERVAL = 1.0
HEARTBEAT_INTERVAL = 1.0
LEADER_TIMEOUT = 3.5

ELECTION_ANSWER_TIMEOUT = 1.2
COORDINATOR_TIMEOUT = 3.0

# ---- Cluster ----
CLUSTER_NODE_IDS = [2, 3, 10]

# ---- Logging ----
LOG_PREFIX = "[CafeDS]"


# ---------------- CafeDS AUTO DISCOVERY (override) ----------------
# Prefer Wi-Fi LAN (your case 192.168.1.x) instead of VirtualBox host-only (192.168.56.x)
import socket as _socket

def _cafeds_default_ipv4() -> str:
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    try:
        # no traffic is actually sent; this just picks the default route interface
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

def _cafeds_broadcast24(ip: str) -> str:
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3] + ["255"])
    return "255.255.255.255"

# force discovery to Wi-Fi / default route broadcast + keep localhost for single-PC tests
try:
    _ip = _cafeds_default_ipv4()
    if _ip.startswith("192.168.56."):
        # if default route somehow points to VirtualBox, fallback to generic broadcast
        DISCOVERY_TARGETS = ["255.255.255.255", "127.0.0.1"]
    else:
        DISCOVERY_TARGETS = [_cafeds_broadcast24(_ip), "127.0.0.1"]
except Exception:
    DISCOVERY_TARGETS = ["255.255.255.255", "127.0.0.1"]
# ------------------------------------------------------------------

