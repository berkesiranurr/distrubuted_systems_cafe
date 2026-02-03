import os

os.environ["CAFEDS_SINGLE_PC"] = "1"

import time
import pytest
from cafeds.node import Node
from cafeds.config import CLUSTER_NODE_IDS


@pytest.fixture(autouse=True)
def setup_env():
    yield


def test_distributed_cafe():
    # 1. Start nodes
    # We use CLUSTER_NODE_IDS = [2, 3, 10]
    # Node 10 (highest ID) will naturally become leader in Bully algorithm
    nodes = {}

    # Leader (Node 10)
    nodes[10] = Node(node_id=10, role="leader", tcp_port=8010, ui="kitchen")
    # Kitchen (Node 3)
    nodes[3] = Node(node_id=3, role="follower", tcp_port=8003, ui="kitchen")
    # Waiter (Node 2)
    nodes[2] = Node(node_id=2, role="follower", tcp_port=8002, ui="kitchen")

    import threading

    threads = []
    try:
        # Run nodes in separate threads
        for node in nodes.values():
            t = threading.Thread(target=node.run, daemon=True)
            t.start()
            threads.append(t)

        # Wait for cluster to stabilize
        time.sleep(3)

        # Verify Node 10 is leader
        assert nodes[10].role == "leader"
        assert nodes[2].leader is not None
        assert nodes[2].leader.leader_id == 10

        # 2. Test Order Submission (Waiter -> Leader -> Kitchen)
        test_order = {"text": "Espresso"}
        print(f"\nSubmitting order: {test_order}")
        nodes[2].submit_order(test_order)

        # Wait for delivery with retry/loop
        success = False
        for _ in range(10):
            time.sleep(1)
            kitchen_orders = [
                o["payload"]["text"]
                for o in nodes[3].history.values()
                if "payload" in o
            ]
            if "Espresso" in kitchen_orders:
                success = True
                break
            print(f"Waiting for Espresso... current orders: {kitchen_orders}")

        assert (
            success
        ), f"Kitchen didn't receive Espresso. Node 3 history: {nodes[3].history}"

        # 3. Test Leader Election (Kill Node 10)
        nodes[10].stop()
        time.sleep(1)  # Grace period

        # Wait for election (LEADER_TIMEOUT is 3.5s + TCP timeouts)
        time.sleep(10)

        # New leader should be Node 3 (highest among [2, 3])
        assert nodes[3].role == "leader"
        assert nodes[2].leader.leader_id == 3

        # Verify system still works with new leader
        nodes[2].submit_order({"text": "Latte"})
        time.sleep(2)

        new_kitchen_orders = [
            o["payload"]["text"] for o in nodes[3].history.values() if "payload" in o
        ]
        assert "Latte" in new_kitchen_orders

    finally:
        for node in nodes.values():
            node.stop()
        # Clean up WAL files
        for nid in CLUSTER_NODE_IDS:
            wal = f"cafeds_wal_node_{nid}.jsonl"
            if os.path.exists(wal):
                os.remove(wal)
