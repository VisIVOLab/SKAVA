"""D2.2 representative sample datasets (WP2 / T2.2).

Seeds SKAVA's catalogue with a curated set of real-world test datasets
covering the four data types declared in the D2.2 deliverable:

* 2-D Images (Stokes total intensity continuum)
* Spectral Cubes (HI / molecular line cubes)
* Beamformed Time Series (FRB / pulsar dynamic spectra)
* Polarimetric Maps (Stokes Q/U/V)

The metadata is ObsCore-aligned. ``s_ra`` / ``s_dec`` are in degrees,
``em_min`` / ``em_max`` are in metres (radio wavelengths), and
``t_min`` / ``t_max`` are MJD timestamps. ``access_endpoint`` per
replica points at the VisIVO backend's Workspace Exports endpoint by
default, which makes the demo fully local — drop the matching files
into ``~/.visivo/exports/`` and the chain "SKAVA discovery → VisIVO
desktop open" works end-to-end without any external connectivity.

Idempotent: previously inserted D2.2 records are deleted before reseed
so calling this multiple times converges on the canonical set.
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.node import Node
from app.models.replica import DatasetReplica
from app.spatial_index import DEFAULT_SPATIAL_ORDER, compute_spatial_cell


# Default URL of the VisIVO Workspace Exports endpoint. Both the URL host
# and the per-file basename can be overridden by editing each replica
# below. The endpoint is unauthenticated by default on a dev backend
# (no Bearer token required for /v1/exports/download).
_VISIVO_EXPORT_BASE = "http://host.docker.internal:8001/v1/exports/download"
# ↑ ``host.docker.internal`` resolves the host's loopback from inside the
# Docker network — works on macOS and Windows. On Linux without Docker
# Desktop, replace with ``http://172.17.0.1:8001/...`` or the LAN IP.

_PUBLIC_ARCHIVES_BASE = "https://archive-gw-1.kat.ac.za/public"
# Replace with the real archive URLs if you prefer pointing at the
# upstream public mirror instead of staging the files locally.


# ── Storage nodes ───────────────────────────────────────────────────────────

_D22_NODES = {
    "VIS-LOCAL": dict(
        name="VisIVO Backend (local Workspace Exports)",
        base_url="http://host.docker.internal:8001",
        is_enabled=True, is_available=True,
        latency_score=5.0, load_score=0.10, capability_score=0.95,
        # Distributed-backend coordinates (see
        # docs/distributed-backend-design.md). The desktop client picks
        # this up via the visivo-backend service descriptor and routes
        # the open through this backend instead of downloading.
        visivo_backend_url="http://host.docker.internal:8001",
        visivo_backend_requires_auth=False,
    ),
    "INAF-PUB": dict(
        name="INAF Public Archive (HTTP)",
        base_url="https://archive.inaf.it/public",
        is_enabled=True, is_available=True,
        latency_score=80.0, load_score=0.40, capability_score=0.75,
        visivo_backend_url=None,            # no VisIVO backend at this node
        visivo_backend_requires_auth=False,
    ),
    "SARAO-MGCLS": dict(
        name="SARAO MGCLS Mirror",
        base_url=_PUBLIC_ARCHIVES_BASE,
        is_enabled=True, is_available=True,
        latency_score=120.0, load_score=0.50, capability_score=0.80,
        visivo_backend_url=None,            # archive-only, no compute service
        visivo_backend_requires_auth=False,
    ),
}


# ── Helper to convert radio frequencies to ObsCore em_min/em_max (metres) ──

_C_M_PER_S = 299_792_458.0


def freq_hz_to_wavelength_m(freq_hz: float) -> float:
    return _C_M_PER_S / freq_hz


# ── D2.2 catalogue ──────────────────────────────────────────────────────────
#
# Each entry is a tuple of (Dataset constructor kwargs, list of replicas).
# Replicas are dicts with keys ``node_code``, ``remote_path``,
# ``access_endpoint``. The order of the list also sets the discovery
# fallback chain — best-ranked replica wins by latency_score, the rest
# stand in as alternates.

# Wavelength band for L-band (≈ 900 MHz – 1.67 GHz)
_L_BAND_MIN_M = freq_hz_to_wavelength_m(1.67e9)
_L_BAND_MAX_M = freq_hz_to_wavelength_m(0.90e9)
# UHF band (≈ 580 MHz – 1.015 GHz) — MeerKAT
_UHF_MIN_M = freq_hz_to_wavelength_m(1.015e9)
_UHF_MAX_M = freq_hz_to_wavelength_m(0.58e9)
# CHIME 400–800 MHz
_CHIME_MIN_M = freq_hz_to_wavelength_m(0.80e9)
_CHIME_MAX_M = freq_hz_to_wavelength_m(0.40e9)
# LoTSS 144 MHz @ 24 MHz bandwidth
_LOTSS_MIN_M = freq_hz_to_wavelength_m(0.156e9)
_LOTSS_MAX_M = freq_hz_to_wavelength_m(0.132e9)
# VLASS S-band 2-4 GHz
_VLASS_MIN_M = freq_hz_to_wavelength_m(4.0e9)
_VLASS_MAX_M = freq_hz_to_wavelength_m(2.0e9)


_D22_CATALOGUE = [
    # ── Category 1: 2-D Images (Stokes I continuum) ────────────────────────
    dict(
        obs_id="d22-mgcls-abell194-StokesI",
        obs_collection="MGCLS",
        obs_title="MGCLS Abell 194 cluster — Stokes I total intensity",
        dataproduct_type="image",
        calib_level=3,
        target_name="Abell 194",
        facility_name="MeerKAT",
        instrument_name="MeerKAT L-band",
        s_ra=21.5, s_dec=-1.4, s_fov=1.5,
        t_min=58484.0, t_max=58486.0,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="image/fits",
        access_estsize=350_000_000,
        doi="10.48479/7epd-w356",
        pid="skava:d22:mgcls:abell194:I",
        citation="Knowles et al. 2022, MeerKAT Galaxy Cluster Legacy Survey",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/mgcls/abell194_StokesI.fits",
                 filename="MGCLS_Abell194_StokesI.fits"),
            dict(node_code="SARAO-MGCLS",
                 remote_path="/repository/10.48479/7epd-w356/StokesI/Abell194.fits"),
        ],
    ),
    dict(
        obs_id="d22-mgcls-galactic-centre-StokesI",
        obs_collection="MGCLS",
        obs_title="MeerKAT Galactic Centre 1.28 GHz — Stokes I",
        dataproduct_type="image",
        calib_level=3,
        target_name="Galactic Centre",
        facility_name="MeerKAT",
        instrument_name="MeerKAT L-band",
        s_ra=266.4168, s_dec=-29.0078, s_fov=3.0,
        t_min=58484.0, t_max=58496.0,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="image/fits",
        access_estsize=800_000_000,
        doi="10.48479/fyst-hj47",
        pid="skava:d22:mgcls:gcen:I",
        citation="Heywood et al. 2022, Nature 'The 1.28 GHz MeerKAT Galactic Centre Mosaic'",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/mgcls/GalacticCentre_StokesI.fits",
                 filename="MeerKAT_Galactic_Centre_1284MHz-StokesI.fits"),
        ],
    ),
    dict(
        obs_id="d22-lotss-dr2-tile-145mhz",
        obs_collection="LoTSS-DR2",
        obs_title="LOFAR Two-metre Sky Survey DR2 tile (145 MHz)",
        dataproduct_type="image",
        calib_level=3,
        target_name="LoTSS-DR2 P184+55 tile",
        facility_name="LOFAR",
        instrument_name="LOFAR HBA",
        s_ra=184.0, s_dec=55.0, s_fov=2.5,
        t_min=58030.0, t_max=58060.0,
        em_min=_LOTSS_MIN_M, em_max=_LOTSS_MAX_M,
        access_format="image/fits",
        access_estsize=200_000_000,
        doi="10.1051/0004-6361/202142484",
        pid="skava:d22:lotss-dr2:P184+55",
        citation="Shimwell et al. 2022, LoTSS DR2",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/lotss/P184+55_mosaic.fits",
                 filename="LoTSS_DR2_P184+55.fits"),
        ],
    ),
    dict(
        obs_id="d22-vlass-21-quicklook",
        obs_collection="VLASS-2.1",
        obs_title="VLA Sky Survey VLASS 2.1 quick-look tile",
        dataproduct_type="image",
        calib_level=2,
        target_name="VLASS J123000+050000",
        facility_name="VLA",
        instrument_name="VLA S-band",
        s_ra=187.5, s_dec=5.0, s_fov=1.0,
        t_min=59100.0, t_max=59130.0,
        em_min=_VLASS_MIN_M, em_max=_VLASS_MAX_M,
        access_format="image/fits",
        access_estsize=120_000_000,
        doi="10.26093/cds/vizier.36240122",
        pid="skava:d22:vlass-21:J123000+050000",
        citation="Lacy et al. 2020, VLASS Quick-Look Catalog",
        license="Public Domain",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/vlass/vlass21_J123000+050000.fits",
                 filename="VLASS21_J123000+050000.fits"),
        ],
    ),
    dict(
        obs_id="d22-apertif-dr1-image",
        obs_collection="Apertif-DR1",
        obs_title="Apertif DR1 Stokes I continuum field",
        dataproduct_type="image",
        calib_level=3,
        target_name="Apertif DR1 field 191",
        facility_name="WSRT",
        instrument_name="Apertif",
        s_ra=200.0, s_dec=42.0, s_fov=8.0,
        t_min=58200.0, t_max=58300.0,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="image/fits",
        access_estsize=400_000_000,
        doi="10.1051/0004-6361/202244039",
        pid="skava:d22:apertif-dr1:field191:I",
        citation="Adams et al. 2022, Apertif DR1",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/apertif/dr1_field191_StokesI.fits",
                 filename="Apertif_DR1_field191_StokesI.fits"),
        ],
    ),

    # ── Category 2: Spectral Cubes (HI) ────────────────────────────────────
    dict(
        obs_id="d22-wallaby-pre-pilot-NGC4636",
        obs_collection="WALLABY",
        obs_title="ASKAP WALLABY pre-pilot — NGC 4636 HI cube",
        dataproduct_type="cube",
        calib_level=3,
        target_name="NGC 4636",
        facility_name="ASKAP",
        instrument_name="ASKAP-36 PAF",
        s_ra=190.7, s_dec=2.7, s_fov=2.0,
        t_min=58850.0, t_max=58900.0,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="image/fits",
        access_estsize=2_000_000_000,   # ~11 GB upstream, INT4-capped
        doi="10.25919/64ev-sh17",
        pid="skava:d22:wallaby:NGC4636",
        citation="Westmeier et al. 2022, WALLABY Pre-Pilot",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/wallaby/NGC4636_HI.fits",
                 filename="WALLABY_NGC4636_HI.fits"),
        ],
    ),
    dict(
        obs_id="d22-meerkat-fornax-HI",
        obs_collection="MFS",
        obs_title="MeerKAT Fornax Survey — HI cube fragment",
        dataproduct_type="cube",
        calib_level=3,
        target_name="Fornax A surroundings",
        facility_name="MeerKAT",
        instrument_name="MeerKAT L-band",
        s_ra=50.7, s_dec=-37.2, s_fov=4.0,
        t_min=59400.0, t_max=59600.0,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="image/fits",
        access_estsize=2_000_000_000,   # ~4.5 GB upstream, INT4-capped
        doi="10.1093/mnras/stab1822",
        pid="skava:d22:mfs:fornax-A",
        citation="Serra et al. 2023, MeerKAT Fornax Survey",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/mfs/Fornax_HI.fits",
                 filename="MeerKAT_Fornax_HI.fits"),
        ],
    ),
    dict(
        obs_id="d22-sdc2-pilot-cube",
        obs_collection="SDC2",
        obs_title="SKA Science Data Challenge 2 — pilot HI cube",
        dataproduct_type="cube",
        calib_level=3,
        target_name="SDC2 simulated field",
        facility_name="SKA (simulated)",
        instrument_name="SKA-MID (simulated)",
        s_ra=0.0, s_dec=-30.0, s_fov=20.0,
        t_min=60000.0, t_max=60001.0,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="image/fits",
        access_estsize=2_000_000_000,   # ~6 GB upstream, INT4-capped
        doi="10.5281/zenodo.6577089",
        pid="skava:d22:sdc2:pilot",
        citation="Hartley et al. 2023, SKA Data Challenge 2",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/sdc2/sdc2_pilot_cube.fits",
                 filename="SDC2_pilot_cube.fits"),
        ],
    ),
    dict(
        obs_id="d22-apertif-dr1-HI",
        obs_collection="Apertif-DR1",
        obs_title="Apertif DR1 HI cube",
        dataproduct_type="cube",
        calib_level=3,
        target_name="Apertif DR1 HI field",
        facility_name="WSRT",
        instrument_name="Apertif",
        s_ra=200.0, s_dec=42.0, s_fov=8.0,
        t_min=58200.0, t_max=58300.0,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="image/fits",
        access_estsize=2_000_000_000,   # ~3.5 GB upstream, INT4-capped
        doi="10.1051/0004-6361/202244039",
        pid="skava:d22:apertif-dr1:HI",
        citation="Adams et al. 2022, Apertif DR1",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/apertif/dr1_field191_HI.fits",
                 filename="Apertif_DR1_field191_HI.fits"),
        ],
    ),

    # ── Category 3: Beamformed time series / dynamic spectra ──────────────
    dict(
        obs_id="d22-chime-frb-sample",
        obs_collection="CHIME-FRB",
        obs_title="CHIME/FRB representative dynamic spectrum (open data)",
        dataproduct_type="timeseries",
        calib_level=2,
        target_name="FRB 20180916B (R3) sample",
        facility_name="CHIME",
        instrument_name="CHIME FRB backend",
        s_ra=29.5, s_dec=65.7, s_fov=0.0,
        t_min=58800.0, t_max=58800.001,  # sub-second event
        em_min=_CHIME_MIN_M, em_max=_CHIME_MAX_M,
        access_format="application/x-hdf5",
        access_estsize=450_000_000,
        doi="10.11570/21.0007",
        pid="skava:d22:chime-frb:R3-sample",
        citation="CHIME/FRB Collaboration 2021, First CHIME/FRB Catalog",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/chime/R3_sample.h5",
                 filename="CHIME_FRB_R3_sample.h5"),
        ],
    ),
    dict(
        obs_id="d22-meerkat-pulsar-J0437",
        obs_collection="MeerTime",
        obs_title="MeerKAT MeerTime PSR J0437-4715 PSRFITS",
        dataproduct_type="timeseries",
        calib_level=2,
        target_name="PSR J0437-4715",
        facility_name="MeerKAT",
        instrument_name="PTUSE",
        s_ra=69.3158, s_dec=-47.2525, s_fov=0.0,
        t_min=58900.0, t_max=58900.05,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="application/fits",
        access_estsize=200_000_000,
        doi="10.1017/pasa.2020.11",
        pid="skava:d22:meertime:J0437-4715",
        citation="Bailes et al. 2020, MeerTime",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/meertime/J0437-4715.psrfits",
                 filename="MeerKAT_MeerTime_J0437-4715.fits"),
        ],
    ),

    # ── Category 4: Polarimetric maps (Stokes Q/U/V) ──────────────────────
    dict(
        obs_id="d22-mgcls-abell194-StokesQ",
        obs_collection="MGCLS",
        obs_title="MGCLS Abell 194 — Stokes Q polarisation",
        dataproduct_type="image",
        calib_level=3,
        target_name="Abell 194",
        facility_name="MeerKAT",
        instrument_name="MeerKAT L-band",
        s_ra=21.5, s_dec=-1.4, s_fov=1.5,
        t_min=58484.0, t_max=58486.0,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="image/fits",
        access_estsize=350_000_000,
        doi="10.48479/7epd-w356",
        pid="skava:d22:mgcls:abell194:Q",
        citation="Knowles et al. 2022, MGCLS — Stokes Q plane",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/mgcls/abell194_StokesQ.fits",
                 filename="MGCLS_Abell194_StokesQ.fits"),
        ],
    ),
    dict(
        obs_id="d22-mgcls-abell194-StokesU",
        obs_collection="MGCLS",
        obs_title="MGCLS Abell 194 — Stokes U polarisation",
        dataproduct_type="image",
        calib_level=3,
        target_name="Abell 194",
        facility_name="MeerKAT",
        instrument_name="MeerKAT L-band",
        s_ra=21.5, s_dec=-1.4, s_fov=1.5,
        t_min=58484.0, t_max=58486.0,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="image/fits",
        access_estsize=350_000_000,
        doi="10.48479/7epd-w356",
        pid="skava:d22:mgcls:abell194:U",
        citation="Knowles et al. 2022, MGCLS — Stokes U plane",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/mgcls/abell194_StokesU.fits",
                 filename="MGCLS_Abell194_StokesU.fits"),
        ],
    ),
    dict(
        obs_id="d22-apertif-dr1-StokesV",
        obs_collection="Apertif-DR1",
        obs_title="Apertif DR1 — Stokes V circular polarisation",
        dataproduct_type="image",
        calib_level=3,
        target_name="Apertif DR1 field 191",
        facility_name="WSRT",
        instrument_name="Apertif",
        s_ra=200.0, s_dec=42.0, s_fov=8.0,
        t_min=58200.0, t_max=58300.0,
        em_min=_L_BAND_MIN_M, em_max=_L_BAND_MAX_M,
        access_format="image/fits",
        access_estsize=400_000_000,
        doi="10.1051/0004-6361/202244039",
        pid="skava:d22:apertif-dr1:field191:V",
        citation="Adams et al. 2022, Apertif DR1 — Stokes V",
        license="CC-BY-4.0",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/apertif/dr1_field191_StokesV.fits",
                 filename="Apertif_DR1_field191_StokesV.fits"),
        ],
    ),
    dict(
        obs_id="d22-vlass-21-IQU-cube",
        obs_collection="VLASS-2.1",
        obs_title="VLASS 2.1 IQU polarimetric cube",
        dataproduct_type="cube",
        calib_level=3,
        target_name="VLASS J123000+050000",
        facility_name="VLA",
        instrument_name="VLA S-band",
        s_ra=187.5, s_dec=5.0, s_fov=1.0,
        t_min=59100.0, t_max=59130.0,
        em_min=_VLASS_MIN_M, em_max=_VLASS_MAX_M,
        access_format="image/fits",
        access_estsize=600_000_000,
        doi="10.26093/cds/vizier.36240122",
        pid="skava:d22:vlass-21:IQU",
        citation="VLASS Polarimetric Pilot",
        license="Public Domain",
        replicas=[
            dict(node_code="VIS-LOCAL",
                 remote_path="/data/vlass/vlass21_IQU.fits",
                 filename="VLASS21_IQU_cube.fits"),
        ],
    ),
]


# ── Seed function ──────────────────────────────────────────────────────────

def _build_access_url(node_code: str, filename: str | None,
                       node_obj: Node, remote_path: str) -> str:
    """Build the per-replica access URL.

    Local nodes (VIS-LOCAL) get the VisIVO Workspace Exports endpoint with
    the filename as a query parameter. External nodes get
    ``<base_url>/<remote_path>`` as a generic URL — the user can refine
    in the seed file as they actually point at archive endpoints.
    """
    if node_code == "VIS-LOCAL" and filename:
        return f"{_VISIVO_EXPORT_BASE}?filename={filename}"
    return f"{node_obj.base_url}{remote_path}"


def seed_d22(db: Session) -> dict[str, int]:
    """Seed (or reseed) the D2.2 representative sample datasets.

    Idempotent: any existing dataset whose ``obs_id`` starts with ``d22-``
    is removed (and its replicas cascade-deleted) before reinsertion, so
    repeated calls converge on the canonical D2.2 set without polluting
    older runs.
    """
    # ── Remove previous D2.2 datasets (cascade deletes replicas) ─────
    stale = db.scalars(
        select(Dataset).where(Dataset.obs_id.like("d22-%"))).all()
    for ds in stale:
        db.delete(ds)
    db.flush()

    # ── Upsert nodes (preserve other nodes already present) ───────────
    existing_node_codes = {n.code for n in db.scalars(select(Node)).all()}
    new_nodes: dict[str, Node] = {}
    for code, kwargs in _D22_NODES.items():
        if code in existing_node_codes:
            new_nodes[code] = db.scalar(
                select(Node).where(Node.code == code))
        else:
            node = Node(code=code, **kwargs)
            db.add(node)
            new_nodes[code] = node
    db.flush()

    # ── Insert D2.2 datasets + replicas ──────────────────────────────
    counts = {"datasets": 0, "replicas": 0}
    for entry in _D22_CATALOGUE:
        ent = dict(entry)
        replicas_spec = ent.pop("replicas")
        ent["spatial_index_order"] = DEFAULT_SPATIAL_ORDER
        ent["spatial_index_cell"] = compute_spatial_cell(
                ent["s_ra"], ent["s_dec"])
        ent.setdefault("provenance_json", {
            "generated_by": "app.services.seed_d22",
            "wp": "WP2 / T2.2",
            "deliverable": "D2.2",
        })
        dataset = Dataset(**ent)
        db.add(dataset)
        db.flush()
        counts["datasets"] += 1

        for rep in replicas_spec:
            node_obj = new_nodes[rep["node_code"]]
            access_url = _build_access_url(
                    rep["node_code"], rep.get("filename"),
                    node_obj, rep["remote_path"])
            db.add(DatasetReplica(
                    dataset_id=dataset.id,
                    node_id=node_obj.id,
                    remote_path=rep["remote_path"],
                    access_endpoint=access_url,
                    status="available",
                    is_public=True,
            ))
            counts["replicas"] += 1

    db.commit()
    return counts


def seed_d22_if_empty(db: Session) -> dict[str, int] | None:
    has_d22 = db.scalar(
        select(Dataset.id).where(Dataset.obs_id.like("d22-%")).limit(1))
    if has_d22:
        return None
    return seed_d22(db)
