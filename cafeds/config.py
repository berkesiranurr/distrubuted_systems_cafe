# ---- Networking ----
DISCOVERY_PORT = 37020
NODE_UDP_BASE = 37100

# Default (will be overridden below)
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
# Prefer the active LAN interface broadcast (works on multi-PC),
# but keep localhost for single-PC tests.

import socket as _socket

def _cafeds_default_ipv4() -> str:
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    try:
        # no traffic actually sent; selects default route interface
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        try:
            s.close()
        except Exception:
            pass

def _cafeds_broadcast24(ip: str) -> str:
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3] + ["255"])
    return "255.255.255.255"

try:
    _ip = _cafeds_default_ipv4()

    # If we only have loopback/link-local, fallback to generic broadcast.
    if _ip.startswith("127.") or _ip.startswith("169.254.") or _ip.startswith("0."):
        DISCOVERY_TARGETS = ["255.255.255.255", "127.0.0.1"]
    else:
        DISCOVERY_TARGETS = [_cafeds_broadcast24(_ip), "255.255.255.255", "127.0.0.1"]
except Exception:
    DISCOVERY_TARGETS = ["255.255.255.255", "127.0.0.1"]
# ------------------------------------------------------------------
