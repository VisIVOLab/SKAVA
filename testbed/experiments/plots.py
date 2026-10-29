"""The figures of the experiments, from results/*.json, as PDFs in
results/figures/. Needs matplotlib (``make figures`` names a Python that
has it). Every figure is drawn from the files alone, so re-running an
experiment and this script is the whole of regenerating a figure.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results"
FIGURES = RESULTS / "figures"

# The column width of an elsarticle 5p page is 3.4 in; figures are drawn at
# print size so their fonts are the paper's.
COL = 3.4
plt.rcParams.update({"font.size": 8, "axes.titlesize": 8, "legend.fontsize": 7, "figure.dpi": 150})


def load(name: str) -> dict | None:
    path = RESULTS / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGURES / f"{name}.pdf")
    plt.close(fig)
    print("wrote", FIGURES / f"{name}.pdf")


def fig_routing() -> None:
    """E1: the decision's cost against n (left) and k (right)."""
    n = load("routing_n")
    k = load("routing_k")
    if not n or not k:
        return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(2 * COL, 0.55 * COL))
    for workload, style in (("datalink", "o-"), ("cone", "s--"), ("collection", "^:")):
        rows = [r for r in n["results"] if r["workload"] == workload]
        ax1.plot([r["n"] for r in rows], [r["p50_ms"] for r in rows], style, label=workload, ms=4)
    ax1.set_xscale("log")
    ax1.set_xlabel("catalogue size $n$ (datasets, $k=3$)")
    ax1.set_ylabel("p50 latency (ms)")
    ax1.legend(frameon=False)
    ax1.grid(alpha=0.3)
    rows = [r for r in k["results"] if r["workload"] == "datalink"]
    ax2.plot([r["k"] for r in rows], [r["p50_ms"] for r in rows], "o-", ms=4, label="p50")
    ax2.plot([r["k"] for r in rows], [r["p95_ms"] for r in rows], "o--", ms=4, label="p95")
    ax2.set_xlabel("replicas per dataset $k$ ($n=10^4$)")
    ax2.set_ylabel("decision latency (ms)")
    ax2.set_ylim(bottom=0)
    ax2.legend(frameon=False)
    ax2.grid(alpha=0.3)
    save(fig, "e1_routing")


def fig_placement() -> None:
    """E2: time to moment-0 on the chosen node, per policy, against the best replica."""
    d = load("e2_placement")
    if not d:
        return
    rows = d["rows"]
    datasets = list(dict.fromkeys(r["dataset"] for r in rows))
    policies = list(dict.fromkeys(r["policy"] for r in rows))
    fig, axes = plt.subplots(1, 3, figsize=(2 * COL, 0.6 * COL), sharey=False)
    for ax, key, title in zip(axes, ("t_open", "t_slice", "t_m0"), ("open", "first slice", "moment 0")):
        width = 0.8 / (len(policies) + 1)
        for i, policy in enumerate(policies):
            vals, fails = [], []
            for ds in datasets:
                chosen = next((r for r in rows if r["dataset"] == ds and r["policy"] == policy and r["chosen"]), None)
                v = chosen[key] if chosen and chosen[key] is not None else None
                vals.append(v if v is not None else 0)
                fails.append(chosen is not None and chosen[key] is None)
            xs = [j + (i - len(policies) / 2) * width + width / 2 for j in range(len(datasets))]
            bars = ax.bar(xs, vals, width, label=policy.replace("_", "-"))
            for bar, failed in zip(bars, fails):
                if failed:
                    ax.text(bar.get_x() + bar.get_width() / 2, 0.02, "failed", rotation=90, ha="center", va="bottom", fontsize=6)
        best = []
        for ds in datasets:
            cands = [r[key] for r in rows if r["dataset"] == ds and r[key] is not None]
            best.append(min(cands) if cands else 0)
        xs = [j + len(policies) / 2 * width - width / 2 for j in range(len(datasets))]
        ax.bar(xs, best, width, label="best replica", color="0.75")
        ax.set_xticks(range(len(datasets)))
        ax.set_xticklabels([ds.replace("tb-cube-", "cube ") for ds in datasets])
        ax.set_title(title)
        ax.set_ylabel("seconds")
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(frameon=False)
    save(fig, "e2_placement")


def fig_failure() -> None:
    """E3: the client's fallback and the catalogue's detection, per trial."""
    d = load("e3_failure")
    if not d:
        return
    rows = d["rows"]
    fig, ax = plt.subplots(figsize=(COL, 0.6 * COL))

    def series(key: str, style: str, label: str) -> None:
        # A missing value is a failure or a timeout: it is marked, not drawn as zero.
        pts = [(r["trial"], r[key]) for r in rows if r.get(key) is not None]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], style, ms=4, label=label)
        for r in rows:
            if r.get(key) is None:
                ax.annotate("none", (r["trial"], 0), fontsize=6, ha="center", va="bottom", color="C3")

    series("t_client_fallback", "o-", "client: session resumed on the next node (after the kill)")
    series("t_skava_detect", "s--", "SKAVA: node dropped from the ranking (after the kill)")
    series("t_skava_recover", "^:", "SKAVA: node ranked again (after its backend answered)")
    ax.set_xlabel("trial")
    ax.set_ylabel("seconds")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=6)
    ax.grid(alpha=0.3)
    save(fig, "e3_failure")


def fig_bytes() -> None:
    """E4: bytes that crossed the node's link, per operation, against the file's size."""
    d = load("e4_bytes")
    if not d:
        return
    # A row whose product could not be opened in place is not a measurement
    # of the operation: it is left out and said so.
    rows = [r for r in d["rows"] if r.get("complete", True)]
    incomplete = [r for r in d["rows"] if not r.get("complete", True)]
    ops = list(dict.fromkeys(r["operation"] for r in rows))
    fig, ax = plt.subplots(figsize=(COL, 0.7 * COL))
    styles = {"download": "k-o", "open+preview": "-s", "cutout+open": "-^", "moment0+open": "-v", "finder+catalogue": "-D"}
    for op in ops:
        pts = [(r["file_bytes"], max(r["bytes_tx"], 1)) for r in rows
               if r["operation"] == op and r["bytes_tx"] is not None]
        pts.sort()
        ax.plot([p[0] for p in pts], [p[1] for p in pts], styles.get(op, "-x"), ms=4, label=op)
    if incomplete:
        ax.set_title(f"{len(incomplete)} incomplete measurement(s) left out", fontsize=6, color="C3")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("dataset size (bytes)")
    ax.set_ylabel("bytes sent by the node")
    # Above the axes: every corner inside has a line in it.
    ax.legend(frameon=False, fontsize=6, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3)
    ax.grid(alpha=0.3, which="both")
    save(fig, "e4_bytes")


def fig_finder() -> None:
    """E5: time and bytes, broker versus download-and-run."""
    d = load("e5_finder")
    if not d:
        return
    # A run that failed has no time to compare: it is marked, not drawn.
    rows = [r for r in d["rows"] if not r.get("error")]
    failed = [r for r in d["rows"] if r.get("error")]
    datasets = list(dict.fromkeys(r["dataset"] for r in d["rows"]))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(2 * COL, 0.55 * COL))
    width = 0.35
    for i, mode in enumerate(("broker", "download+local")):
        xs = [j + (i - 0.5) * width for j in range(len(datasets))]
        found = [next((r for r in rows if r["dataset"] == ds and r["mode"] == mode), None) for ds in datasets]
        ts = [r["t_total"] if r else 0 for r in found]
        # Bytes: a failed run or a missing counter has no bar, and says so;
        # a measured zero is drawn as one byte (the log scale has no zero).
        bs = [max(r["bytes_tx"], 1) if r and r["bytes_tx"] is not None else 0 for r in found]
        ax1.bar(xs, ts, width, label=mode)
        ax2.bar(xs, bs, width, label=mode)
        for x, r in zip(xs, found):
            if r is None:
                ax1.annotate("failed", (x, 0), fontsize=6, ha="center", va="bottom", color="C3", rotation=90)
                ax2.annotate("failed", (x, 1), fontsize=6, ha="center", va="bottom", color="C3", rotation=90)
            elif r["bytes_tx"] is None:
                ax2.annotate("no counter", (x, 1), fontsize=6, ha="center", va="bottom", color="C3", rotation=90)
        if mode == "download+local":
            tr = [r["t_transfer"] or 0 if r else 0 for r in found]
            ax1.bar(xs, tr, width, color="0.3", label="of which transfer")
    if failed:
        ax1.set_title(f"{len(failed)} failed run(s) marked", fontsize=6, color="C3")
    for ax in (ax1, ax2):
        ax.set_xticks(range(len(datasets)))
        ax.set_xticklabels([ds.replace("tb-cube-", "cube ") for ds in datasets])
        ax.grid(axis="y", alpha=0.3)
    ax1.set_ylabel("seconds to the catalogue")
    ax2.set_ylabel("bytes sent by the data node")
    ax2.set_yscale("log")
    ax1.legend(frameon=False, fontsize=6)
    save(fig, "e5_finder")


def main() -> None:
    fig_routing()
    fig_placement()
    fig_failure()
    fig_bytes()
    fig_finder()


if __name__ == "__main__":
    main()
