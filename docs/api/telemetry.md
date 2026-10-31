# Telemetry API

The `resource_aware` ranking policy ranks replicas on what each node's
co-located VisIVO Visual Analytics backend reports about itself: round
trip, CPU pressure, tasks per worker, free memory. SKAVA gets that state in
two ways, and stores the newer of the two on the node row:

* the **prober**: SKAVA calls each node's backend;
* **node reports**: a node SKAVA cannot reach sends its state itself.

Three endpoints read and refresh that state. They are internal endpoints,
not part of the public catalogue.

```
GET  /internal/telemetry           the stored state of every node     X-Internal-Api-Key
POST /internal/telemetry/probe     probe the nodes now                X-Internal-Api-Key
POST /internal/telemetry/report    a node reports its own state       X-Skava-Node-Token
```

```{contents}
:local:
:depth: 2
```

## The prober

When `SKAVA_TELEMETRY_INTERVAL_SECONDS` is above zero (10 s by default),
an asyncio task started with the application probes, every interval, each
node that is enabled and has a VisIVO backend URL:

1. `GET <backend>/v1/ping`, `SKAVA_TELEMETRY_PING_SAMPLES` times (3 by
   default); the median round trip is kept as `probe_rtt_ms`;
2. `GET <backend>/v1/node/status`, with `SKAVA_VISIVO_BACKEND_TOKEN` as
   `X-Visivo-Token` when the node is marked as requiring a token.

Each request times out after `SKAVA_TELEMETRY_TIMEOUT_SECONDS`. A failure
stores `probe_ok: false` and the error; the policy then sets the node's
replicas aside ("backend unreachable at the last probe"). The round trip is
SKAVA's, measured from the catalogue's host. With an interval of `0` there
is no background prober: the state is refreshed only by
`POST /internal/telemetry/probe` and by node reports. The settings are in
[Environment variables](../reference/env-vars.md#routing-and-node-telemetry).

## Node reports

A node behind a firewall, a NAT or an SSH tunnel cannot be probed. Its
backend can instead post its `/v1/node/status` document to
`POST /internal/telemetry/report` every few seconds. The policy reads a
report as it reads a probe; the round trip is the one the node measured
on its previous exchange with the catalogue, when it sends one.

### How the prober and the reports interact

* The prober skips a node whose last stored observation is a report
  (`"source": "push"`) younger than `SKAVA_TELEMETRY_TTL_SECONDS`. A
  failing probe therefore never marks a reporting node unreachable.
* When the reports stop, the stored report ages past the TTL, the policy
  ranks the node as unmeasured (declared order), and the prober tries the
  node again on its next cycle.
* Whatever arrives, the newer observation wins: a probe or a report is
  stored only if nothing more recent is already on the node row. A probe
  in flight when a report lands is discarded.
* A node needs a VisIVO backend URL for the policy to rank it on
  telemetry, even when the catalogue cannot reach that URL: the URL is
  what the clients use.

The setup of a node that reports is in
[Registering a node SKAVA cannot reach](../operations/node-behind-firewall.md).

### The node token

`POST /internal/telemetry/report` does not accept the internal key. Each
node presents its own token:

```
X-Skava-Node-Token: <HMAC-SHA256(INTERNAL_API_KEY, "skava-node-telemetry:" + node code), hex>
```

The catalogue recomputes the token on every report, so nothing is stored.
A token speaks for one node only, and the node never holds the internal
key, which also opens ingestion. Changing `INTERNAL_API_KEY` revokes every
node token at once. Print a node's token on the catalogue's host:

```bash
python -m app.security.node_token INAF-CT
```

and give it to the operator of the node's backend, with this catalogue's
URL and the node's code. How the VisIVO Visual Analytics backend is set up
to report is described by VisIVO:
[Running the backend as an SRC node](https://visivo.readthedocs.io/en/latest/deployment/src-node.html).

## `POST /internal/telemetry/report`

```bash
curl -s -X POST https://skava.example.org/internal/telemetry/report \
    -H "X-Skava-Node-Token: $NODE_TOKEN" -H "Content-Type: application/json" \
    -d '{"node_code": "INAF-CT", "rtt_ms": 12.4, "status": { ... the /v1/node/status document ... }}'
```

```{list-table}
:header-rows: 1
:widths: 18 82

* - Field
  - Meaning
* - ``node_code``
  - The node's ``code`` in the catalogue (1 to 32 characters, compared
    exactly; codes are stored upper-case). The token must be the one of
    this code.
* - ``status``
  - The backend's ``/v1/node/status`` document, a JSON object. SKAVA keeps
    only the fields the policy reads (below); a missing or malformed field
    is stored as unknown, not refused.
* - ``rtt_ms``
  - Optional. The round trip the node measured to the catalogue, in
    milliseconds. Kept when it is a number from 0 to 60000; otherwise the
    last known value stays.
```

Answer:

```json
{"node": "INAF-CT", "accepted": true}
```

`accepted` is `false` when a newer observation of the node was already
stored; the report is then dropped.

### Errors

```{list-table}
:header-rows: 1
:widths: 12 88

* - Status
  - When
* - 401
  - ``X-Skava-Node-Token`` missing, malformed (not 64 lowercase hex
    digits) or not the token of ``node_code``; also when the catalogue has
    no ``INTERNAL_API_KEY``.
* - 400
  - The node is unknown or disabled (``Node not found or disabled``).
* - 400
  - ``status.node_code`` is set and names another node (``The status
    describes node ..., not ...``).
* - 400
  - The body does not validate (no ``node_code``, ``status`` not an
    object).
```

Errors use SKAVA's error envelope, `{"error": {"code", "message",
"details"}, "request_id"}`, with `code` `unauthorized` (401) or
`invalid_query` (400).

## `GET /internal/telemetry`

Requires `X-Internal-Api-Key`. Returns the policy in force and the stored
state of every node, enabled or not, ordered by code. The node entry below
is the one recorded in the
[PLEIADI-GPU run](../operations/e2e-pleiadi-gpu-runbook.md) (cgroup v1, so
CPU pressure is unknown):

```json
{
  "policy": "resource_aware",
  "ttl_seconds": 60.0,
  "interval_seconds": 10.0,
  "nodes": [
    {
      "code": "PLEIADI-GPU-OACT",
      "probe_ok": true,
      "probe_rtt_ms": 76.899,
      "probe_error": null,
      "telemetry_at": "2026-10-30T08:47:34.907351Z",
      "status": {
        "node_code": "PLEIADI-GPU-OACT",
        "version": "d9ccbd7",
        "cpu": {"cpus": 8.0, "pressure_pct": null, "utilisation_pct": null},
        "memory": {"total_bytes": 68719476736.0, "available_bytes": 65074757632.0, "pressure_pct": null},
        "disk": {"workspace_free_bytes": 1170038849536.0},
        "workers": {"total": 8.0},
        "tasks": {"running": 0.0, "queued": 0.0},
        "render": {"active": 0.0, "capacity": 8.0},
        "gpu": true,
        "capabilities": {"kinds": ["image", "cube", "dynspec"], "finders": ["sofia2", "photutils"]},
        "source": "probe"
      }
    }
  ]
}
```

`status` holds only the fields listed here, whatever the node sent; a value
SKAVA cannot use is `null`. `source` is `probe` or `push` (a node report).
`telemetry_at` is the time of the stored observation (UTC). A node never
measured has `null` in every field.

## `POST /internal/telemetry/probe`

Requires `X-Internal-Api-Key`. Probes every node the prober would probe (the
enabled nodes with a backend URL, except those with a fresh report) now,
and stores the results:

```json
{"probed": 4, "ok": 3}
```

Use it after registering a node, in experiments, or with the background
prober off.

## Metrics

Every probe attempt and every report increments
`skava_node_probes_total{node, outcome}` (a report counts as a successful
probe), and the round trip of the newest stored observation sets
`skava_node_rtt_ms{node}`. See
[Monitoring](../operations/monitoring.md).
