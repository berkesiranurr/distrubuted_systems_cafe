# DS Project Report Form - CaféDS

---

## 1. Project Information

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

## 2. Project Description

CaféDS is a distributed kitchen display system for café environments running on a local area network. Waiter devices (phones/tablets) submit orders, and kitchen screens display these orders in a strict first-come-first-served order. The system ensures:
- **Global order consistency**: All devices see orders in identical sequence
- **Fault tolerance**: If the leader crashes, remaining nodes elect a new leader
- **Concurrent submissions**: Simultaneous orders from multiple waiters are sequenced deterministically

---

## 3. Architectural Model

### Architecture Type
- [x] **Client-Server**
- [ ] Peer-to-Peer
- [ ] Hybrid
- [ ] Other

**Explanation**:  
Dynamic client-server architecture with role switching. One node acts as **Leader** (server, sequencer, kitchen display) while others are **Followers** (clients, waiters). Any node can become Leader after winning an election.

---

## 4. Communication

### UDP Protocol
**Used for**:
- **Discovery**: `WHO_IS_LEADER`, `I_AM_LEADER` messages
- **Heartbeats**: `LEADER_ALIVE` broadcasts (1.0 second interval, redundancy factor of 2)
- **Election**: `ELECTION`, `ANSWER`, `COORDINATOR` messages for Bully algorithm

### TCP Protocol
**Used for**:
- `NEW_ORDER` – Waiter submits order to Leader
- `ORDER` – Leader broadcasts sequenced orders to all followers
- `RESEND_REQUEST` – Followers request missing orders for catch-up

---

## 5. Concurrency

### Multithreading
**Implemented using**: Python `threading` module

**Threads used**:
1. UDP node listener (discovery, heartbeats, election)
2. UDP discovery listener (Leader only)
3. Follower discovery loop (timeout detection)
4. TCP server accept loop + per-client reader threads (Leader)
5. TCP client reader thread (Follower)
6. Leader heartbeat broadcast thread
7. Stdin order input thread (Waiter UI)

### Multiprocessing
**Used for**: Not implemented. All concurrency via multithreading (I/O-bound workload).

---

## 6. System Architecture Diagram

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
│   │  ┌───────────────┐  │    │  ┌───────────────┐  │    (Election msgs) │
│   │  │ Local History │  │    │  │ Local History │  │◄───────────────────┘
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

## 7. Dynamic Discovery of Hosts

### Discovery Mechanism
- [x] **Broadcast**
- [ ] Multicast
- [ ] Other

**Explanation**:  
UDP broadcast discovery on port 37020. Nodes broadcast `WHO_IS_LEADER(sender_id, sender_tcp_port)` to the /24 network broadcast address and 255.255.255.255. The Leader replies with `I_AM_LEADER(leader_id, leader_ip, leader_tcp_port, epoch, last_seq)`.

### Discovery Implemented
- [x] **Client discovers server**
- [ ] Server discovers servers
- [ ] Other

### Discovery Occurs
- [x] **When system starts**
- [x] **Whenever new component comes in**
- [ ] Other

**Explanation**:  
Discovery runs continuously in `_follower_discovery_loop()` every 1.0 second. New nodes discover the leader on startup. Rediscovery triggers when leader becomes unknown (e.g., after crash).

---

## 8. Voting / Leader Election

### Voting Algorithm
- [x] **Bully Algorithm**
- [ ] LeLann-Chang-Roberts Algorithm
- [ ] Hirschberg-Sinclair Algorithm

**Explanation**:  
Each node has a unique `node_id`. Higher ID = higher priority. When heartbeats stop for 3.5 seconds (`LEADER_TIMEOUT`), a node broadcasts `ELECTION(candidate_id, epoch+1)`. Higher-ID nodes reply `ANSWER` and start their own election. No `ANSWER` received within timeout → node declares itself Leader with `COORDINATOR` message.

### Group View Used
- [x] **Yes**
- [ ] No

**What group view is used for**:  
`CLUSTER_NODE_IDS = [2, 3, 10]` in `config.py` defines known node IDs for:
- Sending heartbeats to all cluster members
- Determining which nodes are "higher" in Bully election
- Broadcasting COORDINATOR messages after winning

### Node Identification
- [ ] IP addresses / IP addresses + ports
- [x] **UUIDs / Unique IDs**
- [ ] Other

**Explanation**:  
Nodes identified by integer `node_id` (comparable for Bully). UDP port derived as `NODE_UDP_BASE + node_id`. Orders use `uuid.uuid4()` for deduplication.

### Election Trigger
- [ ] When system starts
- [ ] When a new server joins
- [x] **When the leader fails**

**Explanation**:  
Election triggered in `_follower_discovery_loop()` when `now - leader.last_seen_ts > LEADER_TIMEOUT` (3.5 seconds). Only when Leader is perceived crashed (crash-stop failure model).

---

## 9. Reliable Ordered Multicast

### Type of Ordering
- [ ] FIFO Ordering
- [ ] Causal Ordering
- [x] **Total Ordering**

**Reason for Total Ordering**:  
Kitchen queue must be **identical on all screens**. When two waiters submit orders simultaneously, all devices must see them in the exact same sequence. A Leader-based sequencer ensures global total order.

### Reliability Mechanism
- [ ] Acknowledgements (ACKs)
- [x] **Negative Acknowledgments (NACKs)**
- [x] **Sequencing**
- [ ] Other

**Explanation**:
1. **Sequencing**: Leader assigns global `seq` numbers. Clients deliver only when `seq == expected_seq`
2. **Negative ACKs**: Gap detection (`received_seq > expected`) triggers `RESEND_REQUEST(from_seq)` for missing orders
3. **TCP**: Provides reliable per-connection delivery; sequence numbers enable catch-up after reconnect

---

## 10. Fault Tolerance

### Faults Tolerated
- [x] **Crash Faults** (Leader, Server, Client)
- [ ] Omission Faults
- [ ] Byzantine Faults

**Explanation**:  
System designed for **crash-stop failures**. Leader crash → followers detect and elect new Leader. Client crashes handled gracefully (TCP disconnect cleanup). New Leader reconstructs state from local history.

### Fault Detection

**Heartbeat Configuration**:
- **Direction**: Leader → All Followers
- **Message**: `LEADER_ALIVE(leader_id, epoch, last_seq)` via UDP
- **Frequency**: Every 1.0 second (`HEARTBEAT_INTERVAL`)
- **Redundancy**: Each heartbeat sent 2x (`HEARTBEAT_REDUNDANCY`)
- **Timeout**: 3.5 seconds (`LEADER_TIMEOUT`) without heartbeat = Leader crash

### Recovery Strategy

1. **Election**: Bully Algorithm elects highest-ID available node
2. **State Reconstruction**: New Leader uses local `history` (all delivered orders stored locally) + WAL recovery if enabled
3. **Catch-up**: Reconnecting clients send `RESEND_REQUEST(last_seq_seen)` to get missed orders
4. **Epoch**: Each election increments `epoch` to distinguish Leadership periods

---

## 11. Additional Features

### Write-Ahead Log (WAL)
- **Enabled**: `WAL_ENABLED = True`
- **File**: `cafeds_wal_node_{node_id}.jsonl`
- **Purpose**: Orders persisted to disk before broadcasting for crash durability
- **Recovery**: `_recover_from_wal()` restores history on startup

### Order UUID Deduplication
- Leader tracks `seen_order_uuids` set
- Duplicate orders (same `order_uuid`) are ignored to prevent double delivery

### Omission Tolerance
- Heartbeats sent multiple times per interval (`HEARTBEAT_REDUNDANCY = 2`)
- Reduces false leader-timeout elections due to UDP packet loss

---

## 12. Implementation Files

| Component | File | Description |
|-----------|------|-------------|
| Main Node Logic | `cafeds/node.py` | Node class with election, ordering, TCP/UDP handling |
| Configuration | `cafeds/config.py` | Network ports, timeouts, cluster node IDs |
| Protocol Messages | `cafeds/proto.py` | JSON message builders for all message types |
| TCP Server | `cafeds/tcp_server.py` | Leader's TCP server for client connections |
| TCP Client | `cafeds/tcp_client.py` | Follower's TCP client for Leader connection |
| UDP Utilities | `cafeds/udp_bus.py` | UDP socket utilities with broadcast support |
| Network Utils | `cafeds/net.py` | IP detection, broadcast address calculation |
| Entry Point | `run_node.py` | CLI entry point for starting nodes |

---
