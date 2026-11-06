"""Generate self-contained Kaggle/Colab notebooks, one per u shard: notebooks/sensorlst_u{XX}.ipynb.

The sensorlst package is embedded in one cell, so the notebook needs no GitHub access to this repo.
    python scripts/make_notebooks.py
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U_SHARDS = [0.0, 0.01, 0.05, 0.20]


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(True)}


def notebook(u: float, first_rep: int = 1, reps: int = 3, suffix: str = "") -> dict:
    tag = f"u{int(round(u * 100)):02d}{suffix}"
    which = f"{reps} repetitions" if first_rep == 1 else f"repetitions {first_rep} to {reps} only"
    cells = [md(f"""
# sensor-LST benchmark — shard `{tag}` (late-update rate u = {u * 100:g}%)

Delta Lake 3.2.1 vs Apache Iceberg 1.6.1 vs Apache Hudi 0.15.0 (+ plain Parquet) on Spark 3.5.3, workload built from
TSM-Bench d1. This notebook runs every format x {{CoW, MoR}} x compaction cycle for **one** u value, {which},
formats interleaved in random order inside each round, one fresh JVM per run.

**Kaggle:** Settings → Internet **On**, Accelerator **None** (CPU, 4 cores / 30 GB). Then *Save Version → Save & Run All
(Commit)*. It runs headless (≤ 12 h); results land in the Output tab as `results_{tag}.zip`.
**Colab:** Runtime → Run all, keep the tab open. Results are written to Google Drive (`MyDrive/sensorlst`) after every
run, so if the session disconnects just Run all again: finished runs are skipped.
"""),
        code(f"""
U = {u}            # this shard
REPS = {reps}
FIRST_REP = {first_rep}
SUFFIX = "{suffix}"
BUDGET_HOURS = 10.5  # stop starting new runs after this; finished runs are kept
SCALE = "small"
USE_DRIVE = True   # Colab only: write results to MyDrive/sensorlst as they finish (survives disconnects)
"""),
        code("""
import os, subprocess, sys, shutil, glob, time, socket
try:
    socket.getaddrinfo("pypi.org", 443)
except OSError:
    raise RuntimeError("NO INTERNET in this notebook. Kaggle: Settings -> Internet -> On (needs a phone-verified "
                       "account), then run again / Save Version again.") from None
KAGGLE = os.path.exists("/kaggle")
WORK = "/kaggle/working" if KAGGLE else "/content"
SCRATCH = "/tmp/lh"                      # tables, staging, ivy cache: not kept as output
os.makedirs(SCRATCH, exist_ok=True); os.makedirs(WORK, exist_ok=True); os.chdir(WORK)
RESULTS = f"{WORK}/results"
if USE_DRIVE and not KAGGLE:
    from google.colab import drive
    drive.mount("/content/drive")
    RESULTS = "/content/drive/MyDrive/sensorlst/results"
os.makedirs(RESULTS, exist_ok=True)
print("results ->", RESULTS)
CORES = os.cpu_count()
MEM_GB = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
DRIVER_MEM = f"{max(2, int(MEM_GB * 0.6))}g"
print(f"cores={CORES} mem={MEM_GB:.1f}GB driver={DRIVER_MEM} kaggle={KAGGLE} notebook-python={sys.version.split()[0]}")
if shutil.which("java") is None:
    subprocess.run("apt-get -qq update && apt-get -qq install -y openjdk-11-jdk-headless > /dev/null", shell=True, check=True)
jh = subprocess.run("dirname $(dirname $(readlink -f $(which java)))", shell=True, capture_output=True, text=True).stdout.strip()
os.environ["JAVA_HOME"] = jh
print(subprocess.run(["java", "-version"], capture_output=True, text=True).stderr.splitlines()[0])
# Tested: PySpark 3.5.3 + Delta/Iceberg/Hudi run correctly on Python 3.13 and Java 21 (Kaggle's defaults).
PY = sys.executable
subprocess.run([PY, "-m", "pip", "install", "-q", "pyspark==3.5.3", "delta-spark==3.2.1", "pyarrow", "tabulate"], check=True)
print(subprocess.run([PY, "-c", "import sys, pyspark; print('python', sys.version.split()[0], 'pyspark', pyspark.__version__)"],
                     capture_output=True, text=True, check=True).stdout)
"""),
        md("## Code (embedded copy of the `sensorlst` package)")]
    files = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "sensorlst", "*.py"))):
        with open(path, encoding="utf-8") as f:
            files[os.path.basename(path)] = f.read()
    writer = "\n".join([
        "# Writes the package next to the notebook (absolute paths, no cell magics).",
        f"FILES = {files!r}",
        "PKG = os.path.join(WORK, 'sensorlst')",
        "os.makedirs(PKG, exist_ok=True)",
        "for name, src in FILES.items():",
        "    with open(os.path.join(PKG, name), 'w', encoding='utf-8') as f:",
        "        f.write(src)",
        "print(sorted(os.listdir(PKG)))",
    ])
    cells.append(code(writer))
    cells += [
        md("## Data: TSM-Bench d1 → Parquet subset (10 stations × 20 sensors × 17 days)"),
        code("""
SRC = f"{SCRATCH}/d1_{SCALE}.parquet"
# Optional shortcut: a Kaggle Dataset holding d1_small.parquet (built by sensorlst.workload.prepare_d1) is used as-is.
attached = glob.glob(f"/kaggle/input/**/d1_{SCALE}.parquet", recursive=True)
if attached and not os.path.exists(SRC):
    shutil.copy(attached[0], SRC)
    print("using attached dataset", attached[0])
if not os.path.exists(SRC):
    t = time.time()
    repo = f"{SCRATCH}/tsmbench"
    for attempt in range(1, 4):
        shutil.rmtree(repo, ignore_errors=True)
        r = subprocess.run(f"git clone -q --depth 1 --filter=blob:none --sparse https://github.com/eXascaleInfolab/TSM-Bench.git {repo}"
                           f" && cd {repo} && git sparse-checkout set datasets", shell=True, capture_output=True, text=True)
        if r.returncode == 0:
            break
        print(f"clone attempt {attempt} failed: {r.stderr[-300:]}"); time.sleep(30)
    else:
        raise RuntimeError("Cannot download TSM-Bench from GitHub. Upload d1_small.parquet as a Kaggle Dataset, "
                           "attach it (Add Input), and run again.")
    prep = ("import sys; from sensorlst.config import SCALES; from sensorlst.workload import prepare_d1; "
            "df = prepare_d1(sys.argv[1], sys.argv[2], SCALES[sys.argv[3]]); print(df.shape, df.time.min(), df.time.max())")
    r = subprocess.run([PY, "-c", prep, f"{repo}/datasets/d1_splits", SRC, SCALE], cwd=WORK, capture_output=True, text=True)
    print(r.stdout, r.stderr[-3000:] if r.returncode else "", f"{time.time() - t:.0f}s")
    assert r.returncode == 0 and os.path.exists(SRC), "data preparation failed (see error above)"
    shutil.rmtree(repo, ignore_errors=True)
"""),
        md("## Warm the Maven/Ivy cache so package download is not timed as JVM start"),
        code("""
warm = '''
import sys
from sensorlst.formats import build_spark
s = build_spark(sys.argv[1], "/tmp/lh/warm", 1, "1g", "/tmp/lh/ivy"); s.range(1).count(); s.stop()
'''
for fmt in ["delta", "iceberg", "hudi"]:
    r = subprocess.run([PY, "-c", warm, fmt], cwd=WORK, capture_output=True, text=True)
    print(fmt, "ok" if r.returncode == 0 else r.stderr[-1500:])
"""),
        md("## Run the shard (resumable, prints one line per run)"),
        code("""
TAG = f"u{int(round(U * 100)):02d}{SUFFIX}"
OUT = f"{RESULTS}/runs_{TAG}"
cmd = [PY, "-m", "sensorlst.matrix", "--scale", SCALE, "--u", str(U), "--reps", str(REPS), "--first-rep", str(FIRST_REP),
       "--source", SRC, "--out", OUT, "--staging", f"{SCRATCH}/staging", "--workdir", f"{SCRATCH}/work",
       "--cores", str(CORES), "--driver-mem", DRIVER_MEM, "--ivy", f"{SCRATCH}/ivy",
       "--budget-hours", str(BUDGET_HOURS), "--calibration"]
p = subprocess.Popen(cmd, cwd=WORK, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in p.stdout:
    print(line, end="")
p.wait()
print("exit", p.returncode, "runs:", len(glob.glob(f"{OUT}/*.json")))
"""),
        md("## Shard summary + package results"),
        code("""
# Self-contained: also works on its own after a kernel restart.
import os, sys, glob, shutil, subprocess
WORK = "/kaggle/working" if os.path.exists("/kaggle") else "/content"
RESULTS = next((d for d in ["/content/drive/MyDrive/sensorlst/results", f"{WORK}/results"]
                if glob.glob(f"{d}/runs_*/*.json")), f"{WORK}/results")
runs = sorted(glob.glob(f"{RESULTS}/runs_*"))
print("result folders:", {os.path.basename(r): len(glob.glob(f"{r}/*.json")) for r in runs})
for r in runs:
    tag = os.path.basename(r).replace("runs_", "")
    p = subprocess.run([sys.executable, "-m", "sensorlst.analyze", r, "--out", f"{RESULTS}/report_{tag}"],
                       cwd=WORK, capture_output=True, text=True)
    print(p.stdout or p.stderr[-2000:])
    if os.path.exists(f"{RESULTS}/report_{tag}/summary.md"):
        print(open(f"{RESULTS}/report_{tag}/summary.md").read()[:3000])
    zipname = shutil.make_archive(f"{WORK}/results_{tag}", "zip", RESULTS)
    print("done:", zipname)
if not runs:
    print("No finished runs found yet: the 'Run the shard' cell has not produced results in this session.")
"""),
    ]
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                                        "name": "python3"},
                                         "language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 5}


def main():
    """--extra writes the notebooks that add repetitions 4 and 5; the first three repetitions are already done."""
    extra = "--extra" in sys.argv
    out = os.path.join(ROOT, "notebooks")
    os.makedirs(out, exist_ok=True)
    for u in U_SHARDS:
        suffix = "b" if extra else ""
        p = os.path.join(out, f"sensorlst_u{int(round(u * 100)):02d}{suffix}.ipynb")
        nb = notebook(u, 4, 5, suffix) if extra else notebook(u)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1, ensure_ascii=False)
        print(p)


if __name__ == "__main__":
    main()
