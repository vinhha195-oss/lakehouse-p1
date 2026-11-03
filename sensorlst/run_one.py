"""Execute one RunConfig in a fresh JVM and write results/<run_id>.json.

    python -m sensorlst.run_one --config '<RunConfig json>' --staging DIR --workdir DIR --out DIR
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import time
import traceback
from datetime import datetime, timezone

from .config import VERSIONS, RunConfig
from .formats import ADAPTERS, build_spark
from .queries import make_queries

TT_BACK = 5  # time travel target: the version TT_BACK commits before the latest


def _timed(fn, *a, **kw):
    t = time.perf_counter()
    r = fn(*a, **kw)
    return time.perf_counter() - t, r


class Ledger:
    """Tracks bytes written per operation by diffing the table directory (nothing is cleaned mid-run)."""

    def __init__(self, adapter):
        self.a, self.seen = adapter, {}
        self.data_written = self.meta_written = 0

    def step(self) -> dict:
        now = self.a.disk_files()
        new_data = new_meta = 0
        for p, s in now.items():
            if self.seen.get(p) == s:
                continue
            kind = self.a.classify(p)
            grow = s - self.seen.get(p, 0) if p in self.seen else s
            if kind == "data":
                new_data += max(grow, 0)
            elif kind == "meta":
                new_meta += max(grow, 0)
        self.seen = now
        self.data_written += new_data
        self.meta_written += new_meta
        return {"data_bytes_written": new_data, "meta_bytes_written": new_meta}

    def on_disk(self) -> dict:
        out = {"data": 0, "meta": 0, "data_files_on_disk": 0, "meta_files_on_disk": 0}
        for p, s in self.a.disk_files().items():
            k = self.a.classify(p)
            if k != "ignore":
                out[k] += s
                out[f"{k}_files_on_disk"] += 1
        return {"data_bytes_on_disk": out["data"], "meta_bytes_on_disk": out["meta"],
                "data_files_on_disk": out["data_files_on_disk"], "meta_files_on_disk": out["meta_files_on_disk"]}


def run(cfg: RunConfig, staging: str, workdir: str, out_dir: str, cores: int, driver_mem: str, ivy: str | None) -> dict:
    with open(os.path.join(staging, "manifest.json")) as f:
        manifest = json.load(f)
    shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir)
    res = {"config": json.loads(cfg.to_json()), "run_id": cfg.run_id, "versions": VERSIONS,
           "host": {"platform": platform.platform(), "cpus": os.cpu_count(), "cores_used": cores,
                    "driver_mem": driver_mem},
           "started": datetime.now(timezone.utc).isoformat(), "ops": [], "checkpoints": []}

    t_jvm, spark = _timed(build_spark, cfg.fmt, workdir, cores, driver_mem, ivy)
    res["jvm_start_s"] = t_jvm
    res["host"]["java"] = spark.sparkContext._jvm.System.getProperty("java.version")
    res["host"]["python"] = platform.python_version()
    a = ADAPTERS[cfg.fmt](spark, workdir, cfg.mode)
    spark.read.parquet(os.path.join(staging, "stations.parquet")).createOrReplaceTempView("stations")
    led = Ledger(a)

    def op(kind, batch, fn, *args):
        dt, _ = _timed(fn, *args)
        rec = {"op": kind, "batch": batch, "seconds": dt, **led.step()}
        res["ops"].append(rec)
        return rec

    op("create", 0, a.create, spark.read.parquet(os.path.join(staging, "base.parquet")))
    deletes = {}
    for d in manifest["deletes"]:
        deletes.setdefault(d["batch"], []).append(d)
    checkpoints = {c["batch"]: c for c in manifest["checkpoints"]}

    for b in manifest["batches"]:
        i = b["batch"]
        df = spark.read.parquet(os.path.join(staging, f"batch_{i:03d}.parquet"))
        op("upsert" if cfg.u > 0 else "append", i, a.upsert if cfg.u > 0 else a.append, df)
        for d in deletes.get(i, []):
            op("delete", i, a.delete, d["id_station"], d["day"])
        if cfg.compact_every and i % cfg.compact_every == 0:
            op("compact", i, a.compact)
        if i in checkpoints:
            res["checkpoints"].append(checkpoint(a, spark, checkpoints[i], led))

    final = res["checkpoints"][-1]
    res["correct"] = all(c["correct"] for c in res["checkpoints"])
    res["final"] = {k: final[k] for k in ("count", "sum_s0", "expected_count", "expected_sum_s0")}
    res["logical_bytes"] = logical_bytes(a, workdir)
    res["write_amplification"] = led.data_written / res["logical_bytes"] if res["logical_bytes"] else None
    res["total_write_s"] = sum(o["seconds"] for o in res["ops"] if o["op"] in ("create", "append", "upsert", "delete"))
    res["total_compact_s"] = sum(o["seconds"] for o in res["ops"] if o["op"] == "compact")
    res["finished"] = datetime.now(timezone.utc).isoformat()
    spark.stop()
    return res


def checkpoint(a, spark, cp: dict, led: Ledger) -> dict:
    view = a.read()
    view.createOrReplaceTempView("t")
    out = {"batch": cp["batch"], "queries": {}}
    for name, q in make_queries(cp["event_time_end"]).items():
        times = []
        for _ in range(2):  # 1st = cold-ish (fresh plan/file listing), 2nd = warm
            dt, rows = _timed(lambda: spark.sql(q).collect())
            times.append(dt)
        out["queries"][name] = times
        if name == "Q5_scan":
            out["count"], out["sum_s0"] = int(rows[0].n), round(float(rows[0].s or 0), 4)
    out["expected_count"], out["expected_sum_s0"] = cp["expected_count"], cp["expected_sum_s0"]
    out["correct"] = (out["count"] == cp["expected_count"]
                      and abs(out["sum_s0"] - cp["expected_sum_s0"]) <= 1e-3 * max(1, cp["expected_count"]) ** 0.5)
    out.update(a.live_files())
    out.update(led.on_disk())
    out["data_bytes_written_cum"] = led.data_written
    out["meta_bytes_written_cum"] = led.meta_written
    if a.supports_time_travel:
        vs = a.versions()
        out["n_versions"] = len(vs)
        tt = {}
        for label, ref in (("tt_back", vs[max(0, len(vs) - 1 - TT_BACK)]), ("tt_first", vs[0])):
            dt, rows = _timed(lambda: a.read_version(ref).agg({"*": "count"}).collect())
            tt[label] = {"seconds": dt, "count": int(rows[0][0]), "ref": str(ref)}
        out["time_travel"] = tt
    return out


def logical_bytes(a, workdir: str) -> int:
    """Size of the final logical table written once as plain snappy Parquet (denominator of write amplification)."""
    p = os.path.join(workdir, "logical")
    cols = [c for c in a.read().columns if not c.startswith("_hoodie_") and c != "hkey"]
    a.read().select(*cols).repartition("day").write.partitionBy("day").parquet(p)
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(p) for f in fs
                if f.endswith(".parquet"))
    shutil.rmtree(p, ignore_errors=True)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--staging", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cores", type=int, default=4)
    ap.add_argument("--driver-mem", default="8g")
    ap.add_argument("--ivy", default=None)
    ap.add_argument("--keep", action="store_true", help="keep the table directory (for demos)")
    args = ap.parse_args()
    cfg = RunConfig.from_json(args.config)
    os.makedirs(args.out, exist_ok=True)
    try:
        res = run(cfg, args.staging, args.workdir, args.out, args.cores, args.driver_mem, args.ivy)
    except Exception:
        with open(os.path.join(args.out, "failures.jsonl"), "a") as f:
            f.write(json.dumps({"run_id": cfg.run_id, "error": traceback.format_exc()[-4000:]}) + "\n")
        raise
    finally:
        if not args.keep:
            shutil.rmtree(args.workdir, ignore_errors=True)
    with open(os.path.join(args.out, f"{cfg.run_id}.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(f"{cfg.run_id}: correct={res['correct']} write={res['total_write_s']:.1f}s "
          f"compact={res['total_compact_s']:.1f}s WA={res['write_amplification']:.2f}")


if __name__ == "__main__":
    main()
