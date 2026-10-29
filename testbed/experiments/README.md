# Experiments on the testbed

Scripted sessions against the four-node testbed, speaking the same APIs as
the VisIVO Visual Analytics desktop: SKAVA's discovery and DataLink, the
nodes' VisIVO backends (open in place, slices, SODA jobs, finder tasks) and
the Computing Broker. Each experiment writes `results/<name>.json` (with the
run's metadata: commits, host, data profile) and `results/<name>.csv`;
`plots.py` draws the figures from them and `tables.py` writes the paper's
tables (LaTeX, one file each) and prints the numbers the text quotes.

| Experiment | What it measures |
|---|---|
| **E1** `scripts/benchmark_routing.py` | The decision's cost against catalogue size `n` and replica multiplicity `k`, on the testbed's PostgreSQL (the paper's Tables 2–3), plus the prober's cost from SKAVA's own metrics. |
| **E2** `e2_placement.py` | Placement quality: open, first slice and moment-0 timed on the node each policy (static, resource-aware) chose and on every other replica; the loaded, far and too-small nodes are what the policies see differently. |
| **E3** `e3_failure.py` | A node killed mid-session: the client's fallback to the next ranked node, the catalogue's detection through its probe, the time to rank the node again. |
| **E4** `e4_bytes.py` | Bytes that crossed the node's link, from the kernel's counters: downloading the file versus open + preview, a cutout, a moment map and a source finder run in place. |
| **E5** `e5_finder.py` | Source finding through the broker versus download and run locally: time and bytes. |
| **E6** `e6_federation.py` | Two catalogues, one search: the merge on `obs_id` with the second site under `also_at`, the IAM's token forwarded (and refused when absent), the cost of the federated search against the local one, and the second site stopped and back. |

```bash
make up seed                      # the testbed, with the ci profile
make experiments                  # E2..E6 in turn (E1 is its own target)
make experiment-e1                # the routing benchmark on PostgreSQL
make figures                      # results/figures/*.pdf
make tables                       # results/tables/*.tex, the paper's tables, and the numbers its text quotes

# The paper's numbers: the larger data, then the same
make data PROFILE=paper && make seed && make experiments
```

The scripts need only the standard library; `make figures` needs matplotlib
(`PLOT_PY` names a Python that has it). E2 and E3 restart the SKAVA
container (to switch the policy) and kill node containers; nothing else on
the host is touched. E4 and E5 start a plain HTTP server inside the big node
for the download case and a throw-away client container on the testbed
network, with the big node's CPU and memory limits, for the local run. E6
signs in at the IAM with the testbed user's password and stops and restarts
the second catalogue's container.
