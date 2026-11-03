"""One Spark session per table format, driven by JSON lines on stdin (used by demo/app.py).

Each request is {"cmd": ..., ...}; each reply is one JSON line on stdout. Spark's own logging goes to stderr.
    python demo/worker.py --fmt delta --mode mor --workdir work/demo_delta --staging staging/demo_u20
"""
import argparse
import json
import os
import shutil
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensorlst.formats import ADAPTERS, build_spark  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fmt", required=True)
    ap.add_argument("--mode", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--staging", required=True)
    ap.add_argument("--ivy", default=None)
    args = ap.parse_args()

    # Keep the protocol on a private copy of fd 1 and point fd 1 at stderr, so that output of the JVM child process
    # (which inherits the OS-level descriptors) cannot corrupt the JSON stream.
    out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    shutil.rmtree(args.workdir, ignore_errors=True)
    os.makedirs(args.workdir)
    spark = build_spark(args.fmt, args.workdir, 2, "1g", args.ivy)
    a = ADAPTERS[args.fmt](spark, args.workdir, args.mode)
    stations = spark.read.parquet(os.path.join(args.staging, "stations.parquet"))
    with open(os.path.join(args.staging, "manifest.json")) as f:
        manifest = json.load(f)
    history = []  # (version ref, label) in commit order, as the demo saw them

    def refresh_versions(label):
        if not a.supports_time_travel:
            return
        known = {str(r) for r, _ in history}
        for ref in a.versions():
            if str(ref) not in known:
                history.append((ref, label))

    def state():
        st = {"rows": a.read().count()}
        st.update(a.live_files())
        meta = data = 0
        for p, sz in a.disk_files().items():
            kind = a.classify(p)
            meta += sz if kind == "meta" else 0
            data += sz if kind == "data" else 0
        st.update({"meta_bytes": meta, "data_bytes_on_disk": data,
                   "versions": [{"ref": str(r), "label": l} for r, l in history]})
        return st

    def series(ref, station):
        df = a.read() if ref is None else a.read_version(ref)
        rows = df.where(f"id_station = '{station}'").select("time", "s0", "ingest_batch").orderBy("time").collect()
        return [{"time": r.time.isoformat(), "s0": r.s0, "batch": int(r.ingest_batch)} for r in rows]

    out.write(json.dumps({"ok": True, "ready": True, "batches": len(manifest["batches"]),
                          "deletes": manifest["deletes"]}) + "\n")
    out.flush()
    for line in sys.stdin:
        req = json.loads(line)
        cmd = req["cmd"]
        t = time.perf_counter()
        try:
            res = {}
            if cmd == "create":
                a.create(spark.read.parquet(os.path.join(args.staging, "base.parquet")))
                refresh_versions("bulk load")
            elif cmd == "batch":
                i = req["i"]
                b = manifest["batches"][i - 1]
                a.upsert(spark.read.parquet(os.path.join(args.staging, f"batch_{i:03d}.parquet")))
                refresh_versions(f"batch {i}: {b['new_rows']} new + {b['late_rows']} late")
                res = {"new_rows": b["new_rows"], "late_rows": b["late_rows"]}
            elif cmd == "delete":
                a.delete(req["station"], req["day"])
                refresh_versions(f"delete {req['station']} {req['day']}")
            elif cmd == "compact":
                a.compact()
                refresh_versions("compaction")
            elif cmd == "state":
                pass
            elif cmd == "series":
                res = {"series": series(req.get("ref"), req["station"])}
            elif cmd == "quit":
                out.write(json.dumps({"ok": True}) + "\n")
                out.flush()
                break
            seconds = time.perf_counter() - t
            if cmd not in ("series", "quit"):
                res["state"] = state()
            out.write(json.dumps({"ok": True, "seconds": seconds, **res}, default=str) + "\n")
        except Exception as e:  # report and keep serving
            out.write(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}",
                                  "trace": traceback.format_exc()[-1500:]}) + "\n")
        out.flush()
    spark.stop()


if __name__ == "__main__":
    main()
