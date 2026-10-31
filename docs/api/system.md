# System, access, staging and provenance

The endpoints that are not discovery, DataLink, SODA, TAP or federation:
the service's own state (for monitoring and VOSI-style descriptions), a
compatibility view of the access resolution, the metadata-cache staging
jobs, and a dataset's provenance.

```
GET  /availability[?include_nodes=true]   service and database state        open
GET  /health/db                           database reachability             open
GET  /metrics                             Prometheus metrics                open
GET  /capabilities                        the service's interfaces (JSON)   open
GET  /access/{obs_id}                     access resolution (legacy shape)  public rule
POST /staging/jobs?ID=<obs_id>            a metadata-cache staging job      public rule
GET  /staging/jobs/{job_id}               one staging job                   public rule
GET  /provenance/{obs_id}                 provenance, PID, DOI, citation    public rule
```

"Open" endpoints never require a token, so monitoring can call them. The
"public rule" is the catalogue's: open by default, a token as soon as
static tokens or an IAM are configured (see [Authentication](auth.md)).
Errors use SKAVA's error envelope,
`{"error": {"code", "message", "details"}, "request_id"}`.

```{contents}
:local:
:depth: 1
```

## `GET /availability`

The service is up and its database answers.

```bash
curl -s "https://skava.example.org/availability?include_nodes=true"
```

```json
{
  "status": "ok",
  "service": "skava-discovery",
  "database": {"status": "ok", "database": "reachable"},
  "nodes": {"total_nodes": 4, "enabled_nodes": 4, "available_nodes": 4}
}
```

* `nodes` is present only with `include_nodes=true`; it counts the node rows
  and those the operator left enabled and available. It does not reflect
  the telemetry.
* `status` is `degraded` when `include_nodes=true` and no node is both
  enabled and available; otherwise `ok`.
* When the database does not answer, the response is `503`
  (`service_unavailable`, `Database unreachable`).

## `GET /health/db`

`{"status": "ok", "database": "reachable"}`, or `503`
(`service_unavailable`) when a `SELECT 1` fails. Use it as the readiness
probe of the API container.

## `GET /metrics`

The Prometheus text exposition of the process's metrics (requests,
latencies, database errors, node probes). The metrics and suggested alerts
are in [Monitoring](../operations/monitoring.md).

## `GET /capabilities`

A JSON description of the service, in the spirit of VOSI capabilities:
`service`, `profile`, `version`, `vosi` (the paths of `availability` and
`capabilities`), `interfaces[]` (each with `name`, `path`, `method`,
`description` and `params`), `standards[]` (ObsCore, DataLink, SODA,
TAP/ObsTAP, each with its `support_level`) and a `compliance_note` stating
what is not supported. The TAP service's own VOSI documents are
`/tap/capabilities` and `/tap/tables` (see [TAP API](tap.md)).

## `GET /access/{obs_id}`

A compatibility view of [`/datalink/{obs_id}`](datalink.md) for clients
written against the first access API. It resolves the dataset the same
way, and returns, next to the DataLink envelope (`dataset`, `routing`,
`primary_access`, `links`, `service_descriptors`, `capabilities`, and the
whole response again under `datalink`), the flat fields of the old
contract:

```{list-table}
:header-rows: 1
:widths: 26 74

* - Field
  - Meaning
* - ``obs_id``
  - The dataset.
* - ``best_node``
  - ``routing.best_node``.
* - ``access_url``
  - ``primary_access.access_url``.
* - ``access_mode``
  - Always ``remote-routing``.
* - ``supported_operations``
  - ``["download"]``, plus ``"cutout"`` and ``"band_subset"`` when a
    ranked replica is a ``file://`` copy on a node with a VisIVO backend.
* - ``supports_soda``
  - True in that same case.
* - ``supports_datalink``
  - Always true.
```

`404` (`dataset_not_found`) for an unknown obs_id. New clients should use
`/datalink/{obs_id}`.

## `POST /staging/jobs`

Records a staging job for a dataset. The only mode is `metadata-cache`: the
dataset is resolved at submission, and the job stores the resolution, so a
workflow can hand the access information on by job id. No file is copied.

```bash
curl -s -X POST "https://skava.example.org/staging/jobs?ID=tb-cube-l&mode=metadata-cache"
```

```json
{
  "job_id": 12,
  "created_at": "2026-10-30T09:41:12.512000",
  "completed_at": "2026-10-30T09:41:12.512000",
  "status": "ready",
  "obs_id": "tb-cube-l",
  "stage_mode": "metadata-cache",
  "staged_url": "file:///data/cubes/tb-cube-l.fits",
  "request": {"ID": "tb-cube-l", "mode": "metadata-cache"},
  "result": { "...": "the DataLink JSON of the dataset at submission" },
  "error_message": null,
  "requested_by": "token:3f9a0c1d2e4b5a69"
}
```

* `ID` is required and is the dataset's obs_id; `mode` defaults to
  `metadata-cache`. Any other mode is `400` (`invalid_query`).
* The job is `ready` at once; `staged_url` is the primary access URL at
  submission.
* `requested_by` is a reference to the caller's token (`token:` and the
  first 16 hex digits of its SHA-256), `null` on an open instance; the
  token itself is never stored.
* An unknown obs_id is `404` (`dataset_not_found`).

`/soda/execute` records the same kind of job when no node can cut the
dataset in place (see [SODA API](soda.md)).

## `GET /staging/jobs/{job_id}`

The job as above. An unknown `job_id` is `400` (`invalid_query`,
`Staging job '<id>' not found`), not 404.

## `GET /provenance/{obs_id}`

What the catalogue records about where a dataset's metadata came from and
how to cite it:

```json
{
  "obs_id": "tb-cube-l",
  "source_type": "...",
  "source_ref": "...",
  "checksum": "sha256:...",
  "provenance": {"rel_path": "cubes/tb-cube-l.fits", "size_bytes": 3221230592, "sha256": "...", "publisher_label": "..."},
  "doi": null,
  "pid": null,
  "citation": null,
  "license": "CC-BY-4.0",
  "ingested_at": "2026-10-30T09:12:44.103000",
  "updated_at": "2026-10-30T09:12:44.103000"
}
```

`provenance` is the free-form object the ingestion stored (the publisher
fills it with the file's relative path, size in bytes, SHA-256 and its
`publisher_label`; see
[Ingestion API](ingestion.md)). `404` (`dataset_not_found`) for an unknown
obs_id.
