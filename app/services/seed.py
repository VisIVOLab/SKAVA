from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.node import Node
from app.models.replica import DatasetReplica
from app.spatial_index import DEFAULT_SPATIAL_ORDER, compute_spatial_cell


def seed_data(db: Session) -> None:
    db.execute(delete(DatasetReplica))
    db.execute(delete(Dataset))
    db.execute(delete(Node))

    nodes = {
        "A": Node(
            code="A",
            name="Node A",
            base_url="https://node-a.example.org",
            is_enabled=True,
            is_available=True,
            latency_score=15.0,
            load_score=0.30,
            capability_score=0.80,
        ),
        "B": Node(
            code="B",
            name="Node B",
            base_url="https://node-b.example.org",
            is_enabled=True,
            is_available=True,
            latency_score=10.0,
            load_score=0.45,
            capability_score=0.90,
        ),
        "C": Node(
            code="C",
            name="Node C",
            base_url="https://node-c.example.org",
            is_enabled=True,
            is_available=True,
            latency_score=22.0,
            load_score=0.20,
            capability_score=0.70,
        ),
    }
    db.add_all(nodes.values())
    db.flush()

    datasets = {}
    for i in range(1, 8):
        obs_id = f"dataset-{i}"
        datasets[obs_id] = Dataset(
            obs_id=obs_id,
            obs_collection="skava-demo",
            obs_title=f"SKAVA demo observation {i}",
            dataproduct_type="image",
            calib_level=2,
            target_name=f"target-{i}",
            facility_name="SKA",
            instrument_name="SKA-MID",
            s_ra=100.0 + i,
            s_dec=-20.0 - i,
            s_fov=0.2,
            spatial_index_order=DEFAULT_SPATIAL_ORDER,
            spatial_index_cell=compute_spatial_cell(100.0 + i, -20.0 - i),
            t_min=59000.0 + i,
            t_max=59000.5 + i,
            em_min=1.2e-6,
            em_max=1.8e-6,
            access_format="image/fits",
            access_estsize=1024 * i,
            provenance_json={"generated_by": "app.services.seed", "calibration_level": 2},
            doi=f"10.0000/skava.demo.{i}",
            pid=f"skava:demo:{obs_id}",
            citation=f"SKAVA demo observation {i}",
            license="CC-BY-4.0",
        )
    db.add_all(datasets.values())
    db.flush()

    replica_map = {
        "A": ["dataset-1", "dataset-2", "dataset-3"],
        "B": ["dataset-3", "dataset-4", "dataset-5"],
        "C": ["dataset-1", "dataset-6", "dataset-7"],
    }

    replicas = []
    for node_code, obs_ids in replica_map.items():
        node = nodes[node_code]
        for obs_id in obs_ids:
            dataset = datasets[obs_id]
            replicas.append(
                DatasetReplica(
                    dataset_id=dataset.id,
                    node_id=node.id,
                    remote_path=f"/data/{obs_id}.fits",
                    access_endpoint=f"{node.base_url}/datalink/{obs_id}",
                    status="available",
                    is_public=True,
                )
            )
    db.add_all(replicas)
    db.commit()


def seed_if_empty(db: Session) -> None:
    has_data = db.scalar(select(Node.id).limit(1))
    if not has_data:
        seed_data(db)
