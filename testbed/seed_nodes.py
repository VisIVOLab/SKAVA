"""Register the testbed's nodes in SKAVA (run inside the SKAVA container).

The publisher can only attach replicas to nodes SKAVA already knows, so the
nodes come first. Each node advertises its co-located VisIVO backend.

The static ranking inputs are what an operator would declare at registration
time, before the testbed's conditions are applied: the small node looks close
and idle, the busy node was idle when it was registered. They are deliberately
not updated afterwards; that staleness is what the static policy lives with.
"""
from sqlalchemy import select

from app.db import SessionLocal
from app.models.node import Node

NODES = [
    # code,    host,         latency, load, capability
    ("BIG", "node-big", 10.0, 0.20, 1.00),
    ("SMALL", "node-small", 5.0, 0.10, 0.50),
    ("FAR", "node-far", 20.0, 0.10, 0.90),
    ("BUSY", "node-busy", 8.0, 0.10, 0.90),
]


def main() -> None:
    with SessionLocal() as db:
        for code, host, latency, load, capability in NODES:
            node = db.scalar(select(Node).where(Node.code == code)) or Node(code=code)
            node.name = f"Testbed node {code.lower()}"
            node.base_url = f"http://{host}:8000"
            node.visivo_backend_url = f"http://{host}:8000"
            node.visivo_backend_requires_auth = True
            node.is_enabled = True
            node.is_available = True
            node.latency_score = latency
            node.load_score = load
            node.capability_score = capability
            db.add(node)
        db.commit()
        for node in db.scalars(select(Node).order_by(Node.code)):
            print(f"{node.code:6s} {node.visivo_backend_url}")


if __name__ == "__main__":
    main()
