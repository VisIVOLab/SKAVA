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

`/datalink/{obs_id}` also supports a minimal VOTable links table for VO-oriented clients.
This is intentionally not a full DataLink server implementation.

## TAP/ObsTAP Profile

`/tap/sync` implements a constrained ObsCore compatibility profile:
- `SELECT` from `ivoa.ObsCore`
- equality predicates on `obs_id`, `obs_collection`, `dataproduct_type`
- bounded `MAXREC`
- VOTable or JSON output

Full TAP async and broad ADQL support remain future work.

## SODA Evolution Path

Current implementation exposes SODA-oriented affordances (`supports_soda`, operation hints), while real processing operations are deferred.

Planned next steps:
1. Add operation descriptors for cutout/subset parameterization.
2. Implement execution backends for selected SODA operations.
3. Align response serialization with richer VO artifacts where needed.

## Compliance Statement

The service is production-hardened and VO-aligned.
It does not currently claim full TAP/ObsTAP, full DataLink, or full SODA standard-server compliance.
