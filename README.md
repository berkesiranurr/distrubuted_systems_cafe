# Cafe Distributed System (CafeDS)

[![CI](https://github.com/berkesiranurr/distrubuted_systems_cafe/actions/workflows/ci.yml/badge.svg)](https://github.com/berkesiranurr/distrubuted_systems_cafe/actions/workflows/ci.yml)

A distributed ordering system for a cafe with leader election and total ordering.

## Features
- **Leader Election**: Uses the Bully algorithm.
- **Total Ordering**: Leader sequences messages; followers use buffers to handle gaps.
- **Persistence**: Write-Ahead Log (WAL) for fault tolerance.

## Running the System

To run a 3-node distributed system on a single machine, open three separate terminals and run the following commands.

### Terminal 1: Node 10 (Initial Leader / Kitchen)
The node with the highest ID (10) will act as the initial leader.
```bash
CAFEDS_SINGLE_PC=1 PYTHONPATH=. python run_node.py --id 10 --role leader --tcp-port 8010 --ui kitchen
```

### Terminal 2: Node 3 (Waiter)
```bash
CAFEDS_SINGLE_PC=1 PYTHONPATH=. python run_node.py --id 3 --role follower --tcp-port 8003 --ui waiter
```

### Terminal 3: Node 2 (Waiter)
```bash
CAFEDS_SINGLE_PC=1 PYTHONPATH=. python run_node.py --id 2 --role follower --tcp-port 8002 --ui waiter
```

---
**Usage Note:** In the Waiter terminal (Node 2 or 3), you can type an order (e.g., `Espresso`) and press Enter. You should see it delivered to all nodes!

## Testing Locally

To run the integration tests locally:

1.  **Install dependencies**:
    Using `pip`:
    ```bash
    pip install pytest black
    ```
    Or using `uv` (recommended):
    ```bash
    uv sync
    ```

2.  **Run tests**:
    ```bash
    PYTHONPATH=. pytest tests/test_integration.py
    ```

To perform a style check:
```bash
black --check .
```