# VO Alignment Notes

## ObsCore Usage

The `datasets` table adopts practical ObsCore-style naming for production discovery:
- `obs_id`, `obs_collection`, `dataproduct_type`, `calib_level`
- sky coordinates: `s_ra`, `s_dec`
- temporal bounds: `t_min`, `t_max`
- spectral bounds: `em_min`, `em_max`

Discovery endpoints map to these fields and are designed to evolve with full VO query semantics.

## DataLink Approximation

`/access/{obs_id}` acts as a DataLink precursor:
- resolves best location for a dataset
- returns an access contract (routing metadata)
- advertises operation hints in `supported_operations`

`/datalink/{obs_id}` also serves a **conformant IVOA DataLink VOTable** (request with
`RESPONSEFORMAT=application/x-votable+xml`): the standard `{links}` table columns
(`ID, access_url, service_def, semantics, content_type, content_length, …` with the
spec UCDs), `#`-prefixed semantics vocabulary terms, and a service-descriptor
`RESOURCE` (`utype="adhoc:service"`) for the SODA cutout with an `inputParams` group
(`ID/POS/BAND/TIME`). This is consumable by pyvo / TOPCAT as a DataLink document.
The JSON descriptor remains the default and is what the VisIVO desktop consumes.

## TAP/ObsTAP Profile

`/tap/sync` implements a constrained ObsCore compatibility profile:
- `SELECT` from `ivoa.ObsCore`
- equality predicates on `obs_id`, `obs_collection`, `dataproduct_type`
- bounded `MAXREC`
- VOTable or JSON output

Full TAP async and broad ADQL support remain future work.

## SODA: validation + real execution

- `/soda/sync` validates SODA parameters and returns a routing descriptor.
- `/soda/execute` performs a **real byte-level FITS cutout** (`POS`/`BAND`) by delegating
  to the dataset node's co-located VisIVO backend (compute-next-to-data), with a staging
  handoff fallback when no backend is available. See [SODA execution](soda_execution.md).

Remaining SODA work:
1. asynchronous SODA (`/soda/async`) with a job queue;
2. additional region shapes (full POLYGON geometry) and `POL`/`BAND` refinements;
3. richer VOTable error/parameter serialisation.

## Compliance Statement

The service is production-hardened and VO-aligned. DataLink is served as a conformant
VOTable descriptor and SODA cutout execution is implemented via node-local delegation.
It does not yet claim full TAP/ObsTAP, full async DataLink/SODA, or full standard-server
compliance across all operations.
