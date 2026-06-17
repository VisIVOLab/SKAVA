from datetime import datetime, timezone
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.base import IngestError, IngestSummary, IngestionRecord
from app.ingestion.normalizers.obscore_normalizer import normalize_record
from app.ingestion.validators.metadata_validator import validate_record
from app.models.dataset import Dataset
from app.models.node import Node
from app.models.replica import DatasetReplica
from app.spatial_index import DEFAULT_SPATIAL_ORDER, compute_spatial_cell

logger = logging.getLogger("skava.ingestion")


class IngestService:
    def __init__(
        self,
        db: Session,
        *,
        dry_run: bool = False,
        source_type: str | None = None,
        source_ref: str | None = None,
    ):
        self.db = db
        self.dry_run = dry_run
        self.source_type = source_type
        self.source_ref = source_ref

    def ingest_records(self, raw_records: list[dict[str, Any]]) -> IngestSummary:
        summary = IngestSummary()

        for idx, raw in enumerate(raw_records):
            summary.total_records += 1

            try:
                record = normalize_record(raw, source_type=self.source_type, source_ref=self.source_ref)
            except Exception as exc:
                self._skip(summary, idx, "normalization_error", str(exc), raw)
                continue

            errors = validate_record(record)
            if errors:
                self._skip(summary, idx, "validation_error", "; ".join(errors), raw)
                continue

            node = self._resolve_node(record.node_id)
            if not node:
                self._skip(summary, idx, "node_not_found", f"Node not found: {record.node_id}", raw)
                continue

            dataset, dataset_action = self._upsert_dataset(record)
            if dataset_action == "inserted":
                summary.inserted_datasets += 1
            else:
                summary.updated_datasets += 1

            replica_action = self._upsert_replica(dataset, node, record)
            if replica_action == "inserted":
                summary.inserted_replicas += 1
            else:
                summary.updated_replicas += 1

        if self.dry_run:
            self.db.rollback()
        else:
            self.db.commit()

        summary.finalize()
        logger.info("ingestion_summary", extra=summary.as_dict())
        return summary

    def _skip(self, summary: IngestSummary, idx: int, code: str, message: str, raw: dict[str, Any]) -> None:
        summary.skipped_records += 1
        summary.validation_errors.append(IngestError(index=idx, code=code, message=message, raw=raw))
        logger.warning("ingestion_record_skipped", extra={"index": idx, "code": code, "error_detail": message})

    def _resolve_node(self, node_id: str) -> Node | None:
        node = self.db.scalar(select(Node).where(Node.code == node_id))
        if node:
            return node

        if node_id.isdigit():
            return self.db.scalar(select(Node).where(Node.id == int(node_id)))
        return None

    def _upsert_dataset(self, record: IngestionRecord) -> tuple[Dataset, str]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        existing = self.db.scalar(select(Dataset).where(Dataset.obs_id == record.obs_id))

        payload = {
            "obs_collection": record.obs_collection,
            "dataproduct_type": record.dataproduct_type,
            "calib_level": record.calib_level,
            "target_name": record.target_name,
            "s_ra": record.s_ra,
            "s_dec": record.s_dec,
            "s_fov": record.s_fov,
            "t_min": record.t_min,
            "t_max": record.t_max,
            "em_min": record.em_min,
            "em_max": record.em_max,
            "spatial_index_order": DEFAULT_SPATIAL_ORDER if record.s_ra is not None and record.s_dec is not None else None,
            "spatial_index_cell": compute_spatial_cell(record.s_ra, record.s_dec),
            "access_format": record.access_format,
            "access_estsize": record.access_estsize,
            "source_type": record.source_type,
            "source_ref": record.source_ref,
            "checksum": record.checksum,
            "provenance_json": record.provenance,
            "doi": record.doi,
            "pid": record.pid,
            "citation": record.citation,
            "license": record.license,
            "updated_at": now,
            "ingested_at": now,
        }

        if existing:
            if not self.dry_run:
                for key, value in payload.items():
                    if value is not None:
                        setattr(existing, key, value)
            return existing, "updated"

        dataset = Dataset(obs_id=record.obs_id, **payload)
        if not self.dry_run:
            self.db.add(dataset)
            self.db.flush()
        return dataset, "inserted"

    def _upsert_replica(self, dataset: Dataset, node: Node, record: IngestionRecord) -> str:
        dataset_id = dataset.id
        if self.dry_run and dataset_id is None:
            # Resolve id in dry-run for existing datasets.
            persisted = self.db.scalar(select(Dataset).where(Dataset.obs_id == record.obs_id))
            dataset_id = persisted.id if persisted else None

        existing = None
        if dataset_id is not None:
            existing = self.db.scalar(
                select(DatasetReplica).where(DatasetReplica.dataset_id == dataset_id, DatasetReplica.node_id == node.id)
            )

        if existing:
            if not self.dry_run:
                existing.access_endpoint = record.access_url
                existing.is_public = record.is_public if record.is_public is not None else True
                existing.status = "available"
            return "updated"

        if not self.dry_run:
            if dataset.id is None:
                persisted = self.db.scalar(select(Dataset).where(Dataset.obs_id == record.obs_id))
                dataset_id = persisted.id if persisted else None
            else:
                dataset_id = dataset.id

            if dataset_id is None:
                raise RuntimeError("Unable to resolve dataset id during replica insertion")

            self.db.add(
                DatasetReplica(
                    dataset_id=dataset_id,
                    node_id=node.id,
                    remote_path=f"/ingested/{record.obs_id}",
                    access_endpoint=record.access_url,
                    is_public=record.is_public if record.is_public is not None else True,
                    status="available",
                )
            )
        return "inserted"
