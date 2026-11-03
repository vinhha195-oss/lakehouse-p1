"""Experiment configuration: workload scales, run configs and the experiment matrix."""
from __future__ import annotations

import itertools
import json
from dataclasses import asdict, dataclass, field

# Pinned versions (Spark 3.5 line). Changing any of these invalidates comparisons.
VERSIONS = {
    "spark": "3.5.3",
    "delta": "3.2.1",
    "iceberg": "1.6.1",
    "hudi": "0.15.0",
}

PACKAGES = {
    "delta": f"io.delta:delta-spark_2.12:{VERSIONS['delta']}",
    "iceberg": f"org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:{VERSIONS['iceberg']}",
    "hudi": f"org.apache.hudi:hudi-spark3.5-bundle_2.12:{VERSIONS['hudi']}",
    "parquet": None,
}

FORMATS = ("delta", "iceberg", "hudi", "parquet")
MODES = ("cow", "mor")
U_LEVELS = (0.0, 0.01, 0.05, 0.20)


@dataclass(frozen=True)
class Scale:
    """Shape of the sensor-LST workload. Event time advances in fixed steps of `interval_s`."""

    name: str
    n_stations: int
    n_sensors: int
    base_hours: float          # history bulk-loaded before the first micro-batch
    batch_minutes: int         # event time covered by one micro-batch
    n_batches: int
    late_window_hours: float   # late corrections hit keys from this window before the batch
    delete_every: int          # a station-day delete every k batches
    checkpoint_every: int      # queries + metadata stats every k batches
    compaction_levels: tuple   # compaction every k batches; 0 = never
    interval_s: int = 10
    start: str = "2019-03-01T00:00:00"

    def rows_per_batch(self) -> int:
        return self.n_stations * self.batch_minutes * 60 // self.interval_s


SCALES = {
    # seconds on a laptop; used by tests and local smoke runs
    "smoke": Scale("smoke", 4, 5, 6, 30, 6, 2, 3, 3, (0, 2)),
    # live localhost demo (demo/app.py): 4 stations, 6 h history, 12 half-hour batches
    "demo": Scale("demo", 4, 5, 6, 30, 12, 2, 4, 4, (0, 4)),
    # main experiment: 10 stations x 20 sensors of TSM-Bench d1, 7 days history + 10 days of 6-h batches
    "small": Scale("small", 10, 20, 24 * 7, 360, 40, 72, 10, 10, (0, 5, 20)),
}


@dataclass(frozen=True)
class RunConfig:
    fmt: str
    mode: str            # cow | mor (Delta: mor = deletion vectors)
    u: float             # late-update fraction relative to batch size
    compact_every: int   # 0 = never
    rep: int
    scale: str
    seed: int = 42
    tags: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def run_id(self) -> str:
        return (f"{self.scale}_{self.fmt}_{self.mode}_u{int(round(self.u * 100)):02d}"
                f"_c{self.compact_every:02d}_r{self.rep}")

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(s: str) -> "RunConfig":
        return RunConfig(**json.loads(s))


def matrix(scale: str, u_levels=U_LEVELS, formats=FORMATS, reps: int = 3) -> list[RunConfig]:
    """Full factorial: table formats x {cow,mor} x u x compaction cycle; plain Parquet as cow/no-compaction baseline."""
    sc = SCALES[scale]
    out = []
    for rep, u in itertools.product(range(1, reps + 1), u_levels):
        for fmt in formats:
            if fmt == "parquet":
                out.append(RunConfig("parquet", "cow", u, 0, rep, scale))
                continue
            for mode, c in itertools.product(MODES, sc.compaction_levels):
                out.append(RunConfig(fmt, mode, u, c, rep, scale))
    return out
