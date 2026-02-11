import argparse
import time

from cafeds.node import Node


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--role", choices=["leader", "follower"], required=True)
    ap.add_argument("--tcp-port", type=int, required=True)

    # NEW: UI mode for follower (and harmless for leader)
    ap.add_argument("--ui", choices=["waiter", "kitchen"], default="kitchen")

    args = ap.parse_args()

    try:
        node = Node(node_id=args.id, role=args.role, tcp_port=args.tcp_port, ui=args.ui)
        node.run()
        while True:
            time.sleep(0.5)
    except OSError:
        # Already logged "CRITICAL: Port ... in use" in Node.__init__
        exit(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        node.stop()


if __name__ == "__main__":
    main()
