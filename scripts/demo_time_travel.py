"""Live demo: a late correction arrives, and time travel shows the value before and after it.

    python scripts/demo_time_travel.py --fmt delta     (or iceberg / hudi)

Uses the smoke-scale staging (built on the fly). Prints, for one corrected sensor reading,
its value in every table version, then the version history with what each commit did.
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from sensorlst.formats import ADAPTERS, build_spark  # noqa: E402
from sensorlst.workload import build_plan  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fmt", default="delta", choices=["delta", "iceberg", "hudi"])
    ap.add_argument("--mode", default="mor", choices=["cow", "mor"])
    ap.add_argument("--workdir", default="work/demo")
    ap.add_argument("--batches", type=int, default=3)
    args = ap.parse_args()

    staging = "staging/demo_u20"
    m = build_plan("smoke", 0.2, staging, seed=42)
    shutil.rmtree(args.workdir, ignore_errors=True)
    spark = build_spark(args.fmt, args.workdir, 2, "1g", os.path.abspath("_ext/ivy") if os.path.isdir("_ext/ivy") else None)
    a = ADAPTERS[args.fmt](spark, args.workdir, args.mode)

    a.create(spark.read.parquet(f"{staging}/base.parquet"))
    print(f"\n[v0] bulk load of {m['base_rows']} rows (6 h of history, 4 stations)")
    for i in range(1, args.batches + 1):
        a.upsert(spark.read.parquet(f"{staging}/batch_{i:03d}.parquet"))
        b = m["batches"][i - 1]
        print(f"[batch {i}] {b['new_rows']} new readings + {b['late_rows']} late corrections")

    # pick one reading that was corrected in the last batch
    last = pd.read_parquet(f"{staging}/batch_{args.batches:03d}.parquet")
    late = last[last.time < last.time.max() - pd.Timedelta(minutes=30)].iloc[0]
    key = f"id_station = '{late.id_station}' AND time = TIMESTAMP '{late.time:%Y-%m-%d %H:%M:%S}'"
    print(f"\nTracking reading {late.id_station} @ {late.time:%Y-%m-%d %H:%M:%S} (sensor s0):")
    for ref in a.versions():
        rows = a.read_version(ref).where(key).select("s0", "ingest_batch").collect()
        val = f"s0 = {rows[0].s0:.6f} (written by batch {rows[0].ingest_batch})" if rows else "not yet ingested"
        print(f"  version {ref}: {val}")
    print("\nThe current table shows the corrected value; every earlier version is still readable,")
    print("so an auditor can reproduce exactly what a dashboard showed before the correction.")
    if args.fmt == "delta":
        spark.sql(f"DESCRIBE HISTORY delta.`{a.root.replace(os.sep, '/')}`") \
            .select("version", "operation", "operationMetrics.numOutputRows").show(truncate=False)
    elif args.fmt == "iceberg":
        spark.sql("SELECT snapshot_id, operation, summary['added-records'] added, "
                  "summary['added-delete-files'] delete_files FROM ice.db.t.snapshots").show(truncate=False)
    spark.stop()


if __name__ == "__main__":
    main()
