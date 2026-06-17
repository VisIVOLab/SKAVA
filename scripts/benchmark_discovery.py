import argparse
import os
import random
import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SKAVA_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SKAVA_PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("SKAVA_ENV", "dev")
os.environ.setdefault("SKAVA_LOG_LEVEL", "WARNING")

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.dataset import Dataset  # noqa: E402
from app.models.node import Node  # noqa: E402
from app.models.replica import DatasetReplica  # noqa: E402
from app.spatial_index import DEFAULT_SPATIAL_ORDER, compute_spatial_cell  # noqa: E402


def seed(session: Session, count: int) -> None:
    node = Node(
        code="BENCH",
        name="Benchmark Node",
        base_url="https://bench.example.org",
        is_enabled=True,
        is_available=True,
        latency_score=5.0,
        load_score=0.1,
        capability_score=1.0,
    )
    session.add(node)
    session.flush()
    for idx in range(count):
        ra = random.random() * 360.0
        dec = (random.random() * 180.0) - 90.0
        dataset = Dataset(
            obs_id=f"bench-{idx}",
            obs_collection="benchmark",
            dataproduct_type="image",
            s_ra=ra,
            s_dec=dec,
            s_fov=0.05,
            spatial_index_order=DEFAULT_SPATIAL_ORDER,
            spatial_index_cell=compute_spatial_cell(ra, dec),
            t_min=59000.0 + (idx % 100),
            t_max=59000.5 + (idx % 100),
            em_min=1.0e-6,
            em_max=2.0e-6,
            access_format="image/fits",
            access_estsize=1024,
        )
        session.add(dataset)
        session.flush()
        session.add(
            DatasetReplica(
                dataset_id=dataset.id,
                node_id=node.id,
                remote_path=f"/bench/{idx}.fits",
                access_endpoint=f"https://bench.example.org/datalink/bench-{idx}",
                status="available",
                is_public=True,
            )
        )
        if idx and idx % 1000 == 0:
            session.commit()
    session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local SKAVA discovery benchmark with synthetic metadata.")
    parser.add_argument("--records", type=int, default=10000)
    parser.add_argument("--queries", type=int, default=20)
    args = parser.parse_args()

    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    with testing_session_local() as db:
        seed(db, args.records)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    durations = []
    with TestClient(app) as client:
        for _ in range(args.queries):
            start = time.perf_counter()
            response = client.get("/discovery/search", params={"COLLECTION": "benchmark", "DPTYPE": "image", "limit": 100})
            response.raise_for_status()
            durations.append((time.perf_counter() - start) * 1000.0)

    print(
        {
            "records": args.records,
            "queries": args.queries,
            "min_ms": round(min(durations), 3),
            "p50_ms": round(sorted(durations)[len(durations) // 2], 3),
            "max_ms": round(max(durations), 3),
        }
    )


if __name__ == "__main__":
    main()
