# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
from app.ingestion.parsers.csv_parser import parse_csv_file
from app.ingestion.parsers.json_parser import parse_json_file

__all__ = ["parse_csv_file", "parse_json_file"]
