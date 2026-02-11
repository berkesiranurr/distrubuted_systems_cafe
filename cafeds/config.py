import os

# ---- Networking ----
DISCOVERY_PORT = int(os.environ.get("CAFEDS_DISCOVERY_PORT", "37020"))
NODE_UDP_BASE = int(os.environ.get("CAFEDS_NODE_UDP_BASE", "37100"))

# ---- Timings ----
DISCOVERY_INTERVAL = 1.0
HEARTBEAT_INTERVAL = 1.0
LEADER_TIMEOUT = 3.5

ELECTION_ANSWER_TIMEOUT = 1.2
COORDINATOR_TIMEOUT = 3.0

# ---- Logging ----
LOG_PREFIX = "[CafeDS]"

# ---- WAL (Write-Ahead Log) Persistence ----
# Enable/disable WAL (set to False to disable disk persistence)
WAL_ENABLED = True
# WAL file path pattern ({node_id} will be replaced with actual node ID)
WAL_FILE = "cafeds_wal_node_{node_id}.jsonl"

# ---- Omission Fault Tolerance ----
# Number of times to send each heartbeat (reduces false elections from packet loss)
HEARTBEAT_REDUNDANCY = 2

# ---- Peer expiry ----
# How long (seconds) before an unseen peer is removed from the registry
PEER_EXPIRY = 5.0
