import threading
import time
import socket
import uuid
import os
import json
from dataclasses import dataclass, field
from typing import Optional, Set, Dict, Any

from .config import (
    DISCOVERY_INTERVAL,
    HEARTBEAT_INTERVAL,
    LEADER_TIMEOUT,
    LOG_PREFIX,
    DISCOVERY_PORT,
    NODE_UDP_BASE,
    ELECTION_ANSWER_TIMEOUT,
    COORDINATOR_TIMEOUT,
    WAL_ENABLED,
    WAL_FILE,
    HEARTBEAT_REDUNDANCY,
    PEER_EXPIRY,
)
from .udp_bus import make_udp_socket, send_udp, recv_udp
from .proto import (
    encode,
    decode,
    who_is_leader,
    i_am_leader,
    leader_alive,
    election,
    answer,
    coordinator,
    new_order,
    order_msg,
    resend_request,
)
from .tcp_server import TCPServer, ClientConn
from .tcp_client import TCPClient
from .net import primary_ip, local_ip_for_peer, discovery_targets


# --------------- Dynamic Peer Registry ---------------


@dataclass
class PeerInfo:
    """Represents a dynamically discovered peer node."""

    node_id: int
    ip: str
    udp_port: int
    tcp_port: int
    last_seen: float = field(default_factory=time.time)


@dataclass
class LeaderInfo:
    leader_id: int
    leader_ip: str
    leader_tcp_port: int
    epoch: int
    last_seq: int
    last_seen_ts: float


class Node:
    def __init__(self, node_id: int, role: str, tcp_port: int, ui: str):
        self.node_id = node_id
        self.role = role
        self.tcp_port = tcp_port
        self.ui = ui

        # UDP sockets
        self.node_udp_port = NODE_UDP_BASE + node_id
        try:
            # Disable reuse_addr to prevent local duplicates (OS will block bind)
            self.udp_node = make_udp_socket(self.node_udp_port, reuse_addr=False)
        except OSError:
            print(f"CRITICAL: Port {self.node_udp_port} is already in use. Is node {node_id} running?")
            raise

        self.udp_disc: Optional[socket.socket] = None
        if role == "leader":
            self.udp_disc = make_udp_socket(DISCOVERY_PORT)

        self.stop_event = threading.Event()

        # Sequencer/log state (EVERYONE keeps history)
        self.epoch = 1
        self.last_seq = 0
        self.history: Dict[int, Dict[str, Any]] = {}
        self.history_lock = threading.Lock()

        # Follower leader info
        self.leader: Optional[LeaderInfo] = None

        # TCP
        self.tcp_server: Optional[TCPServer] = None
        self.tcp_client: Optional[TCPClient] = None
        self.tcp_connected = False
        self.tcp_lock = threading.Lock()

        # Total-order delivery (follower)
        self.expected_seq = 1
        self.buffer: Dict[int, Dict[str, Any]] = {}
        self.delivered_seqs: Set[int] = set()
        self.delivery_lock = threading.Lock()
        self.last_resend_ts = 0.0

        # election state
        self.in_election = False
        self.in_election_since = 0.0
        self.answer_event = threading.Event()
        # UUID deduplication for orders (prevents duplicate processing)
        self.seen_order_uuids: Set[str] = set()
        self.seen_uuids_lock = threading.Lock()

        # WAL (Write-Ahead Log) for persistence
        self.wal_file = WAL_FILE.format(node_id=node_id) if WAL_ENABLED else None
        if self.wal_file:
            self._recover_from_wal()

        # Threads
        self.threads: Set[threading.Thread] = set()

        self.coordinator_event = threading.Event()
        self.coordinator_msg: Optional[Dict[str, Any]] = None
        self.election_lock = threading.Lock()

        # leader heartbeat start guard
        self._heartbeat_started = False

        # ---- Dynamic Peer Registry ----
        self.peers: Dict[int, PeerInfo] = {}
        self.peers_lock = threading.Lock()

    def log(self, msg: str) -> None:
        print(
            f"{LOG_PREFIX} [id={self.node_id} role={self.role} udp_node={self.node_udp_port}] {msg}",
            flush=True,
        )

    # ---------------- Dynamic Peer Registry ----------------

    def _register_peer(
        self, node_id: int, ip: str, tcp_port: int = 0
    ) -> None:
        """Register or update a dynamically discovered peer."""
        if node_id == self.node_id:
            # DUPLICATE ID DETECTION: another node claims OUR id from a different IP
            my_ip = primary_ip()
            if ip not in (my_ip, "127.0.0.1", "0.0.0.0") and my_ip != "127.0.0.1":
                self.log(
                    f"⚠ DUPLICATE NODE ID DETECTED! Another node with id={node_id} "
                    f"is running at {ip}. This WILL cause cluster instability. "
                    f"Please use a unique --id for each node."
                )
            return  # don't register self
        udp_port = NODE_UDP_BASE + node_id
        with self.peers_lock:
            existing = self.peers.get(node_id)
            if existing:
                existing.ip = ip
                existing.udp_port = udp_port
                if tcp_port:
                    existing.tcp_port = tcp_port
                existing.last_seen = time.time()
            else:
                self.peers[node_id] = PeerInfo(
                    node_id=node_id,
                    ip=ip,
                    udp_port=udp_port,
                    tcp_port=tcp_port,
                    last_seen=time.time(),
                )
                self.log(f"Peer discovered: id={node_id} ip={ip} udp={udp_port} tcp={tcp_port}")

    def _get_peer_ids(self) -> list:
        """Return list of known peer IDs (excluding self)."""
        with self.peers_lock:
            return [pid for pid in self.peers if pid != self.node_id]

    def _prune_peers(self) -> None:
        """Remove peers not seen for PEER_EXPIRY seconds."""
        now = time.time()
        with self.peers_lock:
            expired = [
                pid
                for pid, p in self.peers.items()
                if (now - p.last_seen) > PEER_EXPIRY
            ]
            for pid in expired:
                del self.peers[pid]
                # (logging removed to avoid spam)

    # ---------------- WAL (Write-Ahead Log) ----------------

    def _append_to_wal(self, order: Dict[str, Any]) -> None:
        """Persist order to disk before acknowledging (crash durability)."""
        if not self.wal_file:
            return
        try:
            with open(self.wal_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(order, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())  # Ensure durably written to disk
        except Exception as e:
            self.log(f"WAL write error: {e}")

    def _recover_from_wal(self) -> None:
        """Recover order history from WAL on startup."""
        if not self.wal_file or not os.path.exists(self.wal_file):
            return
        recovered = 0
        try:
            with open(self.wal_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        order = json.loads(line)
                        seq = int(order.get("seq", 0))
                        order_uuid = str(order.get("order_uuid", ""))
                        if seq > 0:
                            self.history[seq] = order
                            self.last_seq = max(self.last_seq, seq)
                            if order_uuid:
                                self.seen_order_uuids.add(order_uuid)
                            recovered += 1
                    except Exception:
                        pass
                self.log(f"WAL recovered {recovered} orders, last_seq={self.last_seq}")
                # Update the next expected sequence number so that new orders can be delivered.
                with self.delivery_lock:
                    self.expected_seq = self.last_seq + 1
                    self.delivered_seqs.update(range(1, self.expected_seq))
        except Exception as e:
            self.log(f"WAL recovery error: {e}")

    # ---------------- RUN ----------------

    def run(self) -> None:
        # ---- Duplicate ID check: probe the network before starting ----
        if not self._check_id_available():
            return  # ID already in use, refuse to start

        # ---- Existing Leader Check: if we are leader, check if another leader exists ----
        if self.role == "leader":
            if self._check_existing_leader():
                self.log("⚠ WARNING: Another LEADER is already active. Demoting to FOLLOWER.")
                self.role = "follower"
                # If we had a discovery socket for leader role, close it
                if self.udp_disc:
                    try:
                        self.udp_disc.close()
                    except Exception:
                        pass
                    self.udp_disc = None

        t1 = threading.Thread(target=self._udp_node_listener, daemon=True)
        t1.start()
        self.threads.add(t1)

        if self.udp_disc is not None:
            t2 = threading.Thread(target=self._udp_disc_listener, daemon=True)
            t2.start()
            self.threads.add(t2)

        if self.role == "leader":
            self._start_tcp_leader()
            self._start_leader_heartbeat_thread()
        else:
            self._start_tcp_follower()
            if self.ui == "waiter":
                tw = threading.Thread(target=self._stdin_order_loop, daemon=True)
                tw.start()
                self.threads.add(tw)

        tf = threading.Thread(target=self._follower_discovery_loop, daemon=True)
        tf.start()
        self.threads.add(tf)

        self.log("Node is running.")
        while not self.stop_event.is_set():
            time.sleep(0.5)

    def _check_id_available(self) -> bool:
        """Probe the network to see if our node ID is already in use.

        Sends an ID_CHECK message and waits for ID_TAKEN replies.
        Returns True if the ID is available, False if taken.
        """
        token = str(uuid.uuid4())
        probe = encode({
            "type": "ID_CHECK",
            "node_id": self.node_id,
            "token": token,
        })

        # Send probe to all discovery targets on our own UDP port
        for ip in discovery_targets():
            try:
                send_udp(self.udp_node, probe, ip, self.node_udp_port)
            except Exception:
                pass

        # Listen for ID_TAKEN responses (1 second window is enough for LAN)
        self.log(f"Checking if node ID {self.node_id} is available on the network...")
        old_timeout = self.udp_node.gettimeout()
        self.udp_node.settimeout(0.3)
        deadline = time.time() + 1.0

        while time.time() < deadline:
            try:
                data, (src_ip, _) = self.udp_node.recvfrom(4096)
                msg = decode(data)
                if (
                    msg.get("type") == "ID_TAKEN"
                    and msg.get("token") == token
                    and msg.get("node_id") == self.node_id
                ):
                    self.log(
                        f"\u274c ERROR: Node ID {self.node_id} is already in use "
                        f"by {src_ip}. Cannot start. "
                        f"Please choose a different --id."
                    )
                    self.udp_node.settimeout(old_timeout)
                    return False
            except socket.timeout:
                continue
            except Exception:
                continue

        self.udp_node.settimeout(old_timeout)
        self.log(f"Node ID {self.node_id} is available. Proceeding.")
        return True

    def _check_existing_leader(self) -> bool:
        """Probe the network to see if a leader already exists.

        Returns True if a leader is found, False otherwise.
        """
        # We need a temporary socket for this probe since we might not have udp_disc yet
        # or we want to keep it separate from the main listener.
        # Actually, we can use self.udp_node for sending/receiving.

        token = str(uuid.uuid4())
        probe = encode(who_is_leader(self.node_id, self.tcp_port))

        # Send probe to all discovery targets on DISCOVERY_PORT
        for ip in discovery_targets():
            try:
                send_udp(self.udp_node, probe, ip, DISCOVERY_PORT)
            except Exception:
                pass

        # Listen for I_AM_LEADER responses (1 second window)
        self.log("Checking for existing leader...")
        old_timeout = self.udp_node.gettimeout()
        self.udp_node.settimeout(0.3)
        deadline = time.time() + 1.0

        found_leader = False
        while time.time() < deadline:
            try:
                data, (src_ip, _) = self.udp_node.recvfrom(4096)
                msg = decode(data)
                if msg.get("type") == "I_AM_LEADER":
                    lid = msg.get("leader_id")
                    lip = msg.get("leader_ip")
                    self.log(f"DEBUG: I_AM_LEADER received from {lid} @ {src_ip} (claim ip={lip}). I am {self.node_id}.")
                    self.log(f"Found existing leader: {lid} @ {src_ip}")
                    found_leader = True
                    break
            except socket.timeout:
                continue
            except Exception:
                continue

        self.udp_node.settimeout(old_timeout)
        return found_leader

    # ---------------- UDP HELPERS ----------------

    def _port_of(self, node_id: int) -> int:
        return NODE_UDP_BASE + node_id

    def _send_to_node(self, target_id: int, msg: Dict[str, Any]) -> None:
        """Send a UDP message to a specific node.

        If we know the peer's IP from the registry, send directly.
        Otherwise fall back to broadcast so that unknown peers can still be reached.
        """
        payload = encode(msg)
        port = self._port_of(target_id)

        with self.peers_lock:
            peer = self.peers.get(target_id)

        if peer and not peer.ip.startswith("0."):
            # Send directly to known peer IP
            try:
                send_udp(self.udp_node, payload, peer.ip, port)
            except Exception:
                pass
            return

        # Fallback: broadcast to all discovery targets
        for ip in discovery_targets():
            try:
                send_udp(self.udp_node, payload, ip, port)
            except Exception:
                pass

    def _broadcast_to_all_peers(self, msg: Dict[str, Any]) -> None:
        """Send a UDP message to ALL known peers (used for heartbeats, coordinator)."""
        payload = encode(msg)
        peer_ids = self._get_peer_ids()
        for pid in peer_ids:
            port = self._port_of(pid)
            with self.peers_lock:
                peer = self.peers.get(pid)
            if peer:
                try:
                    send_udp(self.udp_node, payload, peer.ip, port)
                except Exception:
                    pass

    def _broadcast_to_discovery(self, msg: Dict[str, Any], port: int) -> None:
        """Broadcast a message via discovery targets (for reaching unknown nodes)."""
        payload = encode(msg)
        for ip in discovery_targets():
            try:
                send_udp(self.udp_node, payload, ip, port)
            except Exception:
                pass

    def _safe_start_election(self, reason: str = "") -> None:
        if self.role == "leader":
            return
        now = time.time()
        with self.election_lock:
            # single-flight: don't start another election if one started recently
            if self.in_election and (now - self.in_election_since) < 2.0:
                return
            self.in_election = True
            self.in_election_since = now

        if reason:
            self.log(f"{reason} -> starting election")
        threading.Thread(target=self._bully_election, daemon=True).start()

    def _is_better_leader(self, new: LeaderInfo) -> bool:
        cur = self.leader
        if cur is None:
            return True

        # Prefer higher epoch
        if new.epoch != cur.epoch:
            return new.epoch > cur.epoch

        # Prefer higher leader_id (bully style)
        if new.leader_id != cur.leader_id:
            return new.leader_id > cur.leader_id

        # Same leader: prefer non-loopback over loopback
        cur_loop = cur.leader_ip.startswith("127.")
        new_loop = new.leader_ip.startswith("127.")
        if cur_loop and not new_loop:
            return True
        if not cur_loop and new_loop:
            return False

        # Prefer larger last_seq if everything else equal
        if new.last_seq != cur.last_seq:
            return new.last_seq > cur.last_seq

        return False

    # ---------------- ORDER PROCESSING ----------------

    def _process_order(self, msg: Dict[str, Any]) -> None:
        if not msg:
            return
        try:
            seq = int(msg.get("seq", -1))
        except Exception:
            return
        if seq <= 0:
            return

        # keep history for leader handover
        with self.history_lock:
            self.history[seq] = msg
            self.last_seq = max(self.last_seq, seq)

        with self.delivery_lock:
            # dedup
            if seq in self.delivered_seqs or seq < self.expected_seq:
                self.delivered_seqs.add(seq)
                return

            # gap => buffer + resend request
            if seq > self.expected_seq:
                self.buffer[seq] = msg
                now = time.time()
                if (
                    self.tcp_client
                    and self.tcp_connected
                    and (now - self.last_resend_ts) >= 0.5
                ):
                    self.last_resend_ts = now
                    try:
                        req = resend_request(self.expected_seq)
                    except Exception:
                        req = {
                            "type": "RESEND_REQUEST",
                            "sender_id": self.node_id,
                            "from_seq": self.expected_seq,
                        }
                    try:
                        self.tcp_client.send(req)
                        self.log(f"RESEND_REQUEST sent from_seq={self.expected_seq}")
                    except Exception:
                        pass
                return

            # seq == expected => deliver and flush
            self._deliver(msg)
            self._append_to_wal(msg)  # persist to WAL on delivery
            self.delivered_seqs.add(seq)
            self.expected_seq += 1

            while self.expected_seq in self.buffer:
                m2 = self.buffer.pop(self.expected_seq)
                s2 = self.expected_seq
                if s2 in self.delivered_seqs:
                    self.expected_seq += 1
                    continue
                self._deliver(m2)
                self._append_to_wal(m2)  # persist to WAL on delivery
                self.delivered_seqs.add(s2)
                self.expected_seq += 1

    # ---------------- UDP LISTENERS ----------------

    def _udp_node_listener(self) -> None:
        self.log("UDP node listener started.")
        while not self.stop_event.is_set():
            try:
                data, (src_ip, src_port) = recv_udp(self.udp_node)
                msg = decode(data)
                mtype = msg.get("type")

                # --- Register peer from any incoming message ---
                sender_id = msg.get("sender_id") or msg.get("leader_id") or msg.get("candidate_id") or msg.get("responder_id")
                sender_tcp = msg.get("sender_tcp_port") or msg.get("leader_tcp_port") or msg.get("candidate_tcp_port") or msg.get("responder_tcp_port") or 0
                if sender_id is not None:
                    try:
                        self._register_peer(int(sender_id), src_ip, int(sender_tcp))
                    except (ValueError, TypeError):
                        pass

                if mtype == "I_AM_LEADER" and self.role == "follower":
                    new = LeaderInfo(
                        leader_id=int(msg.get("leader_id", -1)),
                        leader_ip=src_ip,  # use real sender IP (multi-PC safe)
                        leader_tcp_port=int(msg.get("leader_tcp_port", 0)),
                        epoch=int(msg.get("epoch", 1)),
                        last_seq=int(msg.get("last_seq", 0)),
                        last_seen_ts=time.time(),
                    )

                    if self._is_better_leader(new):
                        # Reset TCP so we reconnect to the correct leader
                        if self.leader and new.leader_id != self.leader.leader_id:
                            self._close_tcp_client()
                        self.leader = new
                        self.epoch = max(self.epoch, new.epoch)
                        self.log(
                            f"Leader discovered: {new.leader_id} @ {new.leader_ip}:{new.leader_tcp_port} (epoch={new.epoch})"
                        )

                elif mtype == "LEADER_ALIVE" and self.role == "follower":
                    lid = int(msg.get("leader_id", -1))
                    e = int(msg.get("epoch", 1))
                    ls = int(msg.get("last_seq", 0))
                    ltcp = int(msg.get("leader_tcp_port", 0))

                    # If leader unknown, accept heartbeat as "someone exists"
                    if self.leader is None:
                        self.leader = LeaderInfo(
                            leader_id=lid,
                            leader_ip=src_ip,
                            leader_tcp_port=ltcp,
                            epoch=e,
                            last_seq=ls,
                            last_seen_ts=time.time(),
                        )
                    else:
                        # only refresh if same leader or higher epoch
                        if lid == self.leader.leader_id or e > self.leader.epoch:
                            self.leader.last_seen_ts = time.time()
                            self.leader.epoch = max(self.leader.epoch, e)
                            self.leader.last_seq = max(self.leader.last_seq, ls)
                            # Update leader IP to currently seen src_ip
                            # (handles IP changes / reconnects)
                            self.leader.leader_ip = src_ip
                            if ltcp:
                                self.leader.leader_tcp_port = ltcp
                    self.epoch = max(self.epoch, e)

                    # Register sibling peers from leader's cluster list
                    # This allows followers to know about each other for elections
                    cluster = msg.get("cluster", [])
                    for peer_entry in cluster:
                        try:
                            pid = int(peer_entry.get("id", 0))
                            pip = str(peer_entry.get("ip", ""))
                            ptcp = int(peer_entry.get("tcp", 0))
                            if pid and pip:
                                self._register_peer(pid, pip, ptcp)
                        except (ValueError, TypeError, AttributeError):
                            pass

                if mtype == "ELECTION":
                    cand = int(msg.get("candidate_id", -1))
                    e = int(msg.get("epoch", 1))
                    if self.node_id > cand:
                        try:
                            send_udp(
                                self.udp_node,
                                encode(answer(self.node_id, max(self.epoch, e), self.tcp_port)),
                                src_ip,
                                src_port,
                            )
                        except Exception:
                            pass
                        # higher node should also start its own election
                        self._safe_start_election("Received ELECTION from lower node")

                elif mtype == "ID_CHECK":
                    # Another node is probing to see if our ID is taken
                    check_id = msg.get("node_id")
                    check_token = msg.get("token")
                    if check_id == self.node_id and check_token:
                        reply = encode({
                            "type": "ID_TAKEN",
                            "node_id": self.node_id,
                            "token": check_token,
                        })
                        try:
                            send_udp(self.udp_node, reply, src_ip, src_port)
                        except Exception:
                            pass

                elif mtype == "ANSWER":
                    self.answer_event.set()

                elif mtype == "COORDINATOR":
                    # save coordinator msg for election thread
                    self.coordinator_msg = msg
                    self.coordinator_event.set()

                    lead_id = int(msg.get("leader_id", -1))
                    e = int(msg.get("epoch", 1))

                    # If I'm leader but see a legitimate higher coordinator, step down.
                    # Bully rule: higher epoch wins; at same epoch, higher ID wins.
                    should_step_down = (
                        self.role == "leader"
                        and lead_id != self.node_id
                        and (
                            e > self.epoch
                            or (e == self.epoch and lead_id > self.node_id)
                        )
                    )
                    if should_step_down:
                        self.log(f"Stepping down: coordinator {lead_id} epoch={e}")
                        self._demote_to_follower(
                            LeaderInfo(
                                leader_id=lead_id,
                                leader_ip=src_ip,  # real sender IP
                                leader_tcp_port=int(msg.get("leader_tcp_port", 0)),
                                epoch=e,
                                last_seq=int(msg.get("last_seq", 0)),
                                last_seen_ts=time.time(),
                            )
                        )

                    # As follower receiving COORDINATOR: reset TCP to reconnect to new leader
                    if self.role == "follower":
                        new_leader = LeaderInfo(
                            leader_id=lead_id,
                            leader_ip=src_ip,
                            leader_tcp_port=int(msg.get("leader_tcp_port", 0)),
                            epoch=e,
                            last_seq=int(msg.get("last_seq", 0)),
                            last_seen_ts=time.time(),
                        )
                        if self.leader is None or lead_id != self.leader.leader_id:
                            self._close_tcp_client()
                        self.leader = new_leader
                        self.epoch = max(self.epoch, e)

            except socket.timeout:
                continue
            except OSError:
                if self.stop_event.is_set():
                    break
            except Exception as e:
                self.log(f"UDP node listener error: {e}")

    def _udp_disc_listener(self) -> None:
        assert self.udp_disc is not None
        self.log("UDP discovery listener started.")
        while not self.stop_event.is_set():
            try:
                data, (src_ip, src_port) = recv_udp(self.udp_disc)
                msg = decode(data)
                if msg.get("type") == "WHO_IS_LEADER" and self.role == "leader":
                    # Register the querying peer
                    sid = msg.get("sender_id")
                    stcp = msg.get("sender_tcp_port", 0)
                    if sid is not None:
                        try:
                            self._register_peer(int(sid), src_ip, int(stcp))
                        except (ValueError, TypeError):
                            pass

                    reply = i_am_leader(
                        leader_id=self.node_id,
                        leader_ip=local_ip_for_peer(src_ip),
                        leader_tcp_port=self.tcp_port,
                        epoch=self.epoch,
                        last_seq=self.last_seq,
                    )
                    send_udp(self.udp_disc, encode(reply), src_ip, src_port)
            except socket.timeout:
                continue
            except OSError:
                if self.stop_event.is_set():
                    break
            except Exception:
                pass

    # ---------------- FOLLOWER DISCOVERY + TIMEOUT ----------------

    def _follower_discovery_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.role != "follower":
                time.sleep(0.5)
                continue

            now = time.time()

            # leader timeout?
            if self.leader and (now - self.leader.last_seen_ts) > LEADER_TIMEOUT:
                self._close_tcp_client()
                self.leader = None
                self._safe_start_election("Leader timeout")

            # If leader unknown: ask via discovery port
            if self.leader is None and not self.in_election:
                q = who_is_leader(self.node_id, self.tcp_port)
                payload = encode(q)
                for ip in discovery_targets():
                    try:
                        send_udp(self.udp_node, payload, ip, DISCOVERY_PORT)
                    except Exception:
                        pass

            # If leader known but TCP not connected: connect
            if self.leader is not None:
                self._ensure_tcp_connected()

            # Periodic peer pruning
            self._prune_peers()

            time.sleep(DISCOVERY_INTERVAL)

    # ---------------- TCP LEADER ----------------

    def _start_tcp_leader(self) -> None:
        def on_msg(conn: ClientConn, msg: Dict[str, Any]) -> None:
            mtype = msg.get("type")

            if mtype == "NEW_ORDER":
                order_uuid = str(msg.get("order_uuid", ""))
                # UUID Deduplication: prevent duplicate order processing
                with self.seen_uuids_lock:
                    if order_uuid and order_uuid in self.seen_order_uuids:
                        self.log(f"Duplicate order ignored: {order_uuid}")
                        return
                    if order_uuid:
                        self.seen_order_uuids.add(order_uuid)

                with self.history_lock:
                    self.last_seq = max(
                        self.last_seq, max(self.history.keys(), default=0)
                    )
                    self.last_seq += 1
                    seq = self.last_seq
                    om = order_msg(
                        leader_id=self.node_id,
                        epoch=self.epoch,
                        seq=seq,
                        order_uuid=order_uuid,
                        payload=dict(msg.get("payload", {})),
                    )
                    om["sender_id"] = msg.get("sender_id")
                    self.history[seq] = om

                # WAL: persist to disk BEFORE broadcasting (crash durability)
                self._append_to_wal(om)

                self._process_order(om)
                assert self.tcp_server is not None
                self.tcp_server.broadcast(om)

            elif mtype == "RESEND_REQUEST":
                from_seq = int(msg.get("from_seq", 1))
                with self.history_lock:
                    hi = max(self.history.keys(), default=0)
                    for s in range(from_seq, hi + 1):
                        if s in self.history:
                            conn.send(self.history[s])

        self.tcp_server = TCPServer(
            "0.0.0.0", self.tcp_port, on_msg=on_msg, on_log=self.log
        )
        self.tcp_server.start()

    def _start_leader_heartbeat_thread(self) -> None:
        if self._heartbeat_started:
            return
        self._heartbeat_started = True
        t = threading.Thread(target=self._leader_heartbeat_loop, daemon=True)
        t.start()
        self.threads.add(t)

    def _leader_heartbeat_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.role != "leader":
                time.sleep(0.5)
                continue

            with self.history_lock:
                self.last_seq = max(self.last_seq, max(self.history.keys(), default=0))

            # Build cluster peer list for heartbeat so followers learn about each other
            cluster_list = []
            with self.peers_lock:
                for pid, pinfo in self.peers.items():
                    cluster_list.append({"id": pid, "ip": pinfo.ip, "tcp": pinfo.tcp_port})

            hb = leader_alive(self.node_id, self.epoch, self.last_seq, self.tcp_port, cluster=cluster_list)

            # Omission Fault Tolerance: send heartbeat multiple times
            # This reduces the chance of election due to dropped UDP packets
            for _ in range(HEARTBEAT_REDUNDANCY):
                # Send to all known peers directly
                self._broadcast_to_all_peers(hb)

            time.sleep(HEARTBEAT_INTERVAL)

    # ---------------- TCP FOLLOWER ----------------

    def _start_tcp_follower(self) -> None:
        def on_msg(msg: Dict[str, Any]) -> None:
            if msg.get("type") == "ORDER":
                self._process_order(msg)

        def on_log(s: str) -> None:
            if "disconnected" in s.lower() or "stopped" in s.lower():
                with self.tcp_lock:
                    self.tcp_connected = False
            self.log(s)

        self.tcp_client = TCPClient(on_msg=on_msg, on_log=on_log)

    def _ensure_tcp_connected(self) -> None:
        if not self.leader or not self.tcp_client:
            return
        with self.tcp_lock:
            if self.tcp_connected:
                return

        host = self.leader.leader_ip
        port = self.leader.leader_tcp_port
        if port == 0:
            return

        ok = self.tcp_client.connect(host, port)
        with self.tcp_lock:
            self.tcp_connected = ok

        if ok:
            try:
                self.tcp_client.send(resend_request(self.expected_seq))
            except Exception:
                pass

    def _close_tcp_client(self) -> None:
        with self.tcp_lock:
            self.tcp_connected = False
        if self.tcp_client:
            self.tcp_client.close()

    # ---------------- DELIVERY ----------------

    def _deliver(self, msg: Dict[str, Any]) -> None:
        payload = msg.get("payload", {})
        text = payload.get("text", str(payload))
        sender = msg.get("sender_id", "unknown")
        self.log(f"DELIVER seq={msg.get('seq')} [from={sender}] | {text}")

    # ---------------- WAITER INPUT ----------------

    def _stdin_order_loop(self) -> None:
        self.log("WAITER: type order and press Enter")
        while not self.stop_event.is_set():
            try:
                line = input()
            except Exception:
                break
            line = (line or "").strip()
            if not line:
                continue
            self.submit_order({"text": line})

    def submit_order(self, payload: Dict[str, Any]) -> None:
        # If I'm leader, accept local orders (demo-friendly)
        if self.role == "leader":
            oid = str(uuid.uuid4())
            with self.history_lock:
                self.last_seq = max(self.last_seq, max(self.history.keys(), default=0))
                self.last_seq += 1
                seq = self.last_seq
                om = order_msg(self.node_id, self.epoch, seq, oid, payload)
                om["sender_id"] = self.node_id
                self.history[seq] = om
            self.log(f"LOCAL_ORDER -> seq={seq} (broadcast ORDER)")
            self._process_order(om)
            if self.tcp_server:
                self.tcp_server.broadcast(om)
            return

        if not self.tcp_client:
            self.log("Cannot submit order: tcp_client missing")
            return
        with self.tcp_lock:
            if not self.tcp_connected:
                self.log("Cannot submit order: not connected to leader yet")
                return

        oid = str(uuid.uuid4())
        self.tcp_client.send(new_order(self.node_id, oid, payload))
        self.log(f"Sent NEW_ORDER uuid={oid}")

    # ---------------- BULLY ELECTION ----------------

    def _bully_election(self) -> None:
        # IMPORTANT: no extra guard here (starter already guarded)
        self.answer_event.clear()
        self.coordinator_event.clear()
        self.coordinator_msg = None

        proposed_epoch = self.epoch + 1
        # Dynamic: get higher-ID peers from registry
        higher = [pid for pid in self._get_peer_ids() if pid > self.node_id]
        self.log(f"Election started. higher={higher}")

        for nid in higher:
            try:
                self._send_to_node(nid, election(self.node_id, proposed_epoch, self.tcp_port))
            except Exception:
                pass

        # If we don't know any higher peers, we are the highest known — promote directly
        if not higher:
            self.log("No known higher peers; promoting self.")

        got_answer = self.answer_event.wait(ELECTION_ANSWER_TIMEOUT)

        if not got_answer:
            self.log("No ANSWER -> I become LEADER")
            self._promote_to_leader(new_epoch=proposed_epoch)
            with self.election_lock:
                self.in_election = False
                self.in_election_since = 0.0
            return

        self.log("Got ANSWER -> waiting for COORDINATOR")
        got_coord = self.coordinator_event.wait(COORDINATOR_TIMEOUT)

        if not got_coord or not self.coordinator_msg:
            self.log("Coordinator timeout -> retry election")
            with self.election_lock:
                self.in_election = False
                self.in_election_since = 0.0
            return

        msg = self.coordinator_msg
        lead = LeaderInfo(
            leader_id=int(msg["leader_id"]),
            leader_ip=str(msg.get("leader_ip", "")) or "127.0.0.1",
            leader_tcp_port=int(msg.get("leader_tcp_port", 0)),
            epoch=int(msg.get("epoch", proposed_epoch)),
            last_seq=int(msg.get("last_seq", 0)),
            last_seen_ts=time.time(),
        )
        self.epoch = max(self.epoch, lead.epoch)
        self.leader = lead
        self.log(
            f"COORDINATOR is {lead.leader_id} @ {lead.leader_ip}:{lead.leader_tcp_port} epoch={lead.epoch}"
        )

        with self.election_lock:
            self.in_election = False
            self.in_election_since = 0.0

        self._ensure_tcp_connected()

    def _promote_to_leader(self, new_epoch: int) -> None:
        self._close_tcp_client()
        self.role = "leader"
        self.leader = None
        self.epoch = max(self.epoch + 1, new_epoch)

        if self.udp_disc is None:
            try:
                self.udp_disc = make_udp_socket(DISCOVERY_PORT)
                t = threading.Thread(target=self._udp_disc_listener, daemon=True)
                t.start()
                self.threads.add(t)
            except Exception as e:
                self.log(f"Failed to bind discovery port: {e}")

        if self.tcp_server is None:
            self._start_tcp_leader()

        # start periodic heartbeat AFTER promotion
        self._start_leader_heartbeat_thread()

        with self.history_lock:
            self.last_seq = max(self.last_seq, max(self.history.keys(), default=0))
            # Update the next expected sequence number so that new orders can be delivered.
            with self.delivery_lock:
                self.expected_seq = max(self.expected_seq, self.last_seq + 1)
                self.delivered_seqs.update(range(1, self.expected_seq))

        coord_msg = coordinator(
            self.node_id, primary_ip(), self.tcp_port, self.epoch, self.last_seq
        )

        # Send COORDINATOR to all known peers
        self._broadcast_to_all_peers(coord_msg)

        self.log(f"Announced COORDINATOR epoch={self.epoch} last_seq={self.last_seq}")

    def _demote_to_follower(self, new_leader: LeaderInfo) -> None:
        if self.role != "leader":
            self.leader = new_leader
            return

        if self.tcp_server:
            self.tcp_server.stop()
            self.tcp_server = None

        # Release the discovery port so the new leader can bind it
        if self.udp_disc:
            try:
                self.udp_disc.close()
            except Exception:
                pass
            self.udp_disc = None

        self.role = "follower"
        self.leader = new_leader
        self._start_tcp_follower()
        self.log("Demoted to follower.")

    # ---------------- STOP ----------------

    def stop(self) -> None:
        self.stop_event.set()
        try:
            self.udp_node.close()
        except Exception:
            pass
        try:
            if self.udp_disc:
                self.udp_disc.close()
        except Exception:
            pass
        if self.tcp_client:
            self.tcp_client.close()
        if self.tcp_server:
            self.tcp_server.stop()
