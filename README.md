# Cafe Distributed System (CafeDS)

[![CI](https://github.com/berkesiranurr/distrubuted_systems_cafe/actions/workflows/ci.yml/badge.svg)](https://github.com/berkesiranurr/distrubuted_systems_cafe/actions/workflows/ci.yml)

A distributed ordering system for a cafe with **dynamic discovery**, leader election, and total ordering.

## Features
- **Dynamic Discovery**: Nodes find each other automatically via UDP broadcast — no hardcoded IP/host lists.
- **Leader Election**: Uses the Bully algorithm. Any node can become leader dynamically.
- **Total Ordering**: Leader sequences messages; followers use buffers to handle gaps.
- **Persistence**: Write-Ahead Log (WAL) for fault tolerance.

---

## Running on Multiple Laptops (LAN)

Make sure all laptops are on the **same LAN / WiFi network**. No special configuration needed — nodes discover each other automatically.

### Laptop A: Node 10 (Initial Leader / Kitchen)
The node with the highest ID will act as the initial leader.
```bash
PYTHONPATH=. python run_node.py --id 10 --role leader --tcp-port 8010 --ui kitchen
```

### Laptop B: Node 3 (Waiter)
```bash
PYTHONPATH=. python run_node.py --id 3 --role follower --tcp-port 8003 --ui waiter
```

### Laptop C: Node 2 (Waiter)
```bash
PYTHONPATH=. python run_node.py --id 2 --role follower --tcp-port 8002 --ui waiter
```

> **Note:** Node IDs can be **any unique integers** (not limited to 2, 3, 10). The Bully algorithm uses the highest ID to determine the leader during elections.

---

## Running Locally (Single PC — 3 Terminals)

For testing on a single machine, set `CAFEDS_SINGLE_PC=1` to enable localhost discovery.

### Terminal 1: Node 10 (Initial Leader / Kitchen)
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

## Windows Users

On Windows (PowerShell), set environment variables before running:
```powershell
$env:PYTHONPATH = "."
$env:CAFEDS_SINGLE_PC = "1"   # Only for single-PC testing
python run_node.py --id 10 --role leader --tcp-port 8010 --ui kitchen
```

Or in CMD:
```cmd
set PYTHONPATH=.
set CAFEDS_SINGLE_PC=1
python run_node.py --id 10 --role leader --tcp-port 8010 --ui kitchen
```

## Firewall Note

If nodes on different laptops cannot discover each other, make sure:
1. **Windows Firewall** allows Python through (both private and public networks)
2. UDP ports **37020** (discovery) and **37100–37120** (node communication) are open
3. TCP ports **8002–8010** (or whatever `--tcp-port` you use) are open

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