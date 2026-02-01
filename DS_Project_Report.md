# DS Project Report - CaféDS

> **Note**: This document fills out all sections of the DS_Project_Report_Form.pdf based on analysis of your codebase. Copy these answers to the PDF form.

---

## Project Information

| Field | Value |
|-------|-------|
| **Group ID** | 21 |
| **Semester** | WS2024/2025 |
| **1. Student Name** | Hakan Berke Siranur |
| **2. Student Name** | Berkay Cagri Soylu |
| **3. Student Name** | Emre Erisen |
| **4. Student Name** | Junichi Nagasawa |
| **Project Title** | CaféDS: Distributed Order & Kitchen Display System |
| **GitHub/GitLab URL** | https://github.com/berkesiranurr/distrubuted_systems_cafe |

---

## Project Description

CaféDS is a distributed kitchen display system for a café LAN. Waiter devices (phones/tablets) can place orders, and the kitchen screen (and other terminals) show these orders in a strict "first-come-first-served" way. Even if two waiters submit at the same time, every device shows the same global order. If the leader device crashes, the remaining nodes pick a new leader and keep the system running.

---

## Architectural Model

### Architecture Type
- [x] **Client-Server**
- [ ] Peer-to-Peer
- [ ] Hybrid
- [ ] Other

**Explanation**: CaféDS uses a client-server architecture with role switching. One node is the **Leader** (server + sequencer + kitchen display) and others are **Waiters** (clients). Any node can become Leader after an election, making it a dynamic client-server model.

---

## Communication

### UDP
**Used for**: Lightweight control messages including:
- Discovery (`WHO_IS_LEADER`, `I_AM_LEADER`)
- Heartbeats (`LEADER_ALIVE`)
- Election messages (`ELECTION`, `ANSWER`, `COORDINATOR`)

### TCP
**Used for**: Reliable order submission and ordered updates:
- `NEW_ORDER` - Waiter submits order to Leader
- `ORDER` - Leader broadcasts sequenced orders to all clients
- `RESEND_REQUEST` - Clients request missing orders for catch-up

---

## Concurrency

### Multithreading
**Used for**: 
- UDP node listener thread (handles discovery, heartbeats, election messages)
- UDP discovery listener thread (Leader only - handles `WHO_IS_LEADER` requests)
- Follower discovery loop thread (timeout detection, leader discovery)
- TCP server accept loop + per-client reader threads (Leader)
- TCP client reader thread (Follower)
- Leader heartbeat broadcast thread
- Stdin order input thread (Waiter UI)

### Multiprocessing
**Used for**: Not implemented. All concurrency is handled via Python's `threading` module.

---

## System Architecture Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CaféDS Architecture                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────────┐         UDP (Discovery/Heartbeat/Election)    │
│   │   LEADER NODE       │◄────────────────────────────────────────────┐ │
│   │  (Kitchen Display)  │                                             │ │
│   │                     │                                             │ │
│   │  ┌───────────────┐  │     TCP (Orders/Sync)                       │ │
│   │  │ Sequencer     │  │◄──────────────────────┐                     │ │
│   │  │ (seq counter) │  │                       │                     │ │
│   │  └───────────────┘  │                       │                     │ │
│   │  ┌───────────────┐  │                       │                     │ │
│   │  │ Order History │  │                       │                     │ │
│   │  │ (Dict[seq→msg])│ │                       │                     │ │
│   │  └───────────────┘  │                       │                     │ │
│   │  ┌───────────────┐  │                       │                     │ │
│   │  │ TCP Server    │  │                       │                     │ │
│   │  │ (broadcast)   │  │                       │                     │ │
│   │  └───────────────┘  │                       │                     │ │
│   └─────────────────────┘                       │                     │ │
│              │                                  │                     │ │
│              │ LEADER_ALIVE (UDP)               │                     │ │
│              │ ORDER (TCP broadcast)            │                     │ │
│              ▼                                  │                     │ │
│   ┌─────────────────────┐    ┌─────────────────────┐                  │ │
│   │   FOLLOWER NODE 1   │    │   FOLLOWER NODE 2   │                  │ │
│   │   (Waiter Tablet)   │    │   (Kitchen Screen)  │                  │ │
│   │                     │    │                     │                  │ │
│   │  ┌───────────────┐  │    │  ┌───────────────┐  │                  │ │
│   │  │ TCP Client    │──┼────┼──│ TCP Client    │──┼──────────────────┘ │
│   │  └───────────────┘  │    │  └───────────────┘  │                    │
│   │  ┌───────────────┐  │    │  ┌───────────────┐  │                    │
│   │  │ Local History │  │    │  │ Local History │  │    (Election msgs) │
│   │  │ + Buffer      │  │    │  │ + Buffer      │  │◄───────────────────┘
│   │  └───────────────┘  │    │  └───────────────┘  │
│   │  ┌───────────────┐  │    │                     │
│   │  │ Waiter UI     │  │    │                     │
│   │  │ (stdin input) │  │    │                     │
│   │  └───────────────┘  │    │                     │
│   └─────────────────────┘    └─────────────────────┘
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Dynamic Discovery of Hosts

### Discovery Mechanism
- [x] **Broadcast**
- [ ] Multicast
- [ ] Other

**Explanation**: UDP broadcast discovery on port 37020. Nodes broadcast `WHO_IS_LEADER(sender_id, sender_tcp_port)` to the /24 network broadcast address and 255.255.255.255. The active Leader replies with `I_AM_LEADER(leader_id, leader_ip, leader_tcp_port, epoch, last_seq)`.

### Discovery Implemented
- [x] **Client discovers server**
- [ ] Server discovers servers
- [ ] Other

### Discovery Occurs
- [x] **When system starts**
- [x] **Whenever new component comes in**
- [ ] Other

**Explanation**: Discovery runs continuously in `_follower_discovery_loop()` with `DISCOVERY_INTERVAL = 1.0` seconds. New nodes discover the leader on startup, and rediscovery happens if leader becomes unknown (e.g., after crash).

---

## Voting

### Voting Implemented Using
- [x] **Bully Algorithm**
- [ ] LeLann-Chang-Roberts Algorithm
- [ ] Hirschberg-Sinclair Algorithm

**Explanation**: Each node has a unique `node_id`. Higher ID = higher priority. When heartbeats stop for `LEADER_TIMEOUT`, a node broadcasts `ELECTION(candidate_id, epoch+1)`. Higher-ID nodes reply `ANSWER` and start their own election. If no `ANSWER` received within timeout, the node declares itself Leader with `COORDINATOR` message.

### Group View Used
- [ ] No
- [x] **Yes**

**What group view is used for**: The `CLUSTER_NODE_IDS = [2, 3, 10]` in `config.py` defines known node IDs. This is used for:
- Sending heartbeats to all cluster members
- Determining which nodes are "higher" in Bully election
- Broadcasting COORDINATOR messages after winning election

### Nodes Identified Using
- [ ] IP addresses / IP addresses + ports
- [x] **UUIDs**
- [ ] Other

**Explanation**: Nodes are identified by integer `node_id` values (comparable for Bully algorithm). Each UDP port is derived as `NODE_UDP_BASE + node_id`. Orders use UUID (`uuid.uuid4()`) for deduplication.

### Election Starts
- [ ] When system starts
- [ ] When a new server joins
- [x] **When the leader fails**

**Explanation**: Election is triggered in `_follower_discovery_loop()` when `now - leader.last_seen_ts > LEADER_TIMEOUT` (3.5 seconds default). This happens only when the Leader is perceived to have crashed (crash-stop failure model).

---

## Reliable Ordered Multicast

### Type of Ordering
- [ ] FIFO Ordering
- [ ] Causal Ordering
- [x] **Total Ordering**

### Reason for Chosen Ordering
The kitchen queue must be **identical on all screens**. When two waiters submit orders simultaneously, all devices must see them in the exact same sequence. Total ordering via a Leader-based sequencer ensures every node delivers messages in the same global order.

### Reliability Mechanism
- [ ] Acknowledgements
- [x] **Negative Acknowledgments**
- [x] **Sequencing**
- [ ] Other

**Explanation**:
1. **Sequencing**: Leader assigns global `seq` numbers to each order. Clients deliver only when `seq == expected_seq`.
2. **Negative Acknowledgments**: When a client detects a gap (received seq > expected), it buffers the message and sends `RESEND_REQUEST(from_seq)` to get missing orders.
3. **TCP**: Provides reliable per-connection delivery; sequence numbers enable catch-up after reconnect.

---

## Fault Tolerance

### Faults Tolerated
- [x] **Crash Faults (Leader Server, Regular Server, Client)**
- [ ] Omission Faults
- [ ] Byzantine Faults

**Explanation**: The system is designed for **crash-stop failures** of the Leader. When the Leader crashes, followers detect the failure and elect a new Leader. Client crashes are handled gracefully (TCP disconnect cleanup). The new Leader reconstructs state from its local history.

### Fault Detection
**Who sends heartbeats to whom, frequency, and retries**:
- **Leader → All Followers**: `LEADER_ALIVE(leader_id, epoch, last_seq)` every `HEARTBEAT_INTERVAL = 1.0` second via UDP
- **Detection**: If a follower doesn't receive heartbeats for `LEADER_TIMEOUT = 3.5` seconds, it considers the Leader crashed
- **No explicit retries**: Heartbeats are broadcast continuously; missing heartbeats trigger election

### Recovery Strategy
1. **Election**: When Leader crash detected, Bully Algorithm elects the highest-ID available node
2. **State Reconstruction**: New Leader uses its local `history` (all delivered orders stored locally) and continues with `seq = last_seq + 1`
3. **Catch-up**: Reconnecting clients send `RESEND_REQUEST(last_seq_seen)` to get missed orders
4. **Epoch**: Each election increments `epoch` to distinguish between Leadership periods

---

## Implementation Details

| Component | File | Description |
|-----------|------|-------------|
| Main Node Logic | [node.py](file:///d:/University%20of%20Stuttgart/Distributed%20Systems%201/distrubuted_systems_cafe/cafeds/node.py) | Node class with election, ordering, TCP/UDP handling |
| Configuration | [config.py](file:///d:/University%20of%20Stuttgart/Distributed%20Systems%201/distrubuted_systems_cafe/cafeds/config.py) | Network ports, timeouts, cluster node IDs |
| Protocol Messages | [proto.py](file:///d:/University%20of%20Stuttgart/Distributed%20Systems%201/distrubuted_systems_cafe/cafeds/proto.py) | JSON message builders for all message types |
| TCP Server | [tcp_server.py](file:///d:/University%20of%20Stuttgart/Distributed%20Systems%201/distrubuted_systems_cafe/cafeds/tcp_server.py) | Leader's TCP server for client connections |
| TCP Client | [tcp_client.py](file:///d:/University%20of%20Stuttgart/Distributed%20Systems%201/distrubuted_systems_cafe/cafeds/tcp_client.py) | Follower's TCP client for Leader connection |
| UDP Bus | [udp_bus.py](file:///d:/University%20of%20Stuttgart/Distributed%20Systems%201/distrubuted_systems_cafe/cafeds/udp_bus.py) | UDP socket utilities with broadcast support |
| Network Utils | [net.py](file:///d:/University%20of%20Stuttgart/Distributed%20Systems%201/distrubuted_systems_cafe/cafeds/net.py) | IP detection, broadcast address calculation |
| Entry Point | [run_node.py](file:///d:/University%20of%20Stuttgart/Distributed%20Systems%201/distrubuted_systems_cafe/run_node.py) | CLI entry point for starting nodes |

---

## Missing/Incomplete Areas to Fix

> [!NOTE]
> The following items have been reviewed and updated:

### 1. Write-Ahead Log (WAL)
- **Proposal**: "Optionally, the Leader writes each accepted order to a WAL before acknowledging"
- **Current Code**: ✅ **IMPLEMENTED** - Orders are persisted to disk via `_append_to_wal()` before broadcasting
- **Config**: `WAL_ENABLED = True`, `WAL_FILE = "cafeds_wal_node_{node_id}.jsonl"`
- **Recovery**: `_recover_from_wal()` restores history on startup

### 2. Order UUID Deduplication
- **Proposal**: "Uses unique order_uuid to deduplicate resends after reconnect"
- **Current Code**: ✅ **IMPLEMENTED** - The Leader tracks `seen_order_uuids` and ignores any duplicate `order_uuid` received from clients.
- **Behavior**: Duplicate orders are logged and ignored to prevent double delivery.

### 3. Omission Fault Tolerance
- **Current Code**: ✅ **IMPLEMENTED** - Heartbeats sent multiple times per interval (`HEARTBEAT_REDUNDANCY = 2`)
- **Benefit**: Reduces false leader-timeout elections due to UDP packet loss

### 4. GitHub/GitLab Repository URL
- **Report Form**: Requires repository URL
- **Current Status**: ✅ **UPDATED** - Repository URL added to the Project Information section.

### 5. System Architecture Diagram
- **Report Form**: "Include a clear diagram of your system architecture"
- **Recommendation**: Create a visual diagram (draw.io, Lucidchart, or hand-drawn) showing the components and connections. The ASCII diagram above can be used as reference.

---

## Summary Checklist

| Report Section | Status | Notes |
|----------------|--------|-------|
| Project Information | ✅ Complete | Add GitHub URL |
| Project Description | ✅ Complete | |
| Architecture Type | ✅ Complete | Client-Server with role switching |
| Communication (UDP/TCP) | ✅ Complete | |
| Concurrency | ✅ Complete | Multithreading |
| System Architecture Design | ⚠️ Needs Diagram | Create visual diagram for PDF |
| Discovery Mechanism | ✅ Complete | UDP Broadcast |
| Discovery Implementation | ✅ Complete | Client discovers server |
| Discovery Timing | ✅ Complete | On startup + continuous |
| Voting Algorithm | ✅ Complete | Bully Algorithm |
| Group View | ✅ Complete | CLUSTER_NODE_IDS |
| Node Identification | ✅ Complete | Integer node_id + UUID for orders |
| Election Trigger | ✅ Complete | On leader failure |
| Ordering Type | ✅ Complete | Total Ordering |
| Ordering Reason | ✅ Complete | Kitchen queue consistency |
| Reliability Mechanism | ✅ Complete | Sequencing + NACK |
| Faults Tolerated | ✅ Complete | Crash faults |
| Fault Detection | ✅ Complete | Heartbeats |
| Recovery Strategy | ✅ Complete | Election + history reconstruction |

---

# Appendix: Missing Features & Implementation Recommendations

This section is for **team discussion** - it lists all features NOT currently implemented and provides guidance on how to add them if needed.

---

## 1. Fault Tolerance - Not Implemented Faults

### 1.1 Omission Faults ❌
**What it is**: Messages are lost (not delivered) even though sender/receiver are both alive. Different from crash faults where a node completely stops.

**Current Gap**: Our system assumes TCP reliably delivers all messages. If a message is dropped at network level before TCP handles it, we rely on TCP retransmission. For UDP (heartbeats/discovery), lost packets could cause false leader-timeout.

**How to implement**:
```python
# In node.py, add acknowledgment tracking for critical UDP messages:
class Node:
    def __init__(self, ...):
        self.pending_acks: Dict[str, float] = {}  # msg_id -> send_time
        
    def _send_with_ack(self, target_id: int, msg: Dict) -> None:
        msg["msg_id"] = str(uuid.uuid4())
        self.pending_acks[msg["msg_id"]] = time.time()
        self._send_to_node(target_id, msg)
        
    def _handle_ack(self, msg_id: str) -> None:
        self.pending_acks.pop(msg_id, None)
        
    def _retransmit_loop(self) -> None:
        """Retransmit unacknowledged messages after timeout"""
        while not self.stop_event.is_set():
            now = time.time()
            for msg_id, send_time in list(self.pending_acks.items()):
                if now - send_time > RETRANSMIT_TIMEOUT:
                    # Retransmit or mark as failed
                    pass
            time.sleep(0.5)
```

### 1.2 Byzantine Faults ❌
**What it is**: Nodes can behave arbitrarily - send wrong data, lie, or act maliciously.

**Current Gap**: We trust all messages. A malicious node could:
- Claim to be Leader with fake epoch
- Send wrong sequence numbers
- Corrupt order payloads

**How to implement** (complex - requires significant changes):
```python
# Option 1: HMAC message authentication
import hmac, hashlib

SHARED_SECRET = b"cafe_secret_key"  # In production, use per-node keys

def sign_message(msg: Dict) -> Dict:
    msg_bytes = json.dumps(msg, sort_keys=True).encode()
    msg["signature"] = hmac.new(SHARED_SECRET, msg_bytes, hashlib.sha256).hexdigest()
    return msg

def verify_message(msg: Dict) -> bool:
    sig = msg.pop("signature", None)
    msg_bytes = json.dumps(msg, sort_keys=True).encode()
    expected = hmac.new(SHARED_SECRET, msg_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig or "", expected)

# Option 2: For full Byzantine fault tolerance, implement PBFT
# Requires 3f+1 nodes to tolerate f Byzantine faults
# Very complex - likely overkill for café system
```

**Recommendation**: Byzantine tolerance is likely **out of scope** for this project. Mention in report that it's not needed for trusted café LAN environment.

---

## 2. Persistence - Write-Ahead Log (WAL) ❌

**What it is**: Before acknowledging an order, write it to disk. If Leader crashes and restarts, it can recover from disk.

**Current Gap**: All orders stored only in `self.history` (memory). Leader crash = all orders lost.

**How to implement**:
```python
# In node.py, add WAL
import os
import json

WAL_FILE = "cafeds_wal.jsonl"

class Node:
    def _append_to_wal(self, order: Dict) -> None:
        with open(WAL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(order) + "\n")
            f.flush()
            os.fsync(f.fileno())  # Ensure durably written
    
    def _recover_from_wal(self) -> None:
        if not os.path.exists(WAL_FILE):
            return
        with open(WAL_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    order = json.loads(line.strip())
                    seq = order.get("seq", 0)
                    self.history[seq] = order
                    self.last_seq = max(self.last_seq, seq)
                except Exception:
                    pass

# Modify _start_tcp_leader to call _append_to_wal before broadcasting:
# self._append_to_wal(om)  # <-- Add this line
# self.tcp_server.broadcast(om)
```

---

## 3. Order UUID Deduplication ⚠️ (Partial)

**What it is**: Prevent same order from being processed twice if client retries.

**Current Gap**: `order_uuid` is generated but no dedup check exists in Leader.

**How to implement**:
```python
# In node.py, add to Node.__init__:
self.seen_order_uuids: Set[str] = set()

# In _start_tcp_leader, inside on_msg for NEW_ORDER:
def on_msg(conn: ClientConn, msg: Dict[str, Any]) -> None:
    if mtype == "NEW_ORDER":
        order_uuid = str(msg.get("order_uuid", ""))
        
        # ADD THIS CHECK:
        if order_uuid in self.seen_order_uuids:
            self.log(f"Duplicate order ignored: {order_uuid}")
            return
        self.seen_order_uuids.add(order_uuid)
        
        # ... rest of existing code
```

---

## 4. Concurrency - Multiprocessing ❌

**What it is**: Using multiple Python processes instead of threads (bypasses Python GIL).

**Current Gap**: Only multithreading used. For CPU-bound tasks, multiprocessing would be faster.

**Why it's OK**: CaféDS is I/O-bound (network communication), not CPU-bound. Multithreading is appropriate.

**How to implement if needed**:
```python
from multiprocessing import Process, Queue

# Instead of threading.Thread:
p = Process(target=worker_function, args=(queue,))
p.start()

# Communication via Queue instead of shared memory
```

---

## 5. Discovery - Multicast ❌

**What it is**: Send to a specific group of hosts (between unicast and broadcast).

**Current Gap**: Using broadcast (255.255.255.255 and /24 broadcast). Works but slightly less efficient.

**How to implement**:
```python
MULTICAST_GROUP = "239.255.1.1"  # Choose a multicast address
MULTICAST_PORT = 37020

def make_multicast_socket(port: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Join multicast group
    mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    
    s.bind(("", port))
    return s
```

**Recommendation**: Broadcast works fine for café LAN. Multicast would only matter for larger networks.

---

## 6. Architecture - Peer-to-Peer ❌

**What it is**: All nodes are equal, no dedicated server.

**Current Gap**: We use Client-Server with Leader election. Leader is special.

**Why Client-Server is correct**: Total ordering requires a central sequencer. Pure P2P would need consensus (Paxos/Raft) which is much more complex.

**How to implement P2P ordering** (not recommended):
- Use Lamport clocks for FIFO/causal ordering
- Use vector clocks for tracking happens-before
- For total ordering: implement Paxos or Raft consensus

---

## 7. Discovery - Server Discovers Servers ❌

**What it is**: Servers discover each other (mesh network).

**Current Gap**: Only clients discover the Leader. Leader doesn't discover other potential leaders.

**How to implement**:
```python
# Add periodic announcement from all nodes:
def _announce_presence(self) -> None:
    """All nodes announce themselves periodically"""
    msg = {
        "type": "NODE_PRESENT",
        "node_id": self.node_id,
        "role": self.role,
        "tcp_port": self.tcp_port,
        "epoch": self.epoch
    }
    for ip in DISCOVERY_TARGETS:
        send_udp(self.udp_node, encode(msg), ip, DISCOVERY_PORT)

# Maintain a node registry:
self.known_nodes: Dict[int, NodeInfo] = {}
```

---

## 8. Other Voting Algorithms ❌

### LeLann-Chang-Roberts Algorithm
**What it is**: Ring-based election. Pass election message around ring, highest ID wins.

**Current**: Using Bully (broadcast-based, faster but more messages).

### Hirschberg-Sinclair Algorithm  
**What it is**: Optimized ring algorithm, O(n log n) messages instead of O(n²).

**Why Bully is OK**: Simple to implement, works well for small cluster (3 nodes). Ring algorithms require maintaining ring topology.

---

## 9. Acknowledgments vs Negative Acknowledgments

**Current**: Using **Negative ACKs (NACKs)** - only request retransmission when gap detected.

**ACKs would require**:
```python
# Client sends ACK after receiving each ORDER
def _process_order(self, msg: Dict) -> None:
    # ... existing delivery logic ...
    
    # Send ACK back to leader
    ack = {"type": "ORDER_ACK", "seq": msg["seq"], "node_id": self.node_id}
    self.tcp_client.send(ack)

# Leader tracks ACKs and retransmits if not received
```

**Why NACKs are better here**: Less network traffic. TCP already provides reliability per-connection.

---

## Quick Fix Priority List

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 🔴 High | UUID Deduplication | 5 min | Prevents duplicate orders |
| 🟡 Medium | WAL Persistence | 30 min | Survives Leader restart |
| 🟡 Medium | Architecture Diagram | 30 min | Required for report |
| 🟢 Low | Message Signing | 2 hrs | Byzantine tolerance |
| 🟢 Low | Multicast | 1 hr | Slight efficiency gain |
| ⚪ N/A | Multiprocessing | - | Not needed (I/O bound) |
| ⚪ N/A | P2P Architecture | - | Would break total ordering |

---

## 🎯 Team Action Items (Fixes to Implement)

> [!IMPORTANT]
> These are the practical fixes your team should implement before submission. Items are ordered by priority.

| # | Fix | File to Edit | What to Do | Why It Matters |
|---|-----|--------------|------------|----------------|
| 1 | **Architecture Diagram** | PDF Report | Convert the ASCII diagram in this doc to a visual diagram using draw.io, Lucidchart, or Canva | Report form explicitly requires a diagram |
| 2 | **GitHub URL** | PDF Report | Add your repository URL to the Project Information section | Required field in report form |
| 3 | **WAL Persistence** *(Optional)* | `node.py` | Add `_append_to_wal()` and `_recover_from_wal()` methods, call append before broadcasting ORDER | Mentioned in proposal as "optional", provides crash durability |

### What You DON'T Need to Fix

| Item | Why It's OK to Skip |
|------|---------------------|
| Omission Faults | TCP already handles packet loss with retransmission; UDP heartbeat loss triggers election which is acceptable |
| Byzantine Faults | Trusted café LAN environment - no malicious nodes expected |
| Multiprocessing | System is I/O-bound, not CPU-bound; threading is appropriate |
| Multicast | Broadcast works fine for small LAN; multicast adds complexity with no real benefit |
| P2P Architecture | Would require Paxos/Raft consensus for total ordering - much more complex |
| Ring-based Elections | Bully works well for 3 nodes; ring algorithms need topology maintenance |
| ACKs instead of NACKs | NACKs are more efficient; TCP provides per-connection reliability already |

---

## Recommended Actions Before Submission

1. **Add UUID dedup check** (5 minutes, critical for correctness)
2. **Create visual architecture diagram** (required for report)
3. **Add GitHub URL** to report
4. **Test leader failover scenario** to verify election works
5. **Document** any decisions about why omission/Byzantine faults are out of scope

