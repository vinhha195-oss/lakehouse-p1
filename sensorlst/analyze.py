"""Aggregate run JSONs into tables and paper figures.

    python -m sensorlst.analyze results/runs --out results/report
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Fixed categorical order (validated reference palette, slots 1-4); mode is a secondary encoding (line style / hatch).
COLORS = {"delta": "#2a78d6", "iceberg": "#eb6834", "hudi": "#1baf7a", "parquet": "#eda100"}
STYLE = {"cow": "-", "mor": "--"}
HATCH = {"cow": "", "mor": "///"}
FMT_ORDER = ["delta", "iceberg", "hudi", "parquet"]
QUERIES = ["Q1_window_agg", "Q2_topk", "Q3_join", "Q4_range", "Q5_scan"]
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "legend.fontsize": 7,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "lines.linewidth": 1.6, "lines.markersize": 4, "figure.dpi": 150,
})


def label(fmt, mode):
    if fmt == "parquet":
        return "Parquet (rewrite)"
    m = {"delta": {"cow": "CoW", "mor": "DV"}}.get(fmt, {"cow": "CoW", "mor": "MoR"})[mode]
    return f"{fmt.capitalize()} {m}"


def load(run_dir: str):
    runs, cps, ops = [], [], []
    for p in sorted(glob.glob(os.path.join(run_dir, "*.json"))):
        r = json.load(open(p))
        c = r["config"]
        key = {"run_id": r["run_id"], "fmt": c["fmt"], "mode": c["mode"], "u": c["u"],
               "c": c["compact_every"], "rep": c["rep"], "shard": os.path.basename(os.path.normpath(run_dir)),
               "calibration": bool((c.get("tags") or {}).get("calibration"))}
        last = r["checkpoints"][-1]
        q_all = sum(sum(x[1] for x in cp["queries"].values()) for cp in r["checkpoints"])
        runs.append({**key, "correct": r["correct"], "write_s": r["total_write_s"],
                     "compact_s": r["total_compact_s"], "query_s": q_all,
                     "total_s": r["total_write_s"] + r["total_compact_s"] + q_all,
                     "wa": r["write_amplification"], "logical_mb": r["logical_bytes"] / 2**20,
                     "live_files": last["data_files"], "delta_files": last["delete_files"],
                     "meta_kb": last["meta_bytes_on_disk"] / 1024, "meta_files": last["meta_files_on_disk"],
                     "n_versions": last.get("n_versions"),
                     "final_q_s": sum(v[1] for v in last["queries"].values()),
                     **{f"final_{q}": last["queries"][q][1] for q in QUERIES},
                     "tt_back_s": last.get("time_travel", {}).get("tt_back", {}).get("seconds"),
                     "tt_first_s": last.get("time_travel", {}).get("tt_first", {}).get("seconds"),
                     "jvm_s": r["jvm_start_s"], "cpus": r["host"]["cpus"]})
        for cp in r["checkpoints"]:
            cps.append({**key, "batch": cp["batch"], "q_warm_s": sum(v[1] for v in cp["queries"].values()),
                        "q_cold_s": sum(v[0] for v in cp["queries"].values()),
                        "live_files": cp["data_files"], "delta_files": cp["delete_files"],
                        "meta_kb": cp["meta_bytes_on_disk"] / 1024, "n_versions": cp.get("n_versions"),
                        "tt_back_s": cp.get("time_travel", {}).get("tt_back", {}).get("seconds"),
                        "tt_first_s": cp.get("time_travel", {}).get("tt_first", {}).get("seconds"),
                        "correct": cp["correct"]})
        for o in r["ops"]:
            ops.append({**key, **o})
    return pd.DataFrame(runs), pd.DataFrame(cps), pd.DataFrame(ops)


def p95(x):
    return np.percentile(x, 95)


def cv(x):
    return float(np.std(x, ddof=1) / np.mean(x)) if len(x) > 1 and np.mean(x) else np.nan


def summarise(runs: pd.DataFrame) -> pd.DataFrame:
    g = runs.groupby(["fmt", "mode", "u", "c"])
    s = g.agg(n=("rep", "count"), all_correct=("correct", "all"),
              write_s=("write_s", "median"), compact_s=("compact_s", "median"),
              query_s=("query_s", "median"), total_s=("total_s", "median"),
              total_s_p95=("total_s", p95), total_cv=("total_s", cv),
              final_q_s=("final_q_s", "median"), final_q_p95=("final_q_s", p95),
              wa=("wa", "median"), live_files=("live_files", "median"), delta_files=("delta_files", "median"),
              meta_kb=("meta_kb", "median"), n_versions=("n_versions", "median"),
              tt_back_s=("tt_back_s", "median"), tt_first_s=("tt_first_s", "median"))
    return s.reset_index()


def degradation(cps: pd.DataFrame) -> pd.DataFrame:
    """LST-Bench-style degradation rate: relative growth of warm query time from first to last checkpoint."""
    def rate(df):
        df = df.sort_values("batch")
        return (df.q_warm_s.iloc[-1] - df.q_warm_s.iloc[0]) / df.q_warm_s.iloc[0]
    d = cps.groupby(["fmt", "mode", "u", "c", "rep"]).apply(rate, include_groups=False).rename("degradation")
    return d.reset_index().groupby(["fmt", "mode", "u", "c"]).degradation.median().reset_index()


def _series(s):
    for fmt in FMT_ORDER:
        for mode in ("cow", "mor"):
            d = s[(s.fmt == fmt) & (s["mode"] == mode)]
            if len(d):
                yield fmt, mode, d


def _legend(fig, axes, ncol, y):
    """One legend for the figure, from every subplot, in the fixed series order."""
    seen = {}
    for ax in np.ravel(axes):
        for h, l in zip(*ax.get_legend_handles_labels()):
            seen.setdefault(l, h)
    order = list(dict.fromkeys(label(f, m) for f in FMT_ORDER for m in ("cow", "mor")))
    labels = [l for l in order if l in seen]
    fig.legend([seen[l] for l in labels], labels, loc="lower center", ncol=ncol, frameon=False,
               bbox_to_anchor=(0.5, y))


def fig_rq1(s, out):
    cs = sorted(s.c.unique())
    us = sorted(s.u.unique())  # evenly spaced categories: the step from 0% to 1% is where the cost changes
    fig, axes = plt.subplots(1, len(cs), figsize=(2.4 * len(cs) + 0.4, 2.4), sharey=True, squeeze=False)
    for ax, c in zip(axes[0], cs):
        sc = s[(s.c == c) | ((s.fmt == "parquet") & (s.c == 0))]
        for fmt, mode, d in _series(sc):
            d = d.sort_values("u")
            ax.plot([us.index(v) for v in d.u], d.total_s, STYLE[mode], color=COLORS[fmt], marker="o",
                    label=label(fmt, mode))
        ax.set_xticks(range(len(us)), [f"{v * 100:g}" for v in us])
        ax.set_title("no compaction" if c == 0 else f"compaction every {c} batches")
        ax.set_xlabel("late-update rate u (%)")
    axes[0][0].set_ylabel("total cost (s): ingest + compaction + queries")
    _legend(fig, axes, 4, -0.16)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_rq1_total_cost.png"), bbox_inches="tight")
    plt.close(fig)


def fig_write_amp(s, out):
    sc = s[s.c == 0]
    us = sorted(sc.u.unique())
    groups = [(f, m) for f, m, _ in _series(sc)]
    fig, ax = plt.subplots(figsize=(5.2, 2.3))
    w = 0.8 / max(1, len(groups))
    for i, (fmt, mode) in enumerate(groups):
        d = sc[(sc.fmt == fmt) & (sc["mode"] == mode)].set_index("u").reindex(us)
        ax.bar(np.arange(len(us)) + i * w, d.wa, w * 0.92, color=COLORS[fmt], hatch=HATCH[mode],
               edgecolor="white", linewidth=0.5, label=label(fmt, mode))
    ax.set_xticks(np.arange(len(us)) + w * (len(groups) - 1) / 2, [f"u={u * 100:g}%" for u in us])
    ax.set_ylabel("write amplification\n(bytes written / logical bytes)")
    ax.legend(ncol=4, frameon=False, loc="upper left", bbox_to_anchor=(0, 1.25))
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_write_amplification.png"), bbox_inches="tight")
    plt.close(fig)


def fig_rq2(s, cps, out):
    u = s.u.max()
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.4))
    for fmt, mode, d in _series(s[s.u == u]):
        d = d.sort_values("c")
        x = [str(c) if c else "never" for c in d.c]
        axes[0].plot(x, d.final_q_s, STYLE[mode], color=COLORS[fmt], marker="o", label=label(fmt, mode))
        axes[1].plot(x, d.live_files + d.delta_files, STYLE[mode], color=COLORS[fmt], marker="o", label=label(fmt, mode))
    axes[0].set_ylabel("Q1-Q5 latency at end (s, warm)")
    axes[1].set_ylabel("live files (data + delete/log)")
    for ax in axes:
        ax.set_xlabel("compaction every k batches")
    axes[0].set_title(f"read cost vs compaction (u={u * 100:g}%)")
    axes[1].set_title("small-file count at end")
    _legend(fig, axes, 4, -0.2)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_rq2_compaction.png"), bbox_inches="tight")
    plt.close(fig)

    # read-latency trajectory without compaction (degradation)
    d0 = cps[(cps.c == 0) & (cps.u == u)].groupby(["fmt", "mode", "batch"]).q_warm_s.median().reset_index()
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    for fmt, mode, d in _series(d0):
        ax.plot(d.batch, d.q_warm_s, STYLE[mode], color=COLORS[fmt], marker="o", label=label(fmt, mode))
    ax.set_xlabel("micro-batches committed")
    ax.set_ylabel("Q1-Q5 latency (s, warm)")
    ax.set_title(f"read degradation, no compaction (u={u * 100:g}%)")
    _legend(fig, [ax], 2, -0.32)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_rq2_degradation.png"), bbox_inches="tight")
    plt.close(fig)


def fig_rq3(cps, out):
    d = cps[(cps.c == 0) & cps.n_versions.notna()]
    u = d.u.max()
    d = d[d.u == u].groupby(["fmt", "mode", "batch"])[["meta_kb", "n_versions", "tt_back_s", "tt_first_s"]] \
        .median().reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.4))
    for fmt, mode, g in _series(d):
        axes[0].plot(g.batch, g.meta_kb / 1024, STYLE[mode], color=COLORS[fmt], marker="o", label=label(fmt, mode))
        axes[1].plot(g.batch, g.tt_back_s, STYLE[mode], color=COLORS[fmt], marker="o", label=label(fmt, mode))
    axes[0].set_xlabel("micro-batches committed")
    axes[0].set_ylabel("metadata on disk (MB)")
    axes[1].set_xlabel("micro-batches committed")
    axes[1].set_ylabel("time travel to T-5 (s)")
    axes[0].set_title(f"metadata growth (u={u * 100:g}%, no compaction)")
    axes[1].set_title("time-travel latency")
    _legend(fig, axes, 3, -0.2)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_rq3_metadata.png"), bbox_inches="tight")
    plt.close(fig)


def fig_ops(ops, out):
    """Median latency per operation type (u=20%; ingest/delete without compaction, compaction over both cadences)."""
    u = ops.u.max()
    d = ops[ops.u == u]
    kinds = [("upsert", "upsert / MERGE"), ("delete", "station-day delete"), ("compact", "compaction")]
    groups = [(f, m) for f in FMT_ORDER for m in ("cow", "mor") if len(d[(d.fmt == f) & (d["mode"] == m)])]
    fig, ax = plt.subplots(figsize=(6.4, 2.4))
    w = 0.8 / len(groups)
    for i, (fmt, mode) in enumerate(groups):
        g = d[(d.fmt == fmt) & (d["mode"] == mode)]
        vals = [g[(g.op == k) & ((g.c == 0) if k != "compact" else (g.c > 0))].seconds.median() for k, _ in kinds]
        ax.bar(np.arange(len(kinds)) + i * w, vals, w * 0.92, color=COLORS[fmt], hatch=HATCH[mode],
               edgecolor="white", linewidth=0.5, label=label(fmt, mode))
    ax.set_xticks(np.arange(len(kinds)) + w * (len(groups) - 1) / 2, [k[1] for k in kinds])
    ax.set_ylabel("median latency per operation (s)")
    ax.set_title(f"cost of one operation (u={u * 100:g}%)")
    _legend(fig, [ax], 4, -0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_ops.png"), bbox_inches="tight")
    plt.close(fig)


def fig_ingest_trend(ops, out):
    """Per-batch ingest latency over the run, no compaction: does ingest slow down as the table grows?"""
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.4), sharey=False)
    for ax, (u, op) in zip(axes, ((0.0, "append"), (ops.u.max(), "upsert"))):
        d = ops[(ops.u == u) & (ops.c == 0) & (ops.op == op)].groupby(["fmt", "mode", "batch"]).seconds             .median().reset_index()
        for fmt, mode, g in _series(d):
            ax.plot(g.batch, g.seconds.rolling(5, min_periods=1).mean(), STYLE[mode], color=COLORS[fmt],
                    label=label(fmt, mode), linewidth=1.4)
        ax.set_xlabel("micro-batch")
        ax.set_title(f"{op} latency, u={u * 100:g}% (5-batch mean)")
    axes[0].set_ylabel("seconds per batch")
    _legend(fig, axes, 4, -0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_ingest_trend.png"), bbox_inches="tight")
    plt.close(fig)


def fig_variability(runs, raw, out):
    """Left: every repetition at u=20% (no compaction); right: calibration runs per VM (raw seconds)."""
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.4), gridspec_kw={"width_ratios": [2.2, 1]})
    u = runs.u.max()
    d = runs[(runs.u == u) & (runs.c == 0)]
    groups = [(f, m) for f in FMT_ORDER for m in ("cow", "mor") if len(d[(d.fmt == f) & (d["mode"] == m)])]
    for i, (fmt, mode) in enumerate(groups):
        v = d[(d.fmt == fmt) & (d["mode"] == mode)].total_s.to_numpy()
        axes[0].scatter(np.full(len(v), i) + np.linspace(-0.12, 0.12, len(v)), v, s=14, color=COLORS[fmt],
                        marker="o" if mode == "cow" else "D", zorder=3)
        axes[0].hlines(np.median(v), i - 0.25, i + 0.25, color=INK, linewidth=1)
    axes[0].set_xticks(range(len(groups)), [label(f, m).replace(" (rewrite)", "") for f, m in groups],
                       rotation=35, ha="right")
    axes[0].set_ylabel("total cost per run (s)")
    axes[0].set_title(f"3 repetitions, u={u * 100:g}%, no compaction")
    cal = raw[raw.calibration | ((raw.fmt == "delta") & (raw["mode"] == "cow") & (raw.u == 0) & (raw.c == 0))]
    shards = sorted(cal.shard.unique())
    for i, sh in enumerate(shards):
        v = cal[cal.shard == sh].total_s.to_numpy()
        axes[1].scatter(np.full(len(v), i) + np.linspace(-0.1, 0.1, len(v)), v, s=14, color=COLORS["delta"], zorder=3)
        axes[1].hlines(np.median(v), i - 0.25, i + 0.25, color=INK, linewidth=1)
    axes[1].set_xticks(range(len(shards)), [s.replace("runs_", "VM ") for s in shards], rotation=35, ha="right")
    axes[1].set_ylabel("Delta CoW, u=0 (s, raw)")
    axes[1].set_title("same config, 4 VMs")
    axes[1].set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_variability.png"), bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", default="results/report")
    ap.add_argument("--raw-times", action="store_true", help="do not normalise durations by machine factor")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    parts = [load(r) for r in args.runs]
    runs, cps, ops = (pd.concat([p[i] for p in parts], ignore_index=True) for i in range(3))
    # Calibration repeats (Delta CoW, u=0) measure machine-to-machine variation across shards; keep them out of
    # the main comparison, which uses only each configuration's own shard.
    calib = runs[runs.calibration | (runs.run_id.isin(runs[runs.calibration].run_id) & (runs.u == 0))]
    runs.to_csv(os.path.join(args.out, "runs_raw.csv"), index=False)
    raw = runs.copy()
    factor = {}
    if len(calib):
        calib.groupby("shard")[["write_s", "query_s", "total_s", "jvm_s"]].agg(["median", "count"]) \
            .to_csv(os.path.join(args.out, "calibration_by_shard.csv"))
        # Reference machine = the shard whose own matrix contains the calibration config (u = 0).
        ref_shard = runs[(runs.u == 0) & ~runs.calibration].shard.mode().iat[0]
        med = calib.groupby("shard").total_s.median()
        factor = (med / med[ref_shard]).to_dict()
        pd.Series(factor, name="slowdown_vs_reference").to_csv(os.path.join(args.out, "machine_factor.csv"))
    runs, cps, ops = (d[~d.calibration].reset_index(drop=True) for d in (runs, cps, ops))
    # Express every duration in reference-machine seconds, so that update rates run on different VMs compare.
    if factor and not args.raw_times:
        tcols = {"runs": [c for c in runs.columns if c.endswith("_s") or c.startswith("final_Q")],
                 "cps": ["q_warm_s", "q_cold_s", "tt_back_s", "tt_first_s"], "ops": ["seconds"]}
        for name, d in (("runs", runs), ("cps", cps), ("ops", ops)):
            f = d.shard.map(factor).fillna(1.0)
            for col in tcols[name]:
                d[col] = d[col] / f
    runs.to_csv(os.path.join(args.out, "runs.csv"), index=False)
    cps.to_csv(os.path.join(args.out, "checkpoints.csv"), index=False)
    ops.to_csv(os.path.join(args.out, "ops.csv"), index=False)
    s = summarise(runs).merge(degradation(cps), on=["fmt", "mode", "u", "c"], how="left")
    s.to_csv(os.path.join(args.out, "summary.csv"), index=False)
    op_s = ops.groupby(["fmt", "mode", "u", "op"]).seconds.median().unstack("op").reset_index()
    op_s.to_csv(os.path.join(args.out, "op_latency_median.csv"), index=False)

    fig_rq1(s, args.out)
    fig_write_amp(s, args.out)
    fig_rq2(s, cps, args.out)
    fig_rq3(cps, args.out)
    fig_ops(ops, args.out)
    fig_ingest_trend(ops, args.out)
    fig_variability(runs, raw, args.out)
    q = [c for c in runs.columns if c.startswith("final_Q")]
    runs.groupby(["fmt", "mode", "u", "c"])[q].median().reset_index()         .to_csv(os.path.join(args.out, "per_query_final.csv"), index=False)
    cps[cps.batch == cps.batch.max()].groupby(["fmt", "mode", "u", "c"])[["q_cold_s", "q_warm_s"]].median()         .reset_index().to_csv(os.path.join(args.out, "cold_warm_final.csv"), index=False)

    with open(os.path.join(args.out, "summary.md"), "w", encoding="utf-8") as f:
        f.write(f"runs: {len(runs)}, all correct: {bool(runs.correct.all())}\n\n")
        f.write(s.round(3).to_markdown(index=False))
    print(f"{len(runs)} runs, correct={runs.correct.all()} -> {args.out}")


if __name__ == "__main__":
    main()
