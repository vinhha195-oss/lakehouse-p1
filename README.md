# sensor-LST: Delta Lake vs Apache Iceberg vs Apache Hudi under update-heavy IoT workloads

Reproducible benchmark for the paper *"Update-Heavy Workloads on Small Clusters: An Experimental Comparison of
Delta Lake, Apache Iceberg and Apache Hudi for IoT and Hydro-Meteorological Data"* (Big Data Analytics and
Management, TLU 2026, Project P1).

## What it measures

| RQ | Question | Metrics |
|----|----------|---------|
| RQ1 | For late-update rate u ∈ {0, 1, 5, 20}%, which format/mode has the lowest total cost? | ingest + compaction + query time |
| RQ2 | What compaction cadence is best for small-file count vs read latency? | live files, Q1–Q5 latency, degradation rate |
| RQ3 | How does metadata grow with commits, and how does that affect time travel? | metadata bytes/files, versions, time-travel latency |

Also recorded for every run: write amplification (bytes written / logical bytes), per-operation latency, and a
**correctness check** — row count and checksum of the table at every checkpoint are compared with the generator's
ground truth.

## Workload (sensor-LST)

Built from [TSM-Bench](https://github.com/eXascaleInfolab/TSM-Bench) dataset d1 (PVLDB 2023; wide schema
`time, id_station, s0..s99`, 10-second sampling). Scale `small`: 10 stations × 20 sensors, 7 days of history
bulk-loaded, then 40 micro-batches of 6 hours of event time (21,600 rows each):

1. **append** of the new slice (u = 0) or **upsert** of new slice + `u × 21,600` late corrections of random existing
   keys from the previous 72 h (u > 0);
2. every 10 batches a **GDPR-style delete** of one station-day;
3. **compaction** every k ∈ {never, 5, 20} batches;
4. every 10 batches a **checkpoint**: queries Q1 window aggregation, Q2 top-k, Q3 join with station metadata,
   Q4 range lookup, Q5 full scan (each run twice: cold, warm); time travel to T−5 and to the first version;
   storage statistics.

## Experimental controls

* One engine (Spark 3.5.3, local mode), one **fresh JVM per run**, byte-identical staged input for all formats.
* Pinned versions: Delta 3.2.1, Iceberg 1.6.1, Hudi 0.15.0 (see `sensorlst/config.py`).
* Snappy Parquet for all formats (defaults differ: Iceberg zstd, Hudi gzip). Partitioned by `day`.
* Nothing is cleaned during a run (no VACUUM / snapshot expiry / Hudi cleaner): bytes on disk = bytes written,
  and all versions stay reachable.
* "MoR" means: Delta deletion vectors, Iceberg `merge-on-read` (position deletes), Hudi `MERGE_ON_READ` (log files).
  "Compaction" means: Delta `REORG … APPLY (PURGE)` + `OPTIMIZE`; Iceberg `rewrite_data_files`
  (+ `rewrite_position_delete_files`); Hudi `run_compaction` (MoR) / `run_clustering` (CoW).
* Baseline: plain Parquet, where an upsert/delete rewrites the affected day partitions (no ACID, no time travel).
* Each configuration runs 3×, in rounds; the order inside a round is shuffled so formats are interleaved on the
  same machine. Each shard also repeats a calibration config (Delta CoW, u = 0) to compare machines across shards.

## Layout

```
sensorlst/config.py     versions, scales, run config, experiment matrix
sensorlst/workload.py   TSM-Bench d1 loader + sensor-LST generator (ground truth in manifest.json)
sensorlst/formats.py    Spark session + one adapter per format (create/append/upsert/delete/compact/time travel/stats)
sensorlst/queries.py    Q1–Q5
sensorlst/run_one.py    one run in a fresh JVM -> results/.../<run_id>.json
sensorlst/matrix.py     shard runner: resumable, time-budgeted, randomized rounds
sensorlst/analyze.py    tables (summary.csv, …) and figures
scripts/make_notebooks.py  builds notebooks/sensorlst_uXX.ipynb (self-contained, for Kaggle/Colab)
tests/                  generator unit tests (no Spark)
```

## Running

**Full experiment (Kaggle, recommended):** upload each `notebooks/sensorlst_uXX.ipynb` to Kaggle, set
Internet = On and Accelerator = None, then *Save Version → Save & Run All*. The four shards can run in parallel;
each takes < 11 h and writes `results_uXX.zip`. Unzip all into `results/` and run

```bash
python -m sensorlst.analyze results/runs_u00 results/runs_u01 results/runs_u05 results/runs_u20 --out results/report
```

**Local smoke test (Linux/macOS/WSL, or Windows with `scripts/local_env.sh`):** needs Java 11/17.

```bash
pip install -r requirements.txt
pytest -q tests
python -m sensorlst.matrix --scale smoke --u 0 0.2 --reps 1 --out results/smoke --cores 2 --driver-mem 1g
python -m sensorlst.analyze results/smoke --out results/smoke_report
```

## Results (Kaggle, 4 vCPU / 31 GB, Oct 2026)

237 runs (228 + 9 calibration), all matching the ground truth at every checkpoint. Full tables and figures:
`results/report/`; raw run records: `results/kaggle/u*/runs_u*/`. Reproduce the report with

```bash
python -m sensorlst.analyze results/kaggle/u*/runs_u* --out results/report
```

* Any late data raises total cost 1.3–3.8× over append-only; from u = 1% to 20% cost changes ≤ 8%.
* Iceberg merge-on-read is cheapest for every u > 0 (2.6–4.3× cheaper than any Delta or Hudi configuration).
* Compaction every 20 batches restores copy-on-write read latency for merge-on-read tables; every 5 only adds cost.
* Delta deletion vectors write 8× fewer bytes than Delta copy-on-write but are slower in ingest and reads here.
* Metadata grows 11–72 KB per batch; Hudi keeps ~23 versions reachable by time travel (archiving).
* The four Kaggle VMs differed up to 1.58× in speed; durations compared across update rates are normalised by the
  calibration configuration (`results/report/machine_factor.csv`).

**Scope against the proposal:** one 4-vCPU node on local disk, no TPC-DS and no MinIO; 3 repetitions instead of 5; a batch holds 6 hours of data; target file size, station partitioning and Z-order were not varied; sensor-LST is not yet integrated into LST-Bench. The report and paper state these limits.

## Live demo (localhost)

Windows: double-click `run_demo.bat` → http://localhost:8501. The Streamlit app (`demo/app.py`) starts one Spark
session per format (`demo/worker.py`), then lets you ingest micro-batches with late corrections, run the scheduled
station-day deletes and compaction, compare files/metadata/timings across formats, check the row count against the
ground truth, and time-travel to any version (including recovering a deleted station). Headless tests:
`python demo/test_worker.py` and `python demo/test_app.py`.

## Known limitations

* Single-node Spark (local mode) on a 4-vCPU VM, not a multi-node cluster; local disk, not object storage.
* TSM-Bench d1 values are i.i.d.-looking uniform numbers (GAN-augmented, normalised), so they compress poorly; real
  sensor series compress better, which lowers absolute byte counts but not the ratios between formats.
* Hudi uses a derived string record key (`hkey = id_station|epoch_micros`) because its bulk-insert and upsert paths
  render timestamp key fields differently (which silently duplicates records).
* Results depend on versions and configuration; they do not generalise to large cloud clusters.
