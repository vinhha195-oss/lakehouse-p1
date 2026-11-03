"""Run (a shard of) the experiment matrix. Resumable: finished run JSONs are skipped.

Runs are grouped in rounds (rep 1 of every config, then rep 2, ...), and the order inside each round
is shuffled, so formats are interleaved on the same machine and an expired time budget still leaves
complete rounds.

    python -m sensorlst.matrix --scale small --u 0.05 --source data/d1_small.parquet --out results/runs
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time

import pandas as pd

from .config import FORMATS, SCALES, RunConfig, matrix
from .workload import build_plan


def stage(scale: str, u: float, source: str | None, staging_root: str, seed: int) -> str:
    d = os.path.join(staging_root, f"{scale}_u{int(round(u * 100)):02d}_s{seed}")
    if not os.path.exists(os.path.join(d, "manifest.json")):
        src = pd.read_parquet(source) if source else None
        t = time.time()
        m = build_plan(scale, u, d, src, seed)
        print(f"staged {d}: base={m['base_rows']} batches={len(m['batches'])} in {time.time() - t:.0f}s", flush=True)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="small", choices=list(SCALES))
    ap.add_argument("--u", type=float, nargs="+", required=True)
    ap.add_argument("--formats", default=",".join(FORMATS))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--source", default=None, help="Parquet from prepare_d1; omit for synthetic data")
    ap.add_argument("--out", default="results/runs")
    ap.add_argument("--staging", default="staging")
    ap.add_argument("--workdir", default="work")
    ap.add_argument("--cores", type=int, default=4)
    ap.add_argument("--driver-mem", default="8g")
    ap.add_argument("--ivy", default=None)
    ap.add_argument("--budget-hours", type=float, default=11.0)
    ap.add_argument("--timeout-min", type=float, default=60)
    ap.add_argument("--calibration", action="store_true",
                    help="add delta/cow/u=0/no-compaction to every round, to compare machines across shards")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    deadline = time.time() + args.budget_hours * 3600
    os.makedirs(args.out, exist_ok=True)
    formats = tuple(args.formats.split(","))
    cfgs = matrix(args.scale, tuple(args.u), formats, args.reps)
    if args.calibration and 0.0 not in args.u:
        cfgs += [RunConfig("delta", "cow", 0.0, 0, r, args.scale, tags={"calibration": True})
                 for r in range(1, args.reps + 1)]
    stagings = {u: stage(args.scale, u, args.source, args.staging, args.seed) for u in {c.u for c in cfgs}}

    durations = []
    for rep in range(1, args.reps + 1):
        rnd = [c for c in cfgs if c.rep == rep]
        random.Random(args.seed * 1000 + rep).shuffle(rnd)
        for c in rnd:
            dst = os.path.join(args.out, f"{c.run_id}.json")
            if os.path.exists(dst):
                continue
            est = (sorted(durations)[len(durations) // 2] if durations else 0)
            if time.time() + est > deadline:
                print("time budget exhausted; stopping", flush=True)
                return
            t = time.time()
            cmd = [sys.executable, "-m", "sensorlst.run_one", "--config", c.to_json(),
                   "--staging", stagings[c.u], "--workdir", os.path.join(args.workdir, c.run_id),
                   "--out", args.out, "--cores", str(args.cores), "--driver-mem", args.driver_mem]
            if args.ivy:
                cmd += ["--ivy", args.ivy]
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout_min * 60)
                tail = (p.stdout + p.stderr).strip().splitlines()[-1:] if p.returncode == 0 else \
                       (p.stderr or p.stdout).strip().splitlines()[-3:]
            except subprocess.TimeoutExpired:
                with open(os.path.join(args.out, "failures.jsonl"), "a") as f:
                    f.write(json.dumps({"run_id": c.run_id, "error": "timeout"}) + "\n")
                tail = ["TIMEOUT"]
            durations.append(time.time() - t)
            print(f"[{time.strftime('%H:%M:%S')}] {c.run_id} {time.time() - t:.0f}s :: {' | '.join(tail)}", flush=True)


if __name__ == "__main__":
    main()
