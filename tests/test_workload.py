"""Unit tests for the sensor-LST generator (no Spark needed)."""
import json
import os

import pandas as pd
import pytest

from sensorlst.config import SCALES, matrix
from sensorlst.workload import build_plan, synthetic_source


@pytest.fixture(scope="module")
def plan(tmp_path_factory):
    d = tmp_path_factory.mktemp("plan")
    return build_plan("smoke", 0.2, str(d), seed=7), d


def test_deterministic(tmp_path):
    a = build_plan("smoke", 0.05, str(tmp_path / "a"), seed=1)
    b = build_plan("smoke", 0.05, str(tmp_path / "b"), seed=1)
    assert a["checkpoints"] == b["checkpoints"]
    for i in (1, 6):
        pa = pd.read_parquet(tmp_path / "a" / f"batch_{i:03d}.parquet")
        pb = pd.read_parquet(tmp_path / "b" / f"batch_{i:03d}.parquet")
        pd.testing.assert_frame_equal(pa, pb)


def test_late_fraction_and_unique_keys(plan):
    m, d = plan
    sc = SCALES["smoke"]
    for b in m["batches"]:
        assert b["new_rows"] == sc.rows_per_batch()
        assert b["late_rows"] == round(0.2 * sc.rows_per_batch())
        df = pd.read_parquet(os.path.join(d, f"batch_{b['batch']:03d}.parquet"))
        assert not df.duplicated(["id_station", "time"]).any()


def test_late_rows_hit_existing_keys(plan):
    m, d = plan
    seen = pd.read_parquet(os.path.join(d, "base.parquet"))[["id_station", "time"]]
    for b in m["batches"]:
        df = pd.read_parquet(os.path.join(d, f"batch_{b['batch']:03d}.parquet"))
        start = pd.Timestamp(m["base_end"]) + pd.Timedelta(minutes=SCALES["smoke"].batch_minutes) * (b["batch"] - 1)
        late = df[df.time < start]
        assert len(late) == b["late_rows"]
        assert len(late.merge(seen, on=["id_station", "time"])) == len(late)
        seen = pd.concat([seen, df[df.time >= start][["id_station", "time"]]])


def test_expected_state_matches_replay(plan):
    """Replaying the staged files with pandas reproduces the manifest's ground truth."""
    m, d = plan
    state = pd.read_parquet(os.path.join(d, "base.parquet")).set_index(["id_station", "time"])
    dels = {x["batch"]: x for x in m["deletes"]}
    cps = {c["batch"]: c for c in m["checkpoints"]}
    for b in m["batches"]:
        df = pd.read_parquet(os.path.join(d, f"batch_{b['batch']:03d}.parquet")).set_index(["id_station", "time"])
        state = pd.concat([state[~state.index.isin(df.index)], df])
        if b["batch"] in dels:
            x = dels[b["batch"]]
            state = state[~((state.index.get_level_values(0) == x["id_station"]) & (state.day == x["day"]))]
        if b["batch"] in cps:
            assert len(state) == cps[b["batch"]]["expected_count"]
            assert round(state.s0.sum(), 4) == pytest.approx(cps[b["batch"]]["expected_sum_s0"], abs=1e-3)


def test_deletes_remove_rows(plan):
    m, _ = plan
    assert m["deletes"] and all(x["rows"] > 0 for x in m["deletes"])


def test_matrix_size():
    cfgs = matrix("small", reps=1)
    # 3 table formats x 2 modes x 4 u x 3 compaction cycles + 4 Parquet baselines
    assert len(cfgs) == 3 * 2 * 4 * 3 + 4
    assert len({c.run_id for c in cfgs}) == len(cfgs)


def test_synthetic_matches_d1_shape():
    sc = SCALES["smoke"]
    df = synthetic_source(sc)
    assert list(df.columns[:2]) == ["time", "id_station"] and df.id_station.nunique() == sc.n_stations
    assert df.s0.between(0, 1).all()
