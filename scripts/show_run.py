"""Print a compact summary of run JSON files: python scripts/show_run.py results/smoke/*.json"""
import json
import sys

for path in sys.argv[1:]:
    r = json.load(open(path))
    ops = {}
    for o in r["ops"]:
        ops.setdefault(o["op"], []).append(o["seconds"])
    print(f"{r['run_id']}: correct={r['correct']} WA={r['write_amplification']:.2f} write={r['total_write_s']:.1f}s "
          f"compact={r['total_compact_s']:.1f}s ops={ {k: round(sum(v), 1) for k, v in ops.items()} }")
    for c in r["checkpoints"]:
        q = {k: round(v[1], 2) for k, v in c["queries"].items()}
        tt = {k: round(v["seconds"], 2) for k, v in c.get("time_travel", {}).items()}
        print(f"   b{c['batch']}: n={c['count']}/{c['expected_count']} live={c['data_files']}+{c['delete_files']} "
              f"meta={c['meta_bytes_on_disk']} versions={c.get('n_versions')} tt={tt} q={q}")
