# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.base import IngestError, IngestSummary, IngestionRecord
from app.ingestion.normalizers.obscore_normalizer import normalize_record
from app.ingestion.validators.metadata_validator import validate_record
from app.config import settings
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
        # What this batch has accepted so far, per obs_id: the nodes holding
        # it and the product's identity (checksum, size, type). Earlier
        # records of the batch are not yet in the database (no autoflush; in a
        # dry run, never), so the replica check reads this first.
        self._batch: dict[str, dict[str, Any]] = {}
        # Identity fields of a replaced file that its new record does not restate.
        self._clear: dict[str, list[str]] = {}

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

            conflict = self._replica_conflict(record, node)
            if conflict:
                self._skip(summary, idx, conflict[0], conflict[1], raw)
                continue

            dataset, dataset_action = self._upsert_dataset(record)
            if not self.dry_run:
                for field in self._clear.pop(record.obs_id, []):
                    setattr(dataset, field, None)
            if dataset_action == "inserted":
                summary.inserted_datasets += 1
            else:
                summary.updated_datasets += 1

            replica_action = self._upsert_replica(dataset, node, record)
            if replica_action == "inserted":
                summary.inserted_replicas += 1
            else:
                summary.updated_replicas += 1
            if not self.dry_run:
                # Later records of the batch look datasets and replicas up by
                # query; with autoflush off they must be written first.
                self.db.flush()

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
            "obs_title": record.obs_title,
            "facility_name": record.facility_name,
            "instrument_name": record.instrument_name,
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

    _IDENTITY_FIELDS = ("checksum", "access_estsize", "dataproduct_type")

    def _evidence(self, obs_id: str) -> dict[str, Any] | None:
        """The catalogued product under ``obs_id``: its holders and identity,
        as this batch left it, else as the database has it, else None."""
        if obs_id in self._batch:
            return self._batch[obs_id]
        existing = self.db.scalar(select(Dataset).where(Dataset.obs_id == obs_id))
        if existing is None:
            return None
        nodes = set(self.db.scalars(select(DatasetReplica.node_id)
                                    .where(DatasetReplica.dataset_id == existing.id)).all())
        return {"nodes": nodes, **{f: getattr(existing, f) for f in self._IDENTITY_FIELDS}}

    def _replica_conflict(self, record: IngestionRecord, node: Node) -> tuple[str, str] | None:
        """Why this record cannot be counted as a copy of the product already
        catalogued under its ``obs_id``, as (code, message), or None (and the
        record is then counted in).

        Records sharing an ``obs_id`` are taken as replicas of one product, so
        a node must not join the copies other nodes hold unless it holds the
        same product. A record that contradicts the catalogue (another
        checksum, size or product type, where both state it) is a
        ``replica_conflict``. Under ``replica_identity = "checksum"`` (the
        default) a node that does not yet hold the dataset must also prove the
        copy, by a checksum equal to the catalogue's; without one the record
        is ``replica_unverified``: two products of one observation of equal
        size and type, with no checksum, are not merged. A node that already
        holds the dataset updates its own replica (which is how a catalogue
        without checksums acquires them), and an operator can still declare a
        replica by hand in the admin UI. Earlier records of the batch count.
        """
        evidence = self._evidence(record.obs_id)
        if evidence is not None and evidence["nodes"] - {node.id}:
            differences = []
            for field in self._IDENTITY_FIELDS:
                mine, theirs = getattr(record, field), evidence.get(field)
                if mine is not None and theirs is not None and str(mine) != str(theirs):
                    differences.append(f"{field} {mine} here, {theirs} in the catalogue")
            if differences:
                return ("replica_conflict",
                        f"obs_id {record.obs_id} is already catalogued as a different product on other "
                        f"nodes ({'; '.join(differences)}); not accepted as a replica")
            joining = node.id not in evidence["nodes"]
            if joining and settings.replica_identity == "checksum" and not (
                    record.checksum and evidence.get("checksum")):
                missing = "this record" if not record.checksum else "the catalogue"
                return ("replica_unverified",
                        f"obs_id {record.obs_id} is held by other nodes and {missing} states no checksum: "
                        "the copy cannot be verified, so it is not accepted as a replica "
                        "(publish checksums, or declare the replica in the admin UI)")
        # Accepted: what the catalogue will hold after this record.
        state = {"nodes": set(), **{f: None for f in self._IDENTITY_FIELDS}} if evidence is None else \
            {"nodes": set(evidence["nodes"]), **{f: evidence.get(f) for f in self._IDENTITY_FIELDS}}
        state["nodes"].add(node.id)
        sole_holder = state["nodes"] == {node.id}
        stated = {f: getattr(record, f) for f in self._IDENTITY_FIELDS if getattr(record, f) is not None}
        changed = sole_holder and any(state[f] is not None and str(state[f]) != str(v) for f, v in stated.items())
        if changed:
            # The file was replaced: what the record does not restate about it
            # belongs to the old file and is forgotten, here and in the catalogue.
            self._clear[record.obs_id] = [f for f in self._IDENTITY_FIELDS if f not in stated]
            for field in self._clear[record.obs_id]:
                state[field] = None
        for field, value in stated.items():
            if sole_holder or state[field] is None:
                state[field] = value
        self._batch[record.obs_id] = state
        return None

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
