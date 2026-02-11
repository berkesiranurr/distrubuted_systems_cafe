import os

os.environ["CAFEDS_SINGLE_PC"] = "1"

import time
import pytest
from cafeds.node import Node


@pytest.fixture(autouse=True)
def setup_env():
    yield


def test_distributed_cafe():
    # 1. Start nodes
    # Node IDs can be any unique integers — dynamic discovery finds them
    # Node 10 (highest ID) will naturally become leader in Bully algorithm
    node_ids = [2, 3, 10]
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
        # (Startup probe takes 1s + discovery takes ~1s + margin)
        time.sleep(8)

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
        for nid in node_ids:
            wal = f"cafeds_wal_node_{nid}.jsonl"
            if os.path.exists(wal):
                os.remove(wal)


def test_duplicate_leader_starts_as_follower():
    """
    Verify that if a node starts with role='leader' but a leader already exists,
    it automatically demotes to 'follower'.
    """
    # 1. Start a legitimate leader (Node 10)
    leader = Node(node_id=10, role="leader", tcp_port=8010, ui="kitchen")
    # Start a late comer that THINKS it's a leader (Node 9)
    # It has lower ID, so it should yield to 10 anyway, but we want to ensure
    # it starts as a follower immediately upon detecting 10.
    late_comer = Node(node_id=9, role="leader", tcp_port=8009, ui="kitchen")

    nodes = [leader, late_comer]
    threads = []
    
    try:
        import threading
        # Run leader first
        t1 = threading.Thread(target=leader.run, daemon=True)
        t1.start()
        threads.append(t1)
        
        # Wait for leader to be established
        time.sleep(3)
        assert leader.role == "leader"

        # Run late comer
        t2 = threading.Thread(target=late_comer.run, daemon=True)
        t2.start()
        threads.append(t2)

        # Wait for probe (1s) + startup
        time.sleep(3)

        # Verify late comer demoted itself
        assert late_comer.role == "follower", "Node 9 should have demoted to follower"
        assert late_comer.leader is not None
        assert late_comer.leader.leader_id == 10

    finally:
        for n in nodes:
            n.stop()
        for nid in [9, 10]:
            wal = f"cafeds_wal_node_{nid}.jsonl"
            if os.path.exists(wal):
                os.remove(wal)
