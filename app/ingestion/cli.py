# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
import argparse
import json

from app.db import SessionLocal
from app.ingestion.parsers.csv_parser import parse_csv_file
from app.ingestion.parsers.json_parser import parse_json_file
from app.ingestion.services.ingest_service import IngestService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SKAVA metadata ingestion CLI")
    parser.add_argument("--file", required=True, help="Input manifest file")
    parser.add_argument("--format", required=True, choices=["csv", "json"], help="Input format")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without writing to DB")
    parser.add_argument("--source-ref", default=None, help="Optional source reference string")
    parser.add_argument("--source-type", default=None, help="Optional source type string")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.format == "csv":
        records = parse_csv_file(args.file)
    else:
        records = parse_json_file(args.file)

    with SessionLocal() as db:
        service = IngestService(
            db,
            dry_run=args.dry_run,
            source_ref=args.source_ref,
            source_type=args.source_type,
        )
        summary = service.ingest_records(records)

    print(json.dumps(summary.as_dict(), indent=2))


if __name__ == "__main__":
    main()
