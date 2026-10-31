# VisIVO + SKAVA — Roadmap: carving out space alongside CARTA

> Scope: this roadmap covers the **whole ecosystem** — SKAVA (discovery /
> access / federation) **and** the VisIVO backend + desktop (compute + 3D
> visualization). It is intentionally cross-repo.

## North Star (positioning)

VisIVO/SKAVA is **not** "a better CARTA". CARTA is the mature, web-based,
SRCNet-endorsed tool for **2D radio cube analysis at scale** — and we do not
beat it on that ground. We win where CARTA *structurally cannot go*:

- **the discovery / access / federation VO layer of the SRC** (SKAVA), and
- **the 3D + source-finding-in-3D viewer** (VisIVO),

**interoperable with CARTA, not competing with it on 2D.**

## Flagship demo (the thread through every phase)

**Fornax HI** — discovery in SKAVA → open the cube **in 3D on the node**
(compute-next-to-data) → run SoFiA-2 on the node → **render the mask as a 3D
grid** over the source → SODA cutout. This single workflow is something CARTA
cannot replicate. Every phase below hardens it.

## Pillars (the "space")

- **A. 3D + source-finding-in-3D** — the radio wedge CARTA does not do.
- **B. SKAVA — discovery / access / federation VO** — the unfilled SRCNet gap.
- **C. Compute-to-data product generation** — spectral-index maps, mosaics,
  SoFiA masks, cross-matched catalogues (CARTA does not produce these).
- **D. Interoperability** — SAMP/DataLink: be the SRC **entry point** and the
  **3D companion**, not yet-another 2D viewer.

---

## Phase 0 — NOW (0–4 weeks): a showable flagship + consolidation

Goal: a **reproducible differentiator we can demo**.

| Deliverable | Why it carves space | Effort |
|---|---|---|
| In-window **3D mask overlay** (grid on volume **and** isosurface) | The "wow" moment CARTA can't show | M (runtime) |
| Wire the **remote spectral profiler** (`spectralProbe`) for large cubes | Without it the 3D feels crippled → retention | S |
| **SoFiA-2 bundled in the backend** image, validated on a PLEIADI node | Removes the "install SoFiA" friction | S |
| **Publish the MFS data** in SKAVA (CT/PA nodes) + run the demo end-to-end | Real data, SKA narrative | S |
| Commit everything pending (SODA/DataLink/TAP/products/deploy/fixes) | Hygiene + stable base | S |

**Metric:** the Fornax demo runs end-to-end on `visivo-server` + 1 node, capturable as a GIF/slide.

---

## Phase 1 — NEXT (1–3 months): make it sticky + interoperable

Goal: a radio astronomer can run a **real HI-3D workflow** without hitting walls, and can reach it from CARTA.

| Deliverable | Why | Effort |
|---|---|---|
| **Competent 2D companions**: region stats + interactive spectrum on the cube | The minimum bar so they don't bounce back to CARTA after the 3D | M |
| **SAMP interop CARTA↔VisIVO**: "send cube → VisIVO 3D" | Add VisIVO to their flow, don't replace it | M |
| **Remote / out-of-core 3D rendering** (use the SSR probe + node GPUs) | The 3D must scale beyond the demo cube | L |
| **MFS early adopters** (Serra et al., INAF) on a real science case | Feedback + publishable case + HI-community word of mouth | — |
| Tutorial "from discovery to 3D in 3 clicks" | Lower the barrier to entry | S |

**Metric:** ≥3 radio astronomers using VisIVO for 3D/SoFiA on real data; SAMP interop working.

---

## Phase 2 — STRATEGIC (3–6 months): SRCNet-grade SKAVA

Goal: SKAVA is **deployable as an SRC service** that fits SRCNet — where CARTA does not play.

| Deliverable | Why | Effort |
|---|---|---|
| **SKA AAI/IAM** (federated tokens) replacing the built-in admin auth | SRCNet entry requirement | M |
| **Standards → compliance**: TAP async, DataLink/SODA async with a job queue, full VOSI | From "aligned" to "compliant" | L |
| **Geo / network-aware routing** (today it is static) | The real "compute near the user" | M |
| **Web / remote access** to the viewer (at least for 3D) | Remove the desktop-Qt barrier | L |
| Robust cross-SRC federation (beyond best-effort) | The real data-mesh | M |

**Metric:** SKAVA deployed on ≥2 SRC nodes with a real catalogue, SKA auth, VO queries from pyvo/TOPCAT.

---

## Phase 3 — MOAT (6–12 months): hard differentiation

Goal: capabilities **no other tool** has.

- **3D volumetric at SKA scale** (out-of-core, node GPUs, multi-TB cubes).
- **Simulation↔observation bridge** (cosmology N-body/hydro — VisIVO heritage).
- **Deep-learning source finders** (Mask-RCNN/U-Net) as a near-data service.
- **CARTA-impossible products**: spectral-index maps, noise-weighted mosaics,
  Faraday/RM in 3D, 3D cross-matched catalogues.

**Metric:** ≥1 science result obtained with VisIVO that was not possible with CARTA.

---

## ⛔ Anti-goals (what we will NOT build)

Do not reimplement CARTA's mature 2D: **image matching** (XY/Z/R),
**Splatalogue** line query, 6-method profile smoothing, the **Stokes-scatter
widget**, tiled raster at scale. Huge cost, zero payoff — CARTA already won
that ground and is inside SRCNet.

## Risks & mitigations

- **Small team / funding** → focus on one wedge (3D + SoFiA) + one layer
  (SKAVA); do not spread thin.
- **SRCNet already leaning on CARTA** → position as **complementary** (interop),
  not as an alternative.
- **3D scale unproven** → Phase 1 (out-of-core) is make-or-break: without it the
  3D stays a demo.
- **Node reachability** (SODA execute / desktop→backend) → document the
  SSH-tunnel / SLURM pattern (see `docs/operations/node-behind-firewall.md` for SKAVA's side, and VisIVO's
  `deployment/hpc-slurm` page for the backend).

## KPIs (12 months)

1. MFS 3D + SoFiA demo at a radio conference.
2. ≥3 active radio astronomers on VisIVO 3D.
3. SKAVA on ≥2 SRC nodes with AAI + standards compliance.
4. Working CARTA↔VisIVO interoperability.

---

### One-line summary

CARTA has already won 2D radio at scale and is inside SRCNet — VisIVO does not
beat it there. But on **3D volumetric + source-finding-in-3D + VO
discovery/federation + products CARTA can't generate**, the space is real and
**complementary**: that is where radio astronomers will open VisIVO, and from
there (interop) we earn the everyday use — without fighting CARTA on its turf.
