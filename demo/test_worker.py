"""Headless check of demo/worker.py for each format: create, 4 batches, scheduled delete, compaction, time travel."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sensorlst.workload import build_plan  # noqa: E402

STAGING = os.path.join(ROOT, "staging", "demo_u20")
if not os.path.exists(os.path.join(STAGING, "manifest.json")):
    build_plan("demo", 0.2, STAGING, seed=42)
man = json.load(open(os.path.join(STAGING, "manifest.json")))
expected = {c["batch"]: c["expected_count"] for c in man["checkpoints"]}
os.makedirs(os.path.join(ROOT, "work"), exist_ok=True)

for fmt in sys.argv[1:] or ["delta", "iceberg", "hudi"]:
    log = open(os.path.join(ROOT, "work", f"test_{fmt}.log"), "w")
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "demo", "worker.py"), "--fmt", fmt, "--mode", "mor",
                          "--workdir", os.path.join(ROOT, "work", f"test_{fmt}"), "--staging", STAGING,
                          "--ivy", os.path.join(ROOT, "_ext", "ivy")],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True)

    def call(**req):
        p.stdin.write(json.dumps(req) + "\n")
        p.stdin.flush()
        r = json.loads(p.stdout.readline())
        assert r["ok"], r
        return r

    json.loads(p.stdout.readline())
    call(cmd="create")
    for i in range(1, 5):
        r = call(cmd="batch", i=i)
        for d in man["deletes"]:
            if d["batch"] == i:
                r = call(cmd="delete", station=d["id_station"], day=d["day"])
    st = r["state"]
    print(f"{fmt}: rows={st['rows']} expected={expected[4]} files={st['data_files']}+{st['delete_files']} "
          f"versions={len(st['versions'])}")
    assert st["rows"] == expected[4]
    st = call(cmd="compact")["state"]
    print(f"   after compaction: files={st['data_files']}+{st['delete_files']}")
    v = st["versions"]
    old = call(cmd="series", ref=v[0]["ref"], station="st0")["series"]
    cur = call(cmd="series", station="st0")["series"]
    print(f"   time travel v0 ({v[0]['label']}): {len(old)} rows; current: {len(cur)} rows; "
          f"labels={[x['label'] for x in v][:3]}...")
    call(cmd="quit")
    p.wait(timeout=60)
print("OK")
