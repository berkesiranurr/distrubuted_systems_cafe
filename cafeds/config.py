# ---- Networking ----
DISCOVERY_PORT = 37020
NODE_UDP_BASE = 37100

# Default (overridden below)
DISCOVERY_TARGETS = ["255.255.255.255"]

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


# ---------------- CafeDS AUTO DISCOVERY (final) ----------------
# Multi-PC default:
#   - Use LAN /24 broadcast + global broadcast
#   - DO NOT include 127.0.0.1 (prevents "leader=127.0.0.1" self-connect bugs)
#
# Single-PC test (3 terminals on same machine):
#   - set env: CAFEDS_SINGLE_PC=1  -> adds 127.0.0.1 back

import os as _os
import socket as _socket

def _cafeds_default_ipv4() -> str:
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    try:
        # No traffic is actually sent; selects the default-route interface.
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

# Build discovery targets
_ip = _cafeds_default_ipv4()
targets = []

# If IP is valid LAN IP, prefer its /24 broadcast
if not (_ip.startswith("127.") or _ip.startswith("169.254.") or _ip.startswith("0.")):
    targets.append(_cafeds_broadcast24(_ip))

# Always add global broadcast
targets.append("255.255.255.255")

# Single-PC mode: allow localhost discovery explicitly
if _os.environ.get("CAFEDS_SINGLE_PC", "").strip() in ("1", "true", "TRUE", "yes", "YES"):
    targets.append("127.0.0.1")

# Remove duplicates while preserving order
seen = set()
DISCOVERY_TARGETS = []
for x in targets:
    if x not in seen:
        DISCOVERY_TARGETS.append(x)
        seen.add(x)
# ------------------------------------------------------------------