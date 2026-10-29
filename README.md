# SKAVA — discovery that returns an execution decision

SKAVA is the data discovery and access service of the SKA Visual Analytics
project for the SKA Regional Centre network. A scientific query resolves to
a dataset, the dataset to its replicas across the federation's nodes, and a
ranking policy over the nodes' measured state picks the replica and the
compute service next to it that should serve this request, with the reason.
The answer is a standard DataLink document; the client then works on the
node, and the file never crosses the network.

Documentation: <https://skava.readthedocs.io>

## What it provides

- **Discovery** on an ObsCore catalogue: `/discovery/search`,
  `/discovery/dataset/{obs_id}`, and TAP on `ivoa.obscore` (`/tap/sync`,
  `/tap/async`, VOSI `/tap/tables` and `/tap/capabilities`) for pyvo,
  TOPCAT and any VO client.
- **Routing**: `/datalink/{obs_id}` lists the replicas in rank order with a
  score and a reason each, and the services of the chosen node (its VisIVO
  backend, its SODA service, moment maps and position–velocity diagrams),
  as JSON or as an IVOA DataLink VOTable. The finders a node offers are in
  its status document, where the Computing Broker reads them. The
  `resource_aware` policy ranks on what a background prober measures at the
  nodes (reachability, round-trip time, CPU pressure, queue, free memory
  against the dataset's size); the `static` policy on declared scores.
- **SODA next to the data**: `/soda/sync` redirects (303) to the SODA
  service of the node that holds the selected replica; the node cuts the
  cube, synchronously or as a UWS job. `/soda/execute` is a non-standard
  proxy for clients that cannot follow the redirect.
- **Federation**: `/federation/search` asks the sibling catalogues of other
  sites with the caller's token and merges the answers on `obs_id`.
- **Identity**: OpenID Connect bearer tokens (the SRCNet IAM, or Keycloak),
  with the IVOA `ivoa_bearer` challenge; static tokens for a closed
  deployment; an open mode for development.
- **Ingestion in place**: `skava-publisher` reads headers on the node and
  sends only metadata to `/internal/ingestion/*`.
- **Operations**: a web admin (`/admin/`) for nodes, datasets, replicas,
  users and the audit log; Prometheus `/metrics`, `/availability`,
  `/health/db`, `/capabilities`; structured JSON logs; Alembic migrations.

## Quick start

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
alembic upgrade head          # PostgreSQL at SKAVA_DATABASE_URL
python -m app.seed            # demo catalogue
uvicorn app.main:app --reload
```

Or `docker compose up --build` (service on `http://localhost:8000`). Every
setting is an environment variable; `.env.example` lists the defaults and
the [configuration reference](https://skava.readthedocs.io/en/latest/reference/env-vars.html)
explains them.

```bash
curl 'http://localhost:8000/discovery/search?POS=CIRCLE%20180%20-30%200.2'
curl 'http://localhost:8000/datalink/dataset-3'
curl 'http://localhost:8000/tap/sync?QUERY=SELECT%20TOP%205%20*%20FROM%20ivoa.obscore'
```

## A federation on one machine

`testbed/` brings up two catalogues, an IAM, a Computing Broker and four
simulated SRC nodes with different memory, CPU, load and network links,
each a VisIVO Visual Analytics backend next to its own copies of the data:

```bash
cd testbed && make data up seed
```

It is where the routing policy, the operations next to the data and the
federation are evaluated; see [testbed/README.md](testbed/README.md).

## Tests

```bash
pytest
```

## License and funding

GNU General Public License v3.0 (see [LICENSE](LICENSE)).

This work was supported by the SKA Visual Analytics (SKAVA) project, funded
by the Italian National Institute for Astrophysics (INAF) under the
Astrophysics Fundamental Research Grant (Techno Grant).
