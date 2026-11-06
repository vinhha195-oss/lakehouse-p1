"""Extra analyses for the paper, computed from results/report/{runs,runs_raw}.csv.

    python scripts/extra_analysis.py [results/report]

Writes stats_tests.csv, ablation*.csv, breakeven.csv, compaction_tradeoff.csv, read_between_compactions.csv,
appendix_tables.tex and fig_{breakdown,rep_agreement,sawtooth}.png.
Bootstrap and permutation tests work on the per-repetition totals; n = 5 per side, so the exact two-sided rank test
cannot go below p = 0.0079.
"""
import itertools
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sensorlst.analyze import COLORS, FMT_ORDER, INK, MUTED, label  # noqa: E402  (also applies the shared rcParams)

OUT = sys.argv[1] if len(sys.argv) > 1 else "results/report"
runs = pd.read_csv(f"{OUT}/runs.csv")
raw = pd.read_csv(f"{OUT}/runs_raw.csv")
raw = raw[~raw.calibration]
summ = pd.read_csv(f"{OUT}/summary.csv")
LAYOUTS = [("iceberg", "mor"), ("iceberg", "cow"), ("hudi", "mor"), ("hudi", "cow"), ("delta", "cow"), ("delta", "mor"), ("parquet", "cow")]
RATES = [0.0, 0.01, 0.05, 0.2]
rng = np.random.default_rng(42)


def vals(f, m, u, c=0, col="total_s", d=runs):
    return d[(d.fmt == f) & (d["mode"] == m) & (d.u == u) & (d.c == c)][col].to_numpy()


def med(*a, **k):
    return float(np.median(vals(*a, **k)))


def rank_test(a, b):
    """Exact two-sided Mann-Whitney permutation p-value."""
    pooled = np.concatenate([a, b])
    ranks = pd.Series(pooled).rank().to_numpy()
    obs = ranks[: len(a)].sum()
    mean = len(a) * (len(pooled) + 1) / 2
    combos = list(itertools.combinations(range(len(pooled)), len(a)))
    return sum(abs(ranks[list(i)].sum() - mean) >= abs(obs - mean) - 1e-9 for i in combos) / len(combos)


def ratio_ci(a, b, n=20000):
    ra = np.median(rng.choice(a, (n, len(a))), axis=1)
    rb = np.median(rng.choice(b, (n, len(b))), axis=1)
    r = ra / rb
    return float(np.median(a) / np.median(b)), float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))


L = {"iM": ("iceberg", "mor"), "iC": ("iceberg", "cow"), "hM": ("hudi", "mor"), "hC": ("hudi", "cow"), "dC": ("delta", "cow"), "dV": ("delta", "mor"), "pq": ("parquet", "cow")}
tests = []


def test(name, a, b):
    r, lo, hi = ratio_ci(a, b)
    tests.append({"claim": name, "ratio": r, "ci_lo": lo, "ci_hi": hi, "p": rank_test(a, b)})


for u in RATES[1:]:
    test(f"Parquet / Iceberg MoR, total, u={u:g}", vals(*L["pq"], u), vals(*L["iM"], u))
    test(f"Iceberg CoW / Iceberg MoR, total, u={u:g}", vals(*L["iC"], u), vals(*L["iM"], u))
    test(f"Hudi MoR / Iceberg MoR, total, u={u:g}", vals(*L["hM"], u), vals(*L["iM"], u))
    test(f"Delta DV / Delta CoW, ingest, u={u:g}", vals(*L["dV"], u, col="write_s"), vals(*L["dC"], u, col="write_s"))
test("Delta CoW / Hudi CoW, total, u=0.2", vals(*L["dC"], .2), vals(*L["hC"], .2))
for k, n in [("iM", "Iceberg MoR"), ("hM", "Hudi MoR"), ("iC", "Iceberg CoW"), ("hC", "Hudi CoW"), ("dC", "Delta CoW"), ("dV", "Delta DV"), ("pq", "Parquet")]:
    test(f"{n}, total, u=20% / u=1%", vals(*L[k], .2), vals(*L[k], .01))
for k, n in [("iM", "Iceberg MoR"), ("hM", "Hudi MoR")]:
    test(f"{n}, total, every 5 / every 20, u=0.2", vals(*L[k], .2, 5), vals(*L[k], .2, 20))
    test(f"{n}, read, never / every 20, u=0.2", vals(*L[k], .2, 0, "final_q_s"), vals(*L[k], .2, 20, "final_q_s"))
    test(f"{n}, read, every 5 / every 20, u=0.2", vals(*L[k], .2, 5, "final_q_s"), vals(*L[k], .2, 20, "final_q_s"))
t = pd.DataFrame(tests)
t.to_csv(f"{OUT}/stats_tests.csv", index=False)

# Ablation: switch one mechanism off and compare with the same layout where it is on.
abl = []
for k, n in [("iM", "Iceberg MoR"), ("hM", "Hudi MoR"), ("dV", "Delta DV")]:
    for u in RATES[1:]:
        abl.append({"remove": "compaction (every 20 -> never)", "layout": n, "u": u, "total_on": med(*L[k], u, 20), "total_off": med(*L[k], u, 0),
                    "read_on": med(*L[k], u, 20, "final_q_s"), "read_off": med(*L[k], u, 0, "final_q_s")})
for u in RATES[1:]:
    abl.append({"remove": "deletion vectors (DV -> CoW)", "layout": "Delta", "u": u, "total_on": med(*L["dV"], u), "total_off": med(*L["dC"], u),
                "read_on": med(*L["dV"], u, 0, "final_q_s"), "read_off": med(*L["dC"], u, 0, "final_q_s")})
    abl.append({"remove": "position deletes (MoR -> CoW)", "layout": "Iceberg", "u": u, "total_on": med(*L["iM"], u), "total_off": med(*L["iC"], u),
                "read_on": med(*L["iM"], u, 0, "final_q_s"), "read_off": med(*L["iC"], u, 0, "final_q_s")})
pd.DataFrame(abl).to_csv(f"{OUT}/ablation.csv", index=False)
norm = []
for k, n in L.items():
    a = {u: med(*n, u) for u in RATES}
    b = {u: med(*n, u, d=raw) for u in RATES}
    norm.append({"layout": label(*n), "step_norm": a[.01] / a[0], "step_raw": b[.01] / b[0],
                 "spread_norm": max(a[u] for u in RATES[1:]) / min(a[u] for u in RATES[1:]) - 1,
                 "spread_raw": max(b[u] for u in RATES[1:]) / min(b[u] for u in RATES[1:]) - 1})
norm = pd.DataFrame(norm)
norm.to_csv(f"{OUT}/ablation_normalisation.csv", index=False)

# Read latency between compactions. Checkpoints fall on batches 10, 20, 30, 40 and run after that batch's compaction, so
# every "every 20" reading at batches 20 and 40 and every "every 5" reading is taken right after a compaction.
cps = pd.read_csv(f"{OUT}/checkpoints.csv")


def cp_curve(f, m, u, c):
    d = cps[(cps.fmt == f) & (cps["mode"] == m) & (cps.u == u) & (cps.c == c)]
    return d.groupby("batch").q_warm_s.median()


saw = []
for k, n in [("iM", "Iceberg MoR"), ("hM", "Hudi MoR"), ("iC", "Iceberg CoW"), ("hC", "Hudi CoW")]:
    for u in RATES[1:]:
        for c in (0, 5, 20):
            q = cp_curve(*L[k], u, c)
            saw.append({"layout": n, "u": u, "c": c, **{f"b{b}": q[b] for b in q.index}, "mean": q.mean()})
saw = pd.DataFrame(saw)
saw.to_csv(f"{OUT}/read_between_compactions.csv", index=False)

# Break-even: how many Q1-Q5 rounds per 40 batches until the read penalty eats the write saving (mean of the 4 checkpoints).
be = []
for mor, cow, n in [("iM", "iC", "Iceberg"), ("hM", "hC", "Hudi")]:
    for c in (0, 5, 20):
        for u in RATES[1:]:
            w_m = med(*L[mor], u, c, "write_s") + med(*L[mor], u, c, "compact_s")
            w_c = med(*L[cow], u, 0, "write_s")
            q_m, q_c = cp_curve(*L[mor], u, c).mean(), cp_curve(*L[cow], u, 0).mean()
            be.append({"format": n, "c": c, "u": u, "write_saving_s": w_c - w_m, "read_penalty_s": q_m - q_c,
                       "breakeven_rounds": (w_c - w_m) / (q_m - q_c) if q_m > q_c else float("inf")})
be = pd.DataFrame(be)
be.to_csv(f"{OUT}/breakeven.csv", index=False)
trade = []
for k, n in [("iM", "Iceberg MoR"), ("hM", "Hudi MoR")]:
    for u in RATES[1:]:
        extra = med(*L[k], u, 5, "compact_s") - med(*L[k], u, 20, "compact_s")
        gain = cp_curve(*L[k], u, 20).mean() - cp_curve(*L[k], u, 5).mean()
        trade.append({"layout": n, "u": u, "extra_compact_s": extra, "mean_read_gain_s": gain, "rounds_to_repay": extra / gain})
trade = pd.DataFrame(trade)
trade.to_csv(f"{OUT}/compaction_tradeoff.csv", index=False)

# Figure: sawtooth.
fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.7), sharey=True)
shade = {0: "#9a9994", 20: INK, 5: "#b9b8b3"}
for ax, (mor, cow, name, col) in zip(axes, [("iM", "iC", "Iceberg", COLORS["iceberg"]), ("hM", "hC", "Hudi", COLORS["hudi"])]):
    ax.plot(cp_curve(*L[mor], .2, 0), color=col, linestyle="--", marker="D", label="MoR, never")
    ax.plot(cp_curve(*L[mor], .2, 20), color=col, marker="D", label="MoR, every 20")
    ax.plot(cp_curve(*L[mor], .2, 5), color=col, linestyle=":", marker="D", label="MoR, every 5")
    ax.plot(cp_curve(*L[cow], .2, 0), color=MUTED, marker="o", label="CoW, never")
    ax.set_xticks([10, 20, 30, 40])
    ax.set_xlabel("checkpoint (batch)")
    ax.set_title(name)
    ax.legend(frameon=False, fontsize=7, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.24))
    ax.set_ylim(0, 3.2)
axes[0].set_ylabel("warm Q1-Q5 (s)")
fig.tight_layout()
fig.savefig(f"{OUT}/fig_sawtooth.png", bbox_inches="tight", dpi=200)
plt.close(fig)

# Figure: where the time goes.
parts = [("write_s", "ingest", "#2b2b2b"), ("compact_s", "compaction", "#8a8984"), ("query_s", "queries", "#cfcec9")]
fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.5), sharex=True, sharey=True)
order = [x for x in LAYOUTS if x[0] != "parquet"]
for ax, c in zip(axes, (0, 20)):
    for i, (f, m) in enumerate(order):
        left = 0
        for col, name, color in parts:
            w = med(f, m, .2, c, col)
            ax.barh(i, w, left=left, height=0.62, color=color, edgecolor="white", linewidth=1, label=name if i == 0 else None)
            left += w
    ax.set_yticks(range(len(order)), [label(f, m) for f, m in order])
    ax.invert_yaxis() if c == 0 else None
    ax.set_title("no compaction" if c == 0 else "compaction every 20 batches")
    ax.set_xlabel("seconds (median, u = 20%)")
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)
h, lab = axes[0].get_legend_handles_labels()
fig.legend(h, lab, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.55, -0.08))
fig.tight_layout()
fig.savefig(f"{OUT}/fig_breakdown.png", bbox_inches="tight", dpi=200)
plt.close(fig)

# Figure: do the two VM batches agree after normalisation?
r = runs.assign(batch=np.where(runs.rep >= 4, "late", "early"))
g = r.groupby(["fmt", "mode", "u", "c", "batch"]).total_s.median().unstack("batch").reset_index()
g["ratio"] = g.late / g.early
fig, ax = plt.subplots(figsize=(3.4, 3.0))
x = np.array([20, 340])
ax.plot(x, x, color=INK, linewidth=0.8)
ax.fill_between(x, x / 1.15, x * 1.15, color="#e4e3df", linewidth=0, zorder=0, label="within ±15%")
for f in FMT_ORDER:
    for m in ("cow", "mor"):
        d = g[(g.fmt == f) & (g["mode"] == m)]
        if len(d):
            ax.scatter(d.early, d.late, s=16, color=COLORS[f], marker="o" if m == "cow" else "D", edgecolor="white", linewidth=0.4, label=label(f, m), zorder=3)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(20, 340); ax.set_ylim(20, 340)
ax.set_xticks([25, 50, 100, 200], ["25", "50", "100", "200"]); ax.set_yticks([25, 50, 100, 200], ["25", "50", "100", "200"])
ax.minorticks_off()
ax.set_xlabel("median of repetitions 1-3 (s)"); ax.set_ylabel("median of repetitions 4-5 (s)")
ax.legend(frameon=False, fontsize=7, loc="upper left")
fig.tight_layout()
fig.savefig(f"{OUT}/fig_rep_agreement.png", bbox_inches="tight", dpi=200)
plt.close(fig)

# Appendix tables.


def matrix(col, caption, lab, fmt="{:.0f}"):
    head = " & \\multicolumn{3}{c}{$u=0$} & \\multicolumn{3}{c}{$u=1\\%$} & \\multicolumn{3}{c}{$u=5\\%$} & \\multicolumn{3}{c}{$u=20\\%$}\\\\"
    sub = "Layout" + " & $\\infty$ & 5 & 20" * 4 + "\\\\\\midrule"
    rows = []
    for f, m in LAYOUTS:
        cells = []
        for u in RATES:
            for c in (0, 5, 20):
                s = summ[(summ.fmt == f) & (summ["mode"] == m) & (summ.u == u) & (summ.c == c)]
                cells.append(fmt.format(s[col].iat[0]) if len(s) else "--")
        rows.append(label(f, m).replace(" (rewrite)", "") + " & " + " & ".join(cells) + "\\\\")
    return ("\\begin{table*}[!t]\\centering\n\\caption{" + caption + "}\\label{" + lab + "}\n\\footnotesize\n"
            "\\begin{tabular}{@{}l" + "rrr" * 4 + "@{}}\\toprule\n" + head + "\n"
            "\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}\\cmidrule(lr){8-10}\\cmidrule(lr){11-13}\n" + sub + "\n" + "\n".join(rows) + "\\bottomrule\n\\end{tabular}\n\\end{table*}\n")


tabs = [("total_s", "Total cost, s (median of 5, normalised). Columns: compaction every $k$ batches, $\\infty$ = never", "tab:a-total", "{:.0f}"),
        ("write_s", "Ingest time, s (median of 5, normalised)", "tab:a-write", "{:.0f}"),
        ("compact_s", "Compaction time over the whole run, s (median of 5, normalised)", "tab:a-compact", "{:.1f}"),
        ("final_q_s", "Warm Q1--Q5 latency at the last checkpoint, s (median of 5, normalised)", "tab:a-read", "{:.2f}"),
        ("wa", "Write amplification (deterministic across repetitions)", "tab:a-wa", "{:.2f}"),
        ("delta_files", "Live delete, deletion-vector or log files at the end of the run", "tab:a-del", "{:.0f}"),
        ("meta_kb", "Metadata on disk at the end of the run, KB", "tab:a-meta", "{:.0f}"),
        ("total_cv", "Coefficient of variation of total cost over five repetitions", "tab:a-cv", "{:.3f}")]
open(f"{OUT}/appendix_tables.tex", "w", encoding="utf-8").write("\n".join(matrix(*x) for x in tabs))

pd.set_option("display.width", 200, "display.max_rows", 200, "display.max_columns", 30)
print(t.round(3).to_string())
print(pd.DataFrame(abl).round(2).to_string())
print(norm.round(3).to_string())
print(be.round(2).to_string())
print(trade.round(2).to_string())
print(saw.round(2).to_string())
print("within 15%:", (g.ratio.between(1 / 1.15, 1.15)).mean(), "max", g.ratio.max(), "min", g.ratio.min(), "n", len(g))
tot = summ[(summ.u == .2) & (summ.c == 0)].assign(w=lambda d: d.write_s / d.total_s, q=lambda d: d.query_s / d.total_s)
print(tot[["fmt", "mode", "w", "q"]].round(3).to_string())
