---
layout: default
title: SKAVA Project
---

### SKAVA VO-aligned Production Service

This repository provides a production-ready backend for SKAVA data discovery and access routing.

Current features:
- ObsCore-inspired metadata catalog in PostgreSQL
- distributed replica modeling across nodes
- discovery API with VO-style parameters
- access-routing API as DataLink/SODA precursor
- VOSI-inspired capabilities endpoint
- structured logging, request tracing, and Prometheus metrics

Operational docs:
- `docs/internal_ingestion.md`
- `docs/ingestion.md`
- `docs/discovery_queries.md`
- `docs/access_datalink.md`
- `docs/datalink_endpoint.md`
- `docs/soda_sync.md`
- `docs/install.md`
- `docs/runbook.md`
- `docs/vo_alignment.md`
- `docs/architecture.md`

Scope note:
The service is operational in production, while full TAP/ObsTAP/DataLink/SODA standard-server compliance is still a planned evolution path.
