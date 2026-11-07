"""Live localhost demo: Delta Lake vs Iceberg vs Hudi on a sensor stream with late corrections.

    run_demo.bat            (Windows: sets Java, then streamlit run demo/app.py)
"""
import atexit
import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import time

import altair as alt
import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sensorlst.workload import build_plan  # noqa: E402

STAGING = os.path.join(ROOT, "staging", "demo_u20")
IVY = os.path.join(ROOT, "_ext", "ivy")
FORMATS = {"delta": "Delta Lake", "iceberg": "Apache Iceberg", "hudi": "Apache Hudi"}
MODE_LABEL = {"cow": "Copy-on-Write", "mor": "Merge-on-Read (Delta: deletion vectors)"}

st.set_page_config(page_title="Lakehouse demo", layout="wide")


@st.cache_resource
def live_workers():
    """Every worker of this server. A page reload starts a new session, so session_state alone would forget them."""
    return []


class Worker:
    """A Spark session for one format in its own process (formats need different Spark catalogs)."""

    def __init__(self, fmt, mode, run_id):
        self.fmt = fmt
        # Dragging a slider starts overlapping Streamlit reruns on different threads; a request and its reply must not
        # interleave with another one on the same pipe, or a reply is cut in half.
        self.lock = threading.Lock()
        self.series_cache = {}
        log = open(os.path.join(ROOT, "work", f"demo_{fmt}.log"), "a")
        self.p = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "demo", "worker.py"), "--fmt", fmt, "--mode", mode,
             "--workdir", os.path.join(ROOT, "work", f"demo_{fmt}_{run_id}"), "--staging", STAGING,
             "--ivy", IVY if os.path.isdir(IVY) else ""],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, cwd=ROOT)
        live_workers().append(self)
        self.hello = self._read()

    def _read(self):
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError(f"{self.fmt} worker stopped; see work/demo_{self.fmt}.log")
        return json.loads(line)

    def call(self, **req):
        with self.lock:
            self.p.stdin.write(json.dumps(req) + "\n")
            self.p.stdin.flush()
            return self._read()

    def series(self, station, ref=None, stamp=None):
        """Readings of one station. An old version never changes; the current table changes with `stamp`."""
        key = (station, ref, stamp)
        if key not in self.series_cache:
            self.series_cache[key] = self.call(cmd="series", station=station, **({"ref": ref} if ref else {}))["series"]
        return self.series_cache[key]

    def stop(self):
        """Wait for a clean exit: the next worker reuses this work directory."""
        try:
            self.p.stdin.close()  # end of input stops the worker's Spark session
            self.p.wait(timeout=20)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        if self.p.poll() is None:
            # On Windows a venv python.exe is a launcher, so killing it alone would leave Python and the JVM running.
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.p.pid)], capture_output=True)
            else:
                self.p.kill()


def stop_all():
    workers = live_workers()
    for w in workers:
        w.stop()
    workers.clear()
    st.session_state.workers = {}


def start(fmts, mode):
    stop_all()
    os.makedirs(os.path.join(ROOT, "work"), exist_ok=True)
    # Each start gets its own directory, so a JVM that is slow to exit can never touch the new run's files.
    for old in glob.glob(os.path.join(ROOT, "work", "demo_*_*")):
        shutil.rmtree(old, ignore_errors=True)
    run_id = int(time.time())
    if not os.path.exists(os.path.join(STAGING, "manifest.json")):
        build_plan("demo", 0.2, STAGING, seed=42)
    with open(os.path.join(STAGING, "manifest.json")) as f:
        st.session_state.manifest = json.load(f)
    st.session_state.workers, st.session_state.log, st.session_state.state = {}, [], {}
    st.session_state.next_batch, st.session_state.mode = 1, mode
    for fmt in fmts:
        with st.spinner(f"Khởi động Spark cho {FORMATS[fmt]} (lần đầu khoảng 20–40 giây)..."):
            w = Worker(fmt, mode, run_id)
            st.session_state.workers[fmt] = w
    run_all("create", "Nạp lịch sử (bulk load)")
    atexit.register(stop_all)


def run_all(cmd, label, **kw):
    for fmt, w in st.session_state.workers.items():
        with st.spinner(f"{FORMATS[fmt]}: {label}..."):
            r = w.call(cmd=cmd, **kw)
        if not r["ok"]:
            st.error(f"{FORMATS[fmt]}: {r['error']}")
            continue
        st.session_state.state[fmt] = r["state"]
        st.session_state.log.append({"Thao tác": label, "Format": FORMATS[fmt], "Thời gian (s)": round(r["seconds"], 2)})


# ------------------------------------------------------------------------------------------------ sidebar
st.sidebar.title("Thiết lập")
fmts = st.sidebar.multiselect("Table format", list(FORMATS), default=list(FORMATS), format_func=FORMATS.get)
mode = st.sidebar.radio("Chế độ ghi", ["cow", "mor"], index=1, format_func=MODE_LABEL.get)
if st.sidebar.button("Khởi động / làm lại từ đầu", type="primary", disabled=not fmts):
    start(fmts, mode)
if st.sidebar.button("Dừng Spark"):
    stop_all()
st.sidebar.caption("Dữ liệu mô phỏng cùng dạng TSM-Bench d1 (giá trị ngẫu nhiên đều trong [0, 1)) — 4 trạm × 5 cảm biến, mẫu 10 giây. Mỗi batch = 30 phút "
                   "dữ liệu mới + 20% bản ghi hiệu chỉnh trễ của 2 giờ trước đó.")

st.title("Delta Lake vs Apache Iceberg vs Apache Hudi")
st.caption("Dòng dữ liệu cảm biến thủy văn có bản ghi đến trễ — mỗi nút bấm chạy thật trên Spark 3.5.")

workers = st.session_state.get("workers", {})
if not workers:
    st.info("Chọn format và chế độ ghi ở thanh bên trái, rồi bấm **Khởi động**.")
    st.stop()

man = st.session_state.manifest
nb = st.session_state.next_batch
total = len(man["batches"])

# ------------------------------------------------------------------------------------------------ actions
def run_batch(i):
    b = man["batches"][i - 1]
    run_all("batch", f"Batch {i}: {b['new_rows']} mới + {b['late_rows']} trễ", i=i)
    st.session_state.next_batch = i + 1


def run_delete(d):
    run_all("delete", f"Xóa {d['id_station']} ngày {d['day']}", station=d["id_station"], day=d["day"])
    d["done"] = True


# Deletes follow the generator's schedule, so the ground-truth check stays valid.
pending = [d for d in man["deletes"] if d["batch"] < nb and not d.get("done")]
nxt = pending[0] if pending else None
# Stable keys: the labels change after every action, and a widget whose label changes would lose the next click.
c1, c2, c3, c4 = st.columns(4)
if c1.button(f"Ghi batch tiếp theo ({nb}/{total})", key="b_batch", disabled=nb > total, width="stretch"):
    run_batch(nb)
    st.rerun()
if c2.button(f"Xóa trạm {nxt['id_station']} ngày {nxt['day']}" if nxt else "Xóa một trạm-ngày (chưa tới lượt)",
             key="b_delete", disabled=nxt is None, width="stretch"):
    run_delete(nxt)
    st.rerun()
if c3.button("Compaction", key="b_compact", width="stretch"):
    run_all("compact", "Compaction")
    st.rerun()
if c4.button("Ghi hết các batch còn lại", key="b_all", disabled=nb > total, width="stretch"):
    for d in pending:
        run_delete(d)
    for i in range(nb, total + 1):
        run_batch(i)
        for d in man["deletes"]:
            if d["batch"] == i and not d.get("done"):
                run_delete(d)
    st.rerun()

# ------------------------------------------------------------------------------------------------ state
st.subheader("Trạng thái bảng")
rows = []
expected = {c["batch"]: c["expected_count"] for c in man["checkpoints"]}
for fmt, s in st.session_state.state.items():
    rows.append({"Format": FORMATS[fmt], "Số dòng": s["rows"], "File dữ liệu": s["data_files"],
                 "File xóa / log": s["delete_files"], "Metadata (KB)": round(s["meta_bytes"] / 1024, 1),
                 "Dữ liệu trên đĩa (KB)": round(s["data_bytes_on_disk"] / 1024),
                 "Số phiên bản": len(s["versions"])})
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
done_batch = nb - 1
if done_batch in expected and not [d for d in man["deletes"] if d["batch"] <= done_batch and not d.get("done")]:
    ok = all(s["rows"] == expected[done_batch] for s in st.session_state.state.values())
    (st.success if ok else st.warning)(
        f"Kiểm tra với ground truth sau batch {done_batch}: mong đợi {expected[done_batch]:,} dòng — "
        + ("tất cả format khớp." if ok else "có format không khớp!"))

log = pd.DataFrame(st.session_state.log)
if len(log):
    left, right = st.columns([3, 2])
    last = log.groupby("Format").tail(1)
    left.markdown(f"**Thao tác gần nhất:** {last['Thao tác'].iloc[-1]}")
    left.altair_chart(alt.Chart(last).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X("Thời gian (s):Q"), y=alt.Y("Format:N", sort=None), color=alt.Color("Format:N", legend=None),
        tooltip=["Format", "Thời gian (s)"]).properties(height=140), width="stretch")
    right.markdown("**Nhật ký thao tác**")
    right.dataframe(log.iloc[::-1], hide_index=True, width="stretch", height=200)

# ------------------------------------------------------------------------------------------------ time travel
st.subheader("Time travel: xem lại bảng ở một phiên bản cũ")
cf, cs = st.columns(2)
fmt_tt = cf.selectbox("Format", list(workers), format_func=FORMATS.get)
STATION = cs.selectbox("Trạm", ["st3", "st2", "st1", "st0"],
                       help="st0, st1, st2 lần lượt bị xóa ở batch 4, 8, 12 — chọn chúng để thấy time travel "
                            "vẫn đọc lại được dữ liệu đã xóa.")
versions = st.session_state.state[fmt_tt]["versions"]
if len(versions) < 2:
    st.info("Ghi thêm vài batch để có nhiều phiên bản.")
    st.stop()
idx = st.select_slider("Phiên bản", options=list(range(len(versions))), value=max(0, len(versions) - 2),
                       format_func=lambda i: f"v{i} · {versions[i]['label']}")
w = workers[fmt_tt]
cols = ["time", "s0", "batch"]
old = pd.DataFrame(w.series(STATION, ref=versions[idx]["ref"]), columns=cols)
cur = pd.DataFrame(w.series(STATION, stamp=len(st.session_state.log)), columns=cols)
for df in (old, cur):
    df["time"] = pd.to_datetime(df["time"])
if old.empty and cur.empty:
    st.info(f"Trạm {STATION} không có dữ liệu ở cả phiên bản v{idx} lẫn hiện tại.")
    st.stop()
both = cur.merge(old, on="time", how="left", suffixes=("", "_old"))
changed = both[both.s0_old.notna() & (both.s0 != both.s0_old)]
st.caption(f"Trạm {STATION}, cảm biến s0. Phiên bản v{idx} có {len(old):,} dòng; hiện tại {len(cur):,} dòng. "
           f"{len(changed)} số đo đã được hiệu chỉnh trễ sau phiên bản này (chấm đỏ).")
if cur.empty:
    st.warning(f"Trạm {STATION} đã bị xóa khỏi bảng hiện tại — nhưng phiên bản v{idx} vẫn còn {len(old):,} dòng "
               "của trạm này: time travel đọc lại được dữ liệu đã xóa.")
    cur = old.assign(s0=float("nan"))
# Zoom on the corrected readings when there are any, otherwise on the last hour.
if len(changed):
    lo, hi = changed.time.min() - pd.Timedelta(minutes=10), changed.time.max() + pd.Timedelta(minutes=10)
else:
    lo, hi = cur.time.max() - pd.Timedelta(hours=1), cur.time.max()
window = cur[(cur.time >= lo) & (cur.time <= hi)]
chart_old = old[(old.time >= lo) & (old.time <= hi)].assign(phiên_bản=f"v{idx}")
chart_cur = window.assign(phiên_bản="hiện tại")
lines = alt.Chart(pd.concat([chart_old, chart_cur])).mark_line(strokeWidth=1.5).encode(
    x=alt.X("time:T", title="thời gian"), y=alt.Y("s0:Q", title="giá trị s0"),
    color=alt.Color("phiên_bản:N", title=None), strokeDash=alt.StrokeDash("phiên_bản:N", legend=None))
pts = alt.Chart(changed).mark_point(color="#e34948", size=60, filled=True).encode(
    x="time:T", y="s0:Q", tooltip=[alt.Tooltip("time:T"), alt.Tooltip("s0_old:Q", title=f"v{idx}"),
                                   alt.Tooltip("s0:Q", title="hiện tại"), alt.Tooltip("batch:Q", title="sửa ở batch")])
st.altair_chart((lines + pts).properties(height=300), width="stretch")
if len(changed):
    st.dataframe(changed.rename(columns={"time": "Thời điểm", "s0_old": f"Giá trị ở v{idx}", "s0": "Giá trị hiện tại",
                                         "batch": "Sửa ở batch"})[["Thời điểm", f"Giá trị ở v{idx}",
                                                                  "Giá trị hiện tại", "Sửa ở batch"]].tail(20),
                 hide_index=True, width="stretch")
