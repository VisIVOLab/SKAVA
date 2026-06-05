---
layout: default
title: SKAVA Project
---

### SKAVA VO-aligned Production Service

This repository provides a production-hardened backend for SKAVA data discovery and access routing.

Current features:
- ObsCore-inspired metadata catalog in PostgreSQL
- distributed replica modeling across nodes
- discovery API with VO-style parameters
- access-routing API as DataLink/SODA precursor
- DataLink VOTable output profile
- TAP sync ObsCore compatibility profile
- VOSI-inspired capabilities endpoint
- structured logging, request tracing, and Prometheus metrics

Operational docs:
- `docs/internal_ingestion.md`
- `docs/ingestion.md`
- `docs/discovery_queries.md`
- `docs/access_datalink.md`
- `docs/datalink_endpoint.md`
- `docs/tap_sync.md`
- `docs/production_readiness_phase2.md`
- `docs/soda_sync.md`
- `docs/install.md`
- `docs/runbook.md`
- `docs/vo_alignment.md`
- `docs/architecture.md`

Scope note:
The service is operationally hardened, while full TAP async/full ADQL, full DataLink service behavior, and SODA execution remain planned evolution paths.
