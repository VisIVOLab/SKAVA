# Copyright 2024-2026 INAF - Istituto Nazionale di Astrofisica
# SPDX-License-Identifier: Apache-2.0
"""The paper's tables and summary figures, from results/*.json, as LaTeX
snippets in results/tables/ (one file per table, to be ``\\input``) and a
few numbers printed for the text. Like the figures, everything is drawn
from the result files alone: re-running an experiment and this script is
the whole of regenerating a table.

Usage: ``python -m experiments.tables``
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results"
TABLES = RESULTS / "tables"

NODE_ORDER = ["BIG", "SMALL", "FAR", "BUSY"]


def load(name: str) -> dict | None:
    path = RESULTS / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def save(name: str, text: str) -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    (TABLES / f"{name}.tex").write_text(text)
    print("wrote", TABLES / f"{name}.tex")


def cube_label(obs_id: str, size: int | None = None) -> str:
    name = tex(obs_id.replace("tb-cube-", ""))
    return f"{name} ({human(size)})" if size else name


def human(n: float | None) -> str:
    if n is None:
        return "--"
    for unit, scale in (("GB", 1 << 30), ("MB", 1 << 20), ("kB", 1 << 10)):
        if n >= scale:
            value = n / scale
            return f"{value:.1f}\\,{unit}" if value < 10 else f"{value:.0f}\\,{unit}"
    return f"{n:.0f}\\,B"


def seconds(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.2f}" if value < 10 else f"{value:.1f}"


_TEX_SPECIAL = {"\\": "\\textbackslash{}", "&": "\\&", "%": "\\%", "$": "\\$", "#": "\\#", "_": "\\_",
                "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}", "^": "\\textasciicircum{}"}


def tex(text: str) -> str:
    """Text as LaTeX will print it, every special character escaped in one pass."""
    return "".join(_TEX_SPECIAL.get(ch, ch) for ch in str(text))


# ── E2 ──────────────────────────────────────────────────────────────────────

def table_placement() -> None:
    """One row per (cube, node): the three times on every replica, and which
    policy chose that node (or set it aside), so the quality of each
    decision is read against the best replica of the same cube."""
    d = load("e2_placement")
    if not d:
        return
    rows = d["rows"]
    datasets = list(dict.fromkeys(r["dataset"] for r in rows))
    policies = list(dict.fromkeys(r["policy"] for r in rows))
    lines = [
        "\\begin{table*}",
        "\\centering",
        "\\caption{Placement quality on the testbed (paper profile). For each cube, every node holding a replica was "
        "timed on the operations a session begins with (median of %d runs after a warm-up, seconds; for the "
        "moment map also the 95th percentile by nearest rank, which with ten runs is the slowest run, a descriptive "
        "figure and not an estimate of the tail): opening in "
        "place, the first channel slice, and a moment-0 map as a SODA job (the job's own clock on the node). "
        "The policy columns say what each policy did with that replica: \\textbf{chosen}, ranked lower, or set "
        "aside (\\emph{excl.}, with the reason the catalogue gave). A node both policies measured shows the "
        "median of both cells. The best time per cube and operation is in bold@LEGEND@.}" % d["meta"]["repeats"],
        "\\label{tab:placement}",
        "\\small",
        "\\begin{tabular*}{\\linewidth}{@{\\extracolsep{\\fill}}llrrrr" + "l" * len(policies) + "}",
        "\\toprule",
        "Cube & Node & Open & Slice & Moment 0 & p95 & " + " & ".join(p.replace("_", "-") for p in policies) + " \\\\",
        "\\midrule",
    ]
    for ds in datasets:
        mine = [r for r in rows if r["dataset"] == ds]
        nodes = [n for n in NODE_ORDER if any(r["node"] == n for r in mine)]
        size = mine[0]["dataset_bytes"]
        # What the table shows per node (the median over the policies that
        # measured it), then the best of what is shown.
        shown: dict[str, dict[str, float | None]] = {}
        for node in nodes:
            per_policy = [r for r in mine if r["node"] == node]
            shown[node] = {}
            for key in ("t_open", "t_slice", "t_m0"):
                vals = [r[key] for r in per_policy if r[key] is not None]
                shown[node][key] = statistics.median(vals) if vals else None
        best = {key: min((shown[n][key] for n in nodes if shown[n][key] is not None), default=None)
                for key in ("t_open", "t_slice", "t_m0")}
        for i, node in enumerate(nodes):
            by_policy = {r["policy"]: r for r in mine if r["node"] == node}
            cells = []
            for key in ("t_open", "t_slice", "t_m0"):
                v = shown[node][key]
                cell = seconds(v)
                if v is not None and v == best[key]:
                    cell = f"\\textbf{{{cell}}}"
                cells.append(cell)
            p95s = [percentile([x["t_m0"] for x in r.get("samples") or [] if x.get("t_m0") is not None], 95)
                    for r in mine if r["node"] == node]
            p95s = [v for v in p95s if v is not None]
            cells.append(seconds(statistics.median(p95s)) if p95s else "--")
            verdicts = []
            for p in policies:
                r = by_policy.get(p)
                if r is None:
                    verdicts.append("--")
                elif r["chosen"]:
                    verdicts.append("\\textbf{chosen}")
                elif r["rank_reason"].startswith("excluded"):
                    # "excluded: not enough memory: rtt ...": the reason is the
                    # middle part; the telemetry after it is in the JSON.
                    parts = r["rank_reason"].split(":", 2)
                    reason = parts[1].strip() if len(parts) > 1 else "excluded"
                    verdicts.append(f"excl.\\ ({tex(reason)})")
                else:
                    verdicts.append(f"rank {r['rank'] + 1}")
            first = cube_label(ds, size) if i == 0 else ""
            error = any(r["error"] for r in by_policy.values())
            node_cell = f"\\emph{{{tex(node)}}}" + ("$^\\dagger$" if error else "")
            lines.append(f"{first} & {node_cell} & " + " & ".join(cells) + " & " + " & ".join(verdicts) + " \\\\")
        if ds != datasets[-1]:
            lines.append("\\addlinespace")
    lines += ["\\bottomrule", "\\end{tabular*}", "\\end{table*}", ""]
    # The key names a mark only if a rendered row carries it.
    body = "\n".join(lines[lines.index("\\midrule") + 1:])
    legend = "; $\\dagger$ marks a node where a run failed" if "$^\\dagger$" in body else ""
    lines = [line.replace("@LEGEND@", legend) for line in lines]
    save("e2_placement", "\n".join(lines))

    # Numbers for the text: per policy and cube, the chosen node's moment-0
    # time against the best replica's.
    for p in policies:
        for ds in datasets:
            chosen = next((r for r in rows if r["policy"] == p and r["dataset"] == ds and r["chosen"]), None)
            best = min((r["t_m0"] for r in rows if r["dataset"] == ds and r["t_m0"] is not None), default=None)
            if chosen and chosen["t_m0"] is not None and best:
                print(f"E2 {p:15s} {ds}: chose {chosen['node']} m0 {chosen['t_m0']} s (best {best} s, "
                      f"x{chosen['t_m0'] / best:.1f}); worst run {chosen.get('t_m0_max')} s, "
                      f"warm-up {(chosen.get('warmup') or {}).get('t_m0_wall')} s, cell {chosen.get('cell_seconds')} s")
    # The erratic cells: where one run or the warm-up took far longer than the median.
    for r in rows:
        worst = max([x for x in (r.get("t_m0_max"), (r.get("warmup") or {}).get("t_m0_wall")) if x is not None],
                    default=None)
        if worst and r["t_m0_wall"] and worst > 3 * r["t_m0_wall"]:
            print(f"E2 erratic: {r['policy']} {r['dataset']} on {r['node']}: median {r['t_m0_wall']} s, "
                  f"worst {worst} s, cell {r.get('cell_seconds')} s")


def percentile(values: list[float], q: float) -> float | None:
    """The q-th percentile by nearest rank (no interpolation), an observed
    value: with 10 runs the 95th is the slowest run."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, -(-len(ordered) * q // 100) - 1))
    return ordered[int(index)]


def table_baselines() -> None:
    """tab:baselines: what simpler dynamic policies would have chosen, read on
    the same measurements. The resource-aware run timed every replica and
    recorded the telemetry each decision saw (round trip, CPU pressure), so a
    latency-only, a CPU-only and a random choice can be evaluated on the very
    times and telemetry the resource-aware policy had, not on another run."""
    import re
    d = load("e2_placement")
    if not d:
        return
    rows = [r for r in d["rows"] if r["policy"] == "resource_aware" and r["t_m0"] is not None]
    static_rows = [r for r in d["rows"] if r["policy"] == "static" and r["chosen"]]
    datasets = list(dict.fromkeys(r["dataset"] for r in rows))

    def telemetry(r):
        rtt = re.search(r"rtt ([\d.]+) ms", r["rank_reason"])
        cpu = re.search(r"cpu pressure (\d+)%", r["rank_reason"])
        return (float(rtt.group(1)) if rtt else None, float(cpu.group(1)) if cpu else None)

    RTT_TIE_MS, CPU_TIE_PCT = 1.0, 5.0       # below these the probe cannot tell nodes apart
    choices: dict[str, dict[str, list[str]]] = {}
    for ds in datasets:
        mine = {r["node"]: r for r in rows if r["dataset"] == ds}
        tel = {n: telemetry(r) for n, r in mine.items()}
        rtts = {n: v[0] for n, v in tel.items() if v[0] is not None}
        cpus = {n: v[1] for n, v in tel.items() if v[1] is not None}
        choices[ds] = {
            "static (declared scores)": [r["node"] for r in static_rows if r["dataset"] == ds],
            "latency only": [n for n, v in rtts.items() if v - min(rtts.values()) <= RTT_TIE_MS],
            "CPU pressure only": [n for n, v in cpus.items() if v - min(cpus.values()) <= CPU_TIE_PCT],
            "random replica": list(mine),
            "resource-aware": [r["node"] for r in mine.values() if r["chosen"]],
        }
    policies = list(next(iter(choices.values())))

    # The time of a node is the one Table~tab:placement shows: the median over
    # the policies that measured it, so the two tables read the same numbers.
    def shown(ds, node, key):
        vals = [r[key] for r in d["rows"] if r["dataset"] == ds and r["node"] == node and r[key] is not None]
        return statistics.median(vals) if vals else None

    def cell(ds, nodes, key):
        vals = [v for v in (shown(ds, n, key) for n in nodes) if v is not None]
        return statistics.mean(vals) if vals else None

    best = {(ds, k): min(v for v in (shown(ds, r["node"], k) for r in rows if r["dataset"] == ds) if v is not None)
            for ds in datasets for k in ("t_slice", "t_m0")}
    lines = [
        "\\begin{table*}",
        "\\centering",
        "\\caption{Counterfactual policy evaluation on recorded telemetry: the node each policy would have "
        "chosen for each cube from the telemetry the resource-aware run recorded at its decision, and that "
        "node's first-slice and moment-0 times as Table~\\ref{tab:placement} gives them (seconds, median of %d "
        "runs). The simpler policies were not run; their choices are read off the same recorded state. "
        "Nodes within %.0f\\,ms of round trip or %.0f\\%% of CPU pressure cannot be told apart by the probe; where a "
        "policy ties several nodes, or picks at random, the time is the mean over them (the expected cost). The static "
        "row is the static policy's own choice; the memory filter applies to the resource-aware row only.}"
        % (d["meta"]["repeats"], RTT_TIE_MS, CPU_TIE_PCT),
        "\\label{tab:baselines}",
        "\\small",
        "\\begin{tabular*}{\\linewidth}{@{\\extracolsep{\\fill}}l" + "lrr" * len(datasets) + "}",
        "\\toprule",
        " & " + " & ".join(f"\\multicolumn{{3}}{{c}}{{{cube_label(ds, rows[[r['dataset'] for r in rows].index(ds)]['dataset_bytes'])}}}"
                           for ds in datasets) + " \\\\",
        "Policy & " + " & ".join("Node & Slice & M0" for _ in datasets) + " \\\\",
        "\\midrule",
    ]
    for pol in policies:
        cells = []
        for ds in datasets:
            nodes = choices[ds][pol]
            label = ", ".join(f"\\emph{{{tex(n)}}}" for n in nodes) if len(nodes) < 3 else "any"
            vals = []
            for key in ("t_slice", "t_m0"):
                v = cell(ds, nodes, key)
                text = seconds(v)
                if v is not None and abs(v - best[(ds, key)]) < 1e-9:
                    text = f"\\textbf{{{text}}}"
                vals.append(text)
            cells.append(f"{label} & " + " & ".join(vals))
        lines.append(f"{pol} & " + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular*}", "\\end{table*}", ""]
    save("e2_baselines", "\n".join(lines))
    for pol in policies:
        print("E2 baseline", pol, {ds: (choices[ds][pol], round(cell(ds, choices[ds][pol], "t_m0") or 0, 3),
                                        round(cell(ds, choices[ds][pol], "t_slice") or 0, 3)) for ds in datasets})


# ── E3 ──────────────────────────────────────────────────────────────────────

def summary_failure() -> None:
    d = load("e3_failure")
    if not d:
        return
    rows = d["rows"]
    ok = [r for r in rows if r["success"]]

    def med(key: str) -> str:
        vals = [r[key] for r in rows if r[key] is not None]
        if not vals:
            return "--"
        return f"{statistics.median(vals):.2f} (range {min(vals):.2f}--{max(vals):.2f})"

    text = (f"E3: {len(ok)}/{len(rows)} trials resumed on {sorted({r['fallback_node'] for r in ok})}; "
            f"client fallback {med('t_client_fallback')} s; SKAVA detection {med('t_skava_detect')} s; "
            f"ranked again {med('t_skava_recover')} s; attempts {sorted({r['attempts'] for r in rows})}")
    print(text)
    save("e3_summary", "% " + text + "\n")


# ── E4 ──────────────────────────────────────────────────────────────────────

def _bytes_legend(body: str) -> str:
    """The caption's key to the marks, naming only those the rendered rows use."""
    parts = []
    if "$^\\dagger$" in body:
        parts.append("$\\dagger$ marks an operation whose product could not be opened in place (the bytes are "
                     "those of the operation alone)")
    if any(cell.strip() == "--" for line in body.splitlines() for cell in line.rstrip(" \\\\").split("&")):
        parts.append("a dash a counter that could not be read")
    if not parts:
        return ""
    text = "; ".join(parts)
    return " " + text[0].upper() + text[1:] + "."


def table_bytes() -> None:
    d = load("e4_bytes")
    if not d:
        return
    rows = d["rows"]
    datasets = list(dict.fromkeys(r["dataset"] for r in rows))
    ops = ["download", "open+preview", "cutout+open", "moment0+open", "finder+catalogue"]
    labels = {"download": "download", "open+preview": "open + first look", "cutout+open": "cutout + look",
              "moment0+open": "moment 0 + look", "finder+catalogue": "finder + catalogue"}
    lines = [
        "\\begin{table*}",
        "\\centering",
        "\\caption{Bytes sent by the data node's link per operation (kernel counters, paper profile): the big "
        "node for the download and the SODA operations, the node the broker placed the job on for the finder. "
        "The product's size in the node's workspace is in parentheses where one is made.@LEGEND@}",
        "\\label{tab:bytes-measured}",
        "\\small",
        "\\begin{tabular*}{\\linewidth}{@{\\extracolsep{\\fill}}l" + "r" * len(ops) + "}",
        "\\toprule",
        "Cube & " + " & ".join(labels[o] for o in ops) + " \\\\",
        "\\midrule",
    ]
    for ds in datasets:
        mine = {r["operation"]: r for r in rows if r["dataset"] == ds}
        cells = []
        for op in ops:
            r = mine.get(op)
            if r is None or r.get("bytes_tx") is None:
                cells.append("--")
                continue
            cell = human(r["bytes_tx"])
            if not r.get("complete", True):
                cell += "$^\\dagger$"
            if r.get("product_bytes"):
                cell += f" ({human(r['product_bytes'])})"
            cells.append(cell)
        lines.append(f"{cube_label(ds, mine[next(iter(mine))]['file_bytes'])} & " + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular*}", "\\end{table*}", ""]
    body = "\n".join(lines[lines.index("\\midrule") + 1:])
    lines = [line.replace("@LEGEND@", _bytes_legend(body)) for line in lines]
    save("e4_bytes", "\n".join(lines))
    for ds in datasets:
        mine = {r["operation"]: r for r in rows if r["dataset"] == ds}
        dl = mine.get("download", {}).get("bytes_tx")
        whole = all(o in mine and mine[o].get("complete", True) and mine[o].get("bytes_tx") is not None for o in ops)
        if dl and whole:
            session = sum(mine[o]["bytes_tx"] for o in ops[1:])
            print(f"E4 {ds}: download {dl:,} B; the four operations together {session:,} B "
                  f"(x{dl / max(session, 1):.0f} less)")
        else:
            print(f"E4 {ds}: no session total, incomplete or unread: "
                  f"{[o for o in ops if o not in mine or not mine[o].get('complete', True) or mine[o].get('bytes_tx') is None]}")


# ── E5 ──────────────────────────────────────────────────────────────────────

def table_finder() -> None:
    d = load("e5_finder")
    if not d:
        return
    rows = d["rows"]
    datasets = list(dict.fromkeys(r["dataset"] for r in rows))
    lines = [
        "\\begin{table*}",
        "\\centering",
        "\\caption{SoFiA-2 on each cube (same threshold), through the broker on the node it was placed on, and "
        "by a client that pulled the cube and ran it under the big node's limits (%s CPUs, %s). Seconds from the "
        "submission to the catalogue; the transfer and the run are the client's own clocks; bytes are what the "
        "data node's link sent. A run that failed is marked.}" % (d["meta"]["client_cpus"], d["meta"]["client_memory"]),
        "\\label{tab:finder}",
        "\\small",
        "\\begin{tabular*}{\\linewidth}{@{\\extracolsep{\\fill}}llrrrrr}",
        "\\toprule",
        "Cube & Mode & Placed on & Total (s) & Transfer (s) & Finder (s) & Bytes sent \\\\",
        "\\midrule",
    ]
    for ds in datasets:
        mine = [r for r in rows if r["dataset"] == ds]
        for i, r in enumerate(mine):
            first = cube_label(ds, r["file_bytes"]) if i == 0 else ""
            mode = "broker" if r["mode"] == "broker" else "download + local"
            node = f"\\emph{{{tex(r['node'])}}}" if r["mode"] == "broker" else "client"
            if r["error"]:
                lines.append(f"{first} & {mode} & {node} & \\multicolumn{{4}}{{l}}{{failed: {tex(r['error'][:60])}}} \\\\")
                continue
            lines.append(f"{first} & {mode} & {node} & {seconds(r['t_total'])} & {seconds(r['t_transfer'])} & "
                         f"{seconds(r['t_worker'])} & {human(r['bytes_tx'])} \\\\")
        if ds != datasets[-1]:
            lines.append("\\addlinespace")
    lines += ["\\bottomrule", "\\end{tabular*}", "\\end{table*}", ""]
    save("e5_finder", "\n".join(lines))
    for ds in datasets:
        mine = {r["mode"]: r for r in rows if r["dataset"] == ds}
        b, l = mine.get("broker"), mine.get("download+local")
        if b and l and not b["error"] and not l["error"]:
            def count(v):
                return f"{v:,}" if v is not None else "unknown"
            print(f"E5 {ds}: broker {b['t_total']} s on {b['node']} vs local {l['t_total']} s "
                  f"(transfer {l['t_transfer']} s); bytes {count(b['bytes_tx'])} vs {count(l['bytes_tx'])}; "
                  f"sources {b['n_sources']} vs {l['n_sources']}")


# ── E1 prober ───────────────────────────────────────────────────────────────

def summary_prober() -> None:
    d = load("e1_prober")
    if not d:
        return
    for r in d["rows"]:
        if r.get("p50_ms") is None:
            print(f"E1 prober {r['what']:12s} " + ", ".join(f"{k} {v}" for k, v in r.items()
                                                            if k not in ("what", "dataset", "policy", "p50_ms",
                                                                         "p95_ms", "mean_ms") and v is not None))
            continue
        print(f"E1 prober {r['what']:12s} {r.get('dataset') or '':10s} {r.get('policy') or '':15s} "
              f"p50 {r['p50_ms']} ms p95 {r['p95_ms']} ms ({r['requests']} requests)")


def table_federation() -> None:
    """tab:federation: what the federated search costs next to the local one,
    and what it does when the second site is down; every row is printed for
    the text."""
    d = load("e6_federation")
    if not d:
        return
    rows = d["rows"]
    by = {(r["what"], r["case"]): r for r in rows}
    labels = {"local": "local search, first site", "federated": "federated search, signed in",
              "second-site-direct": "second site, asked directly"}
    latency = [(label, by[("latency", case)]) for case, label in labels.items()
               if ("latency", case) in by and by[("latency", case)].get("p50_ms") is not None]
    # A measurement with failed samples is shown as such, never as a plain figure.
    latency = [(label + (f" ({r['failed']} of {r['n']} requests failed)" if r.get("failed") else ""), r)
               for label, r in latency]
    down = by.get(("degraded", "site-down"))
    if down is not None and (down.get("request_ms_p50") is None or not down.get("ok", True)):
        down = None
    if not latency and down is None:
        # Nothing usable: a previous run's table must not survive this one.
        save("e6_federation", "% E6: no usable measurements in results/e6_federation.json\n")
        for r in rows:
            print("E6 " + " ".join(f"{k}={v}" for k, v in r.items()))
        return
    counts = sorted({r["n"] for _l, r in latency})
    per = f"{counts[0]} requests each" if len(counts) == 1 else "a different number of requests each"
    caption = (f"E6: the federated search next to the local one ({per}, \\texttt{{limit=100}}; "
               "the second site validates the caller's token)"
               + (", and the federated search with the second site stopped (the first site answers alone, "
                  "within the federation timeout)." if down else "."))
    ms = lambda v: f"{v:.1f} ms" if v < 1000 else f"{v / 1000:.2f} s"   # noqa: E731
    lines = [r"\begin{table}[t]", r"\centering", r"\caption{" + caption + "}", r"\label{tab:federation}",
             r"\small", r"\begin{tabular}{@{}lrr@{}}", r"\toprule", r"Request & p50 & p95 \\", r"\midrule"]
    for label, r in latency:
        lines.append(f"{tex(label)} & {ms(r['p50_ms'])} & {ms(r['p95_ms'])} \\\\")
    if down:
        lines.append(f"{tex('federated, second site down')} & {ms(down['request_ms_p50'])} & "
                     f"{ms(down['request_ms_max'])}$^{{*}}$ \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    if down:
        lines.append(r"\\[2pt]{\footnotesize $^{*}$the slowest of " + str(down["trials"]) + " requests.}")
    lines += [r"\end{table}", ""]
    save("e6_federation", "\n".join(lines))
    for r in rows:
        print("E6 " + " ".join(f"{k}={v}" for k, v in r.items()))


def main() -> None:
    table_placement()
    table_baselines()
    summary_failure()
    table_bytes()
    table_finder()
    summary_prober()
    table_federation()


if __name__ == "__main__":
    main()
