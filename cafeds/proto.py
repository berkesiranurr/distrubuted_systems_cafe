import json
from typing import Any, Dict

def encode(msg: Dict[str, Any]) -> bytes:
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def decode(data: bytes) -> Dict[str, Any]:
    return json.loads(data.decode("utf-8", errors="replace"))

# ---------------- UDP discovery/heartbeat ----------------

def who_is_leader(sender_id: int, sender_tcp_port: int) -> Dict[str, Any]:
    return {"type": "WHO_IS_LEADER", "sender_id": sender_id, "sender_tcp_port": sender_tcp_port}

def i_am_leader(leader_id: int, leader_ip: str, leader_tcp_port: int, epoch: int, last_seq: int) -> Dict[str, Any]:
    return {
        "type": "I_AM_LEADER",
        "leader_id": leader_id,
        "leader_ip": leader_ip,
        "leader_tcp_port": leader_tcp_port,
        "epoch": epoch,
        "last_seq": last_seq,
    }

def leader_alive(leader_id: int, epoch: int, last_seq: int) -> Dict[str, Any]:
    return {"type": "LEADER_ALIVE", "leader_id": leader_id, "epoch": epoch, "last_seq": last_seq}

# ---------------- UDP election (Bully) ----------------

def election(candidate_id: int, epoch: int) -> Dict[str, Any]:
    return {"type": "ELECTION", "candidate_id": candidate_id, "epoch": epoch}

def answer(responder_id: int, epoch: int) -> Dict[str, Any]:
    return {"type": "ANSWER", "responder_id": responder_id, "epoch": epoch}

def coordinator(leader_id: int, leader_ip: str, leader_tcp_port: int, epoch: int, last_seq: int) -> Dict[str, Any]:
    return {
        "type": "COORDINATOR",
        "leader_id": leader_id,
        "leader_ip": leader_ip,
        "leader_tcp_port": leader_tcp_port,
        "epoch": epoch,
        "last_seq": last_seq,
    }

# ---------------- TCP orders ----------------

def new_order(sender_id: int, order_uuid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "NEW_ORDER", "sender_id": sender_id, "order_uuid": order_uuid, "payload": payload}

def order_msg(leader_id: int, epoch: int, seq: int, order_uuid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "ORDER", "leader_id": leader_id, "epoch": epoch, "seq": seq, "order_uuid": order_uuid, "payload": payload}

def resend_request(from_seq: int) -> Dict[str, Any]:
    return {"type": "RESEND_REQUEST", "from_seq": from_seq}
