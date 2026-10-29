# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""Benchmark the cost of SKAVA's routing decision against catalogue size.

For every (n, k) configuration the script builds a synthetic catalogue of
``n`` logical datasets, each with ``k`` replicas on ``k`` nodes whose ranking
inputs differ, so every resolution exercises the full ranking path. It then
times, through the complete HTTP stack:

* ``datalink``   GET /datalink/{obs_id}: identity lookup, replica expansion,
                 eligibility, ranking, descriptor emission (the decision);
* ``collection`` GET /discovery/search?COLLECTION=...&limit=100;
* ``cone``       GET /discovery/search?POS=CIRCLE ra dec r&limit=100.

Two ways to reach the stack:

* in process (default): FastAPI's TestClient against the given database;
* ``--url``: a running SKAVA server whose database is ``--database-url``
  (the script seeds that database, the server answers the requests).

Examples::

    # SQLite in memory, quick
    .venv/bin/python scripts/benchmark_routing.py --n 10000 100000 --k 3

    # PostgreSQL (the testbed's database), n sweep and k sweep
    .venv/bin/python scripts/benchmark_routing.py \\
        --database-url postgresql+psycopg://skava:skava@localhost:5432/skava_bench \\
        --n 10000 100000 1000000 --k 3 --out results/routing_n
    .venv/bin/python scripts/benchmark_routing.py \\
        --database-url postgresql+psycopg://skava:skava@localhost:5432/skava_bench \\
        --n 10000 --k 1 3 10 30 --out results/routing_k

The database is DROPPED and recreated for every configuration: never point
``--database-url`` at a catalogue you want to keep.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = "sqlite+pysqlite://"

# The app reads its settings at import time; give it a harmless database so the
# import never tries to reach the production default.
os.environ.setdefault("SKAVA_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SKAVA_PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("SKAVA_ENV", "dev")
os.environ.setdefault("SKAVA_LOG_LEVEL", "WARNING")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, insert, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.models.dataset import Dataset  # noqa: E402
from app.models.node import Node  # noqa: E402
from app.models.replica import DatasetReplica  # noqa: E402
from app.spatial_index import DEFAULT_SPATIAL_ORDER, compute_spatial_cell  # noqa: E402

BATCH = 10_000
COLLECTIONS = [f"bench-{i}" for i in range(10)]


def make_engine(url: str):
    if url.startswith("sqlite") and (url.endswith("://") or ":memory:" in url):
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, pool_pre_ping=True)


def seed(engine, n: int, k: int, base_seed: int) -> float:
    """Recreate the schema and insert n datasets with k replicas each; returns seconds.

    Positions depend on (seed, n) only and replica order on (seed, n, k), so a k
    sweep at fixed n keeps the same sky and the same queries.
    """
    sky = random.Random(f"{base_seed}-sky-{n}")
    order = random.Random(f"{base_seed}-order-{n}-{k}")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    start = time.perf_counter()
    with engine.begin() as conn:
        conn.execute(insert(Node), [
            {
                "id": j + 1,
                "code": f"NODE-{j:02d}",
                "name": f"Benchmark node {j}",
                "base_url": f"https://node{j}.example.org",
                "is_enabled": True,
                "is_available": True,
                # Distinct inputs so the three-key sort really orders them.
                "latency_score": 5.0 + 3.0 * j,
                "load_score": 0.1 + 0.02 * j,
                "capability_score": 1.0 - 0.01 * j,
            }
            for j in range(k)
        ])
    replica_id = 1
    for lo in range(0, n, BATCH):
        hi = min(n, lo + BATCH)
        datasets, replicas = [], []
        for i in range(lo, hi):
            ra = sky.random() * 360.0
            dec = sky.random() * 180.0 - 90.0
            datasets.append({
                "id": i + 1,
                "obs_id": f"bench-{i}",
                "obs_collection": COLLECTIONS[i % len(COLLECTIONS)],
                "dataproduct_type": "cube",
                "s_ra": ra,
                "s_dec": dec,
                "s_fov": 0.05,
                "spatial_index_order": DEFAULT_SPATIAL_ORDER,
                "spatial_index_cell": compute_spatial_cell(ra, dec),
                "t_min": 59000.0 + (i % 100),
                "t_max": 59000.5 + (i % 100),
                "em_min": 0.21,
                "em_max": 0.22,
                "access_format": "application/fits",
                "access_estsize": 1024,
            })
            # Replicas in a shuffled node order, so ranking (not insertion order)
            # decides the best one.
            for j in order.sample(range(k), k):
                replicas.append({
                    "id": replica_id,
                    "dataset_id": i + 1,
                    "node_id": j + 1,
                    "remote_path": f"/data/bench-{i}.fits",
                    "access_endpoint": f"file:///data/bench-{i}.fits",
                    "status": "available",
                    "is_public": True,
                })
                replica_id += 1
        with engine.begin() as conn:
            conn.execute(insert(Dataset), datasets)
            conn.execute(insert(DatasetReplica), replicas)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            # Explicit ids leave the sequences behind; move them past the data
            # so the catalogue stays usable after the run.
            for table in ("nodes", "datasets", "dataset_replicas"):
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"))
            conn.execute(text("ANALYZE"))
    return time.perf_counter() - start


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(p / 100.0 * (len(ordered) - 1))))
    return ordered[idx]


def time_requests(get, paths: list[str], warmup: int) -> list[float]:
    for path in paths[:warmup]:
        get(path)
    out = []
    for path in paths[warmup:]:
        t0 = time.perf_counter()
        resp = get(path)
        out.append((time.perf_counter() - t0) * 1000.0)
        if resp.status_code != 200:
            raise RuntimeError(f"GET {path} -> HTTP {resp.status_code}: {resp.text[:200]}")
    return out


def run_config(engine, n: int, k: int, args) -> list[dict]:
    seed_s = seed(engine, n, k, args.seed)
    # Same requests for every k at a given n.
    rng = random.Random(f"{args.seed}-requests-{n}")
    total = args.requests + args.warmup
    workloads = {
        "datalink": [f"/datalink/bench-{rng.randrange(n)}" for _ in range(total)],
        "collection": [
            f"/discovery/search?COLLECTION={rng.choice(COLLECTIONS)}&DPTYPE=cube&limit=100"
            for _ in range(total)
        ],
        "cone": [
            f"/discovery/search?POS=CIRCLE%20{rng.random() * 360.0:.4f}%20{rng.uniform(-60, 60):.4f}%201.0&limit=100"
            for _ in range(total)
        ],
    }

    if args.url:
        import httpx

        client = httpx.Client(base_url=args.url, timeout=60.0)
        get = client.get
        closer = client.close
    else:
        from fastapi.testclient import TestClient

        from app.main import app

        session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)

        def override_get_db():
            db = session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        client.__enter__()
        get = client.get

        def closer():
            client.__exit__(None, None, None)
            app.dependency_overrides.pop(get_db, None)

    rows = []
    try:
        for name, paths in workloads.items():
            ms = time_requests(get, paths, args.warmup)
            rows.append({
                "workload": name,
                "n": n,
                "k": k,
                "requests": len(ms),
                "p50_ms": round(statistics.median(ms), 3),
                "p95_ms": round(percentile(ms, 95), 3),
                "mean_ms": round(statistics.fmean(ms), 3),
                "min_ms": round(min(ms), 3),
                "max_ms": round(max(ms), 3),
                "seed_s": round(seed_s, 2),
            })
    finally:
        closer()
    return rows


def environment(engine, args) -> dict:
    info = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "database": engine.dialect.name,
        "target": args.url or "in-process TestClient",
        "requests": args.requests,
        "warmup": args.warmup,
        "seed": args.seed,
    }
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            info["database_version"] = conn.execute(text("SHOW server_version")).scalar()
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=DEFAULT_DB,
                        help="SQLAlchemy URL; dropped and recreated per configuration (default: SQLite in memory)")
    parser.add_argument("--url", default=None, help="base URL of a running SKAVA using --database-url")
    parser.add_argument("--n", type=int, nargs="+", default=[10_000, 100_000], help="catalogue sizes")
    parser.add_argument("--k", type=int, nargs="+", default=[3], help="replicas per dataset")
    parser.add_argument("--requests", type=int, default=50, help="timed requests per workload")
    parser.add_argument("--warmup", type=int, default=5, help="untimed requests per workload")
    parser.add_argument("--seed", type=int, default=20261027)
    parser.add_argument("--out", type=Path, default=None, help="write <out>.json and <out>.csv")
    args = parser.parse_args()
    if args.url and args.database_url == DEFAULT_DB:
        parser.error("--url needs the server's own --database-url (an in-memory database is not shared)")

    engine = make_engine(args.database_url)
    rows = []
    for n in args.n:
        for k in args.k:
            print(f"n={n} k={k} ...", file=sys.stderr, flush=True)
            rows.extend(run_config(engine, n, k, args))

    print(f"{'workload':<11}{'n':>9}{'k':>4}{'p50 ms':>10}{'p95 ms':>10}")
    for r in rows:
        print(f"{r['workload']:<11}{r['n']:>9}{r['k']:>4}{r['p50_ms']:>10.2f}{r['p95_ms']:>10.2f}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.with_suffix(".json").write_text(
            json.dumps({"environment": environment(engine, args), "results": rows}, indent=2))
        with args.out.with_suffix(".csv").open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
