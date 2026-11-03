"""sensor-LST workload generator.

Turns a TSM-Bench-shaped source (time, id_station, s0..sK) into a deterministic stream of
operations staged as Parquet files, so every table format ingests byte-identical input:

  base.parquet          history bulk-loaded at t0
  batch_NNN.parquet     micro-batch NNN = new rows for its event-time slice
                        + round(u * rows_per_batch) late corrections of existing keys
  stations.parquet      station metadata (dimension table for join queries)
  manifest.json         deletes, checkpoints and the expected table state (ground truth)
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .config import SCALES, Scale

KEY = ["id_station", "time"]


def sensor_cols(scale: Scale) -> list[str]:
    return [f"s{i}" for i in range(scale.n_sensors)]


def _t0(scale: Scale) -> pd.Timestamp:
    return pd.Timestamp(scale.start, tz="UTC")


def horizon_hours(scale: Scale) -> float:
    return scale.base_hours + scale.n_batches * scale.batch_minutes / 60


def synthetic_source(scale: Scale, seed: int = 0) -> pd.DataFrame:
    """Same shape and value distribution as TSM-Bench d1 (uniform [0,1), 6 decimals). For tests/smoke runs."""
    rng = np.random.default_rng(seed)
    n_ts = int(horizon_hours(scale) * 3600 // scale.interval_s)
    times = _t0(scale) + pd.to_timedelta(np.arange(n_ts) * scale.interval_s, unit="s")
    frames = []
    for st in range(scale.n_stations):
        df = pd.DataFrame({"time": times, "id_station": f"st{st}"})
        vals = rng.random((n_ts, scale.n_sensors)).round(6)
        frames.append(pd.concat([df, pd.DataFrame(vals, columns=sensor_cols(scale))], axis=1))
    return pd.concat(frames, ignore_index=True)


def prepare_d1(split_dir: str, out_path: str, scale: Scale, chunksize: int = 500_000) -> pd.DataFrame:
    """Stream TSM-Bench d1 (split tar.gz -> d1.csv, 4.8 GB) and keep only what `scale` needs.

    d1 is sorted by station then time, so the whole file is scanned; nothing is extracted to disk.
    """
    parts = sorted(os.path.join(split_dir, f) for f in os.listdir(split_dir) if f.startswith("datasets_splits."))
    stations = {f"st{i}" for i in range(scale.n_stations)}
    end = _t0(scale) + pd.Timedelta(hours=horizon_hours(scale))
    cat = subprocess.Popen(["cat", *parts], stdout=subprocess.PIPE)
    tar = subprocess.Popen(["tar", "-xzOf", "-", "d1.csv"], stdin=cat.stdout, stdout=subprocess.PIPE)
    cat.stdout.close()
    keep = []
    for chunk in pd.read_csv(tar.stdout, usecols=["time", "id_station", *sensor_cols(scale)], chunksize=chunksize):
        chunk = chunk[chunk.id_station.isin(stations)]
        if chunk.empty:
            continue
        chunk["time"] = pd.to_datetime(chunk["time"], utc=True)
        keep.append(chunk[(chunk.time >= _t0(scale)) & (chunk.time < end)])
    tar.wait()
    df = pd.concat(keep, ignore_index=True).drop_duplicates(KEY).sort_values(KEY, ignore_index=True)
    _write(df, out_path)
    return df


def _write(df: pd.DataFrame, path: str) -> None:
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path, coerce_timestamps="us", allow_truncated_timestamps=True, compression="snappy")


def _with_cols(df: pd.DataFrame, batch: int, scols: list[str]) -> pd.DataFrame:
    out = df[["time", "id_station", *scols]].copy()
    out["day"] = out["time"].dt.strftime("%Y-%m-%d")
    out["ingest_batch"] = np.int32(batch)
    return out[["time", "id_station", "day", "ingest_batch", *scols]]


def build_plan(scale_name: str, u: float, out_dir: str, source: pd.DataFrame | None = None, seed: int = 42) -> dict:
    """Stage the operation stream for (scale, u) and return the manifest. Deterministic in (source, u, seed)."""
    scale = SCALES[scale_name]
    scols = sensor_cols(scale)
    if source is None:
        source = synthetic_source(scale, seed=0)
    source = source[source.id_station.isin([f"st{i}" for i in range(scale.n_stations)])]
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng([seed, int(round(u * 10_000))])

    t0 = _t0(scale)
    base_end = t0 + pd.Timedelta(hours=scale.base_hours)
    step = pd.Timedelta(minutes=scale.batch_minutes)
    late = pd.Timedelta(hours=scale.late_window_hours)

    base = _with_cols(source[source.time < base_end], 0, scols)
    _write(base, os.path.join(out_dir, "base.parquet"))

    # Ground-truth state: key -> (time, s0). Only s0 is tracked; it is enough to checksum updates.
    state = base[["id_station", "time", "day", "s0"]].set_index(KEY)
    n_late = int(round(u * scale.rows_per_batch()))
    deletes, checkpoints, batches = [], [], []
    stations = sorted(source.id_station.unique(), key=lambda s: int(s[2:]))

    for i in range(1, scale.n_batches + 1):
        b_start = base_end + (i - 1) * step
        b_end = b_start + step
        new = source[(source.time >= b_start) & (source.time < b_end)]
        parts = [_with_cols(new, i, scols)]
        n_upd = 0
        if n_late:
            window = state[(state.index.get_level_values("time") >= b_start - late)]
            pick = rng.choice(len(window), size=min(n_late, len(window)), replace=False)
            keys = window.index[np.sort(pick)]
            corr = pd.DataFrame({"id_station": keys.get_level_values(0), "time": keys.get_level_values(1)})
            corr[scols] = rng.random((len(corr), len(scols))).round(6)
            parts.append(_with_cols(corr, i, scols))
            state.loc[keys, "s0"] = corr["s0"].to_numpy()
            n_upd = len(corr)
        batch = pd.concat(parts, ignore_index=True)
        _write(batch, os.path.join(out_dir, f"batch_{i:03d}.parquet"))
        state = pd.concat([state, _with_cols(new, i, scols)[["id_station", "time", "day", "s0"]].set_index(KEY)])
        batches.append({"batch": i, "rows": len(batch), "new_rows": len(new), "late_rows": n_upd,
                        "days": sorted(batch.day.unique().tolist())})

        if i % scale.delete_every == 0:
            k = i // scale.delete_every - 1
            station = stations[k % len(stations)]
            day = (t0 + pd.Timedelta(days=k % max(1, int(scale.base_hours // 24)))).strftime("%Y-%m-%d")
            mask = (state.index.get_level_values("id_station") == station) & (state.day == day)
            deletes.append({"batch": i, "id_station": station, "day": day, "rows": int(mask.sum())})
            state = state[~mask]

        if i % scale.checkpoint_every == 0 or i == scale.n_batches:
            checkpoints.append({"batch": i, "event_time_end": b_end.isoformat(),
                                "expected_count": int(len(state)),
                                "expected_sum_s0": round(float(state.s0.sum()), 4)})

    stations_df = pd.DataFrame({"id_station": stations,
                                "region": [f"r{int(s[2:]) % 3}" for s in stations],
                                "elevation_m": [100 + 37 * int(s[2:]) for s in stations]})
    stations_df.to_parquet(os.path.join(out_dir, "stations.parquet"), index=False)

    manifest = {"scale": scale_name, "u": u, "seed": seed, "sensors": scols, "base_rows": len(base),
                "base_end": base_end.isoformat(), "batches": batches, "deletes": deletes,
                "checkpoints": checkpoints, "created": datetime.now(timezone.utc).isoformat()}
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    return manifest
