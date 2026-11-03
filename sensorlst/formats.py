"""One adapter per storage layout. Every adapter exposes the same operations so the runner is format-agnostic.

Design choices that keep the comparison controlled (see README "Fairness"):
  * one Spark engine, one JVM per run, same staged input;
  * snappy Parquet everywhere (Iceberg defaults to zstd, Hudi to gzip);
  * old file versions are never cleaned during a run (no VACUUM / expire / Hudi cleaner), so bytes
    on disk = bytes written, and every version stays reachable for time travel;
  * partitioned by `day`; MERGE/DELETE carry an explicit `day IN (...)` predicate for pruning.
"""
from __future__ import annotations

import json
import os
import re
import shutil

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from .config import PACKAGES

DATA_COLS_EXCLUDE = re.compile(r"^_hoodie_")


def build_spark(fmt: str, workdir: str, cores: int = 4, driver_mem: str = "8g", ivy_dir: str | None = None) -> SparkSession:
    b = (SparkSession.builder.master(f"local[{cores}]").appName(f"sensor-lst-{fmt}")
         .config("spark.driver.memory", driver_mem)
         .config("spark.sql.shuffle.partitions", str(cores * 2))
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.driver.extraJavaOptions", "-Duser.timezone=UTC")
         .config("spark.ui.enabled", "false")
         .config("spark.ui.showConsoleProgress", "false")
         .config("spark.sql.parquet.compression.codec", "snappy")
         .config("spark.local.dir", os.path.join(workdir, "spark-local")))
    if ivy_dir:
        b = b.config("spark.jars.ivy", ivy_dir)
    if PACKAGES[fmt]:
        b = b.config("spark.jars.packages", PACKAGES[fmt])
    if fmt == "delta":
        b = (b.config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
              .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog"))
    elif fmt == "iceberg":
        b = (b.config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
              .config("spark.sql.catalog.ice", "org.apache.iceberg.spark.SparkCatalog")
              .config("spark.sql.catalog.ice.type", "hadoop")
              .config("spark.sql.catalog.ice.warehouse", _uri(os.path.join(workdir, "iceberg_wh"))))
    elif fmt == "hudi":
        b = (b.config("spark.sql.extensions", "org.apache.spark.sql.hudi.HoodieSparkSessionExtension")
              .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.hudi.catalog.HoodieCatalog")
              .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
              .config("spark.kryo.registrator", "org.apache.spark.HoodieSparkKryoRegistrar"))
    spark = b.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def _uri(path: str) -> str:
    return "file:///" + os.path.abspath(path).replace("\\", "/").lstrip("/")


def _sql_path(path: str) -> str:
    return os.path.abspath(path).replace("\\", "/")


def _in_list(values) -> str:
    return ", ".join(f"'{v}'" for v in sorted(set(values)))


class Adapter:
    """Base adapter. `root` is the directory that holds the table and nothing else."""

    meta_dirs: tuple = ()
    supports_time_travel = True

    def __init__(self, spark: SparkSession, workdir: str, mode: str):
        self.spark, self.workdir, self.mode = spark, workdir, mode
        self.root = os.path.abspath(os.path.join(workdir, "table"))

    # --- operations ---------------------------------------------------------------------------
    def create(self, df: DataFrame) -> None: raise NotImplementedError
    def append(self, df: DataFrame) -> None: raise NotImplementedError
    def upsert(self, df: DataFrame) -> None: raise NotImplementedError
    def delete(self, station: str, day: str) -> None: raise NotImplementedError
    def compact(self) -> None: raise NotImplementedError
    def read(self) -> DataFrame: raise NotImplementedError
    def versions(self) -> list: return []
    def read_version(self, ref) -> DataFrame: raise NotImplementedError

    # --- storage accounting -------------------------------------------------------------------
    def disk_files(self) -> dict[str, int]:
        """All files under the table root -> size."""
        out = {}
        for dp, _, fs in os.walk(self.root):
            for f in fs:
                p = os.path.join(dp, f)
                try:
                    out[p] = os.path.getsize(p)
                except OSError:
                    pass
        return out

    def classify(self, path: str) -> str:
        """'meta' | 'data' | 'ignore'. Hadoop .crc sidecars exist only on the local FS (not on S3) -> ignored."""
        rel = os.path.relpath(path, self.root).replace("\\", "/")
        name = rel.rsplit("/", 1)[-1]
        if name.endswith(".crc") or name == "_SUCCESS":
            return "ignore"
        if any(rel == d or rel.startswith(d + "/") for d in self.meta_dirs):
            return "meta"
        return "data"

    def live_files(self) -> dict: raise NotImplementedError


# ---------------------------------------------------------------------------------------------
class DeltaAdapter(Adapter):
    meta_dirs = ("_delta_log",)

    def __init__(self, spark, workdir, mode):
        super().__init__(spark, workdir, mode)
        dv = "true" if mode == "mor" else "false"
        spark.conf.set("spark.databricks.delta.properties.defaults.enableDeletionVectors", dv)
        self.t = f"delta.`{_sql_path(self.root)}`"

    def create(self, df):
        df.write.format("delta").partitionBy("day").mode("overwrite").save(self.root)

    def append(self, df):
        df.write.format("delta").mode("append").save(self.root)

    def upsert(self, df):
        days = [r.day for r in df.select("day").distinct().collect()]
        df.createOrReplaceTempView("src")
        self.spark.sql(f"""MERGE INTO {self.t} t USING src s
            ON t.day IN ({_in_list(days)}) AND t.day = s.day AND t.id_station = s.id_station AND t.time = s.time
            WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *""")

    def delete(self, station, day):
        self.spark.sql(f"DELETE FROM {self.t} WHERE day = '{day}' AND id_station = '{station}'")

    def compact(self):
        if self.mode == "mor":  # materialise deletion vectors, then bin-pack
            self.spark.sql(f"REORG TABLE {self.t} APPLY (PURGE)")
        self.spark.sql(f"OPTIMIZE {self.t}")

    def read(self):
        return self.spark.read.format("delta").load(self.root)

    def versions(self):
        return [r.version for r in self.spark.sql(f"DESCRIBE HISTORY {self.t}").select("version").orderBy("version").collect()]

    def read_version(self, ref):
        return self.spark.read.format("delta").option("versionAsOf", ref).load(self.root)

    def live_files(self):
        """Replay the JSON commit log (never cleaned during a run): live files and live deletion vectors."""
        log = os.path.join(self.root, "_delta_log")
        live = {}
        for name in sorted(f for f in os.listdir(log) if re.fullmatch(r"\d{20}\.json", f)):
            with open(os.path.join(log, name)) as fh:
                for line in fh:
                    a = json.loads(line)
                    # a DV change removes and re-adds the same path in one commit: key on (path, DV)
                    if "add" in a:
                        dv = a["add"].get("deletionVector")
                        live[(a["add"]["path"], json.dumps(dv, sort_keys=True))] = (a["add"]["size"], dv)
                    elif "remove" in a:
                        dv = a["remove"].get("deletionVector")
                        live.pop((a["remove"]["path"], json.dumps(dv, sort_keys=True)), None)
        dvs = [dv for _, dv in live.values() if dv]
        return {"data_files": len(live), "data_bytes": sum(s for s, _ in live.values()),
                "delete_files": len(dvs), "delete_bytes": sum(dv.get("sizeInBytes", 0) for dv in dvs)}


# ---------------------------------------------------------------------------------------------
class IcebergAdapter(Adapter):
    t = "ice.db.t"

    def __init__(self, spark, workdir, mode):
        super().__init__(spark, workdir, mode)
        self.root = os.path.abspath(os.path.join(workdir, "iceberg_wh", "db", "t"))
        self.meta_dirs = ("metadata",)

    def create(self, df):
        m = "merge-on-read" if self.mode == "mor" else "copy-on-write"
        (df.writeTo(self.t).partitionedBy(F.col("day"))
           .tableProperty("format-version", "2")
           .tableProperty("write.parquet.compression-codec", "snappy")
           .tableProperty("write.delete.mode", m).tableProperty("write.update.mode", m)
           .tableProperty("write.merge.mode", m)
           .createOrReplace())

    def append(self, df):
        df.writeTo(self.t).append()

    def upsert(self, df):
        days = [r.day for r in df.select("day").distinct().collect()]
        df.createOrReplaceTempView("src")
        self.spark.sql(f"""MERGE INTO {self.t} t USING src s
            ON t.day IN ({_in_list(days)}) AND t.day = s.day AND t.id_station = s.id_station AND t.time = s.time
            WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *""")

    def delete(self, station, day):
        self.spark.sql(f"DELETE FROM {self.t} WHERE day = '{day}' AND id_station = '{station}'")

    def compact(self):
        self.spark.sql("CALL ice.system.rewrite_data_files(table => 'db.t', "
                       "options => map('min-input-files', '2', 'delete-file-threshold', '1'))")
        if self.mode == "mor":
            self.spark.sql("CALL ice.system.rewrite_position_delete_files(table => 'db.t')")

    def read(self):
        return self.spark.table(self.t)

    def versions(self):
        return [r.snapshot_id for r in
                self.spark.sql(f"SELECT snapshot_id FROM {self.t}.snapshots ORDER BY committed_at").collect()]

    def read_version(self, ref):
        return self.spark.sql(f"SELECT * FROM {self.t} VERSION AS OF {ref}")

    def live_files(self):
        rows = self.spark.sql(f"SELECT content, count(*) n, sum(file_size_in_bytes) b FROM {self.t}.files "
                              f"GROUP BY content").collect()
        by = {r.content: (r.n, r.b or 0) for r in rows}
        dn = sum(v[0] for k, v in by.items() if k != 0)
        db = sum(v[1] for k, v in by.items() if k != 0)
        return {"data_files": by.get(0, (0, 0))[0], "data_bytes": by.get(0, (0, 0))[1],
                "delete_files": dn, "delete_bytes": db}


# ---------------------------------------------------------------------------------------------
_HUDI_BASE = re.compile(r"^(?P<fid>[0-9a-f-]+-\d+)_[^_]+_(?P<ts>\d+)\.parquet$")
_HUDI_LOG = re.compile(r"^\.(?P<fid>[0-9a-f-]+-\d+)_(?P<ts>\d+)\.log\.\d+_.+$")
_HUDI_DONE = re.compile(r"^(\d+)\.(commit|deltacommit|replacecommit)$")


class HudiAdapter(Adapter):
    meta_dirs = (".hoodie",)

    def __init__(self, spark, workdir, mode):
        super().__init__(spark, workdir, mode)
        self.opts = {
            "hoodie.table.name": "t",
            "hoodie.datasource.write.table.type": "MERGE_ON_READ" if mode == "mor" else "COPY_ON_WRITE",
            # Hudi renders timestamp key fields differently on its bulk_insert (row) and upsert (Avro) paths,
            # which silently duplicates records; key on a deterministic string column instead.
            "hoodie.datasource.write.recordkey.field": "hkey",
            "hoodie.datasource.write.partitionpath.field": "day",
            "hoodie.datasource.write.precombine.field": "ingest_batch",
            "hoodie.datasource.write.keygenerator.class": "org.apache.hudi.keygen.SimpleKeyGenerator",
            "hoodie.datasource.write.hive_style_partitioning": "true",
            "hoodie.parquet.compression.codec": "snappy",
            "hoodie.clean.automatic": "false",
            "hoodie.compact.inline": "false",
            "hoodie.clustering.inline": "false",
        }
        # Default compaction scheduling waits for 5 delta commits; the experiment controls the cadence itself.
        spark.conf.set("hoodie.compact.inline.max.delta.commits", "1")

    def _write(self, df, op, mode="append"):
        if "hkey" not in df.columns:
            df = df.withColumn("hkey", F.concat_ws("|", "id_station", F.unix_micros("time").cast("string")))
        (df.write.format("hudi").options(**self.opts).option("hoodie.datasource.write.operation", op)
           .mode(mode).save(_uri(self.root)))

    def create(self, df):
        self._write(df, "bulk_insert", "overwrite")

    def append(self, df):
        self._write(df, "insert")

    def upsert(self, df):
        self._write(df, "upsert")

    def delete(self, station, day):
        doomed = self.read().where(f"day = '{day}' AND id_station = '{station}'")
        self._write(doomed.drop(*[c for c in doomed.columns if c.startswith("_hoodie_")]), "delete")

    def compact(self):
        p = _uri(self.root)
        if self.mode == "mor":
            self.spark.sql(f"CALL run_compaction(op => 'scheduleAndExecute', path => '{p}')").collect()
        else:
            self.spark.sql(f"CALL run_clustering(path => '{p}')").collect()

    def read(self):
        return self.spark.read.format("hudi").load(_uri(self.root))

    def versions(self):
        hd = os.path.join(self.root, ".hoodie")
        return sorted(m.group(1) for f in os.listdir(hd) if (m := _HUDI_DONE.match(f)))

    def read_version(self, ref):
        return self.spark.read.format("hudi").option("as.of.instant", ref).load(_uri(self.root))

    def live_files(self):
        """Latest file slice per file group, minus file groups replaced by clustering."""
        hd = os.path.join(self.root, ".hoodie")
        done = set(self.versions())
        replaced = set()
        for f in os.listdir(hd):
            if f.endswith(".replacecommit") and f.split(".")[0] in done:
                with open(os.path.join(hd, f)) as fh:
                    meta = json.load(fh)
                for ids in (meta.get("partitionToReplaceFileIds") or {}).values():
                    replaced.update(ids)
        groups: dict[str, dict] = {}
        for p, size in self.disk_files().items():
            if os.sep + ".hoodie" in p or "/.hoodie" in p:
                continue
            name = os.path.basename(p)
            if m := _HUDI_BASE.match(name):
                if m["ts"] not in done:
                    continue
                g = groups.setdefault(m["fid"], {"base": None, "logs": []})
                if g["base"] is None or m["ts"] > g["base"][0]:
                    g["base"] = (m["ts"], size)
            elif m := _HUDI_LOG.match(name):
                groups.setdefault(m["fid"], {"base": None, "logs": []})["logs"].append((m["ts"], size))
        out = {"data_files": 0, "data_bytes": 0, "delete_files": 0, "delete_bytes": 0}
        for fid, g in groups.items():
            if fid in replaced:
                continue
            base_ts = g["base"][0] if g["base"] else ""
            if g["base"]:
                out["data_files"] += 1
                out["data_bytes"] += g["base"][1]
            logs = [s for ts, s in g["logs"] if ts >= base_ts]
            out["delete_files"] += len(logs)  # log files = row-level changes not yet compacted
            out["delete_bytes"] += sum(logs)
        return out


# ---------------------------------------------------------------------------------------------
class ParquetAdapter(Adapter):
    """Plain Parquet baseline: no log, no ACID; row changes rewrite whole day partitions."""

    supports_time_travel = False

    def create(self, df):
        df.write.partitionBy("day").mode("overwrite").parquet(self.root)

    def append(self, df):
        df.write.partitionBy("day").mode("append").parquet(self.root)

    def _rewrite_days(self, days, transform):
        days = sorted(set(days))
        old = self.read().where(F.col("day").isin(days))
        new = transform(old)
        tmp = os.path.join(self.workdir, "parquet_tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        new.write.partitionBy("day").parquet(tmp)
        for d in days:  # swap partition directories (not atomic -- that is the point of the baseline)
            shutil.rmtree(os.path.join(self.root, f"day={d}"), ignore_errors=True)
            src = os.path.join(tmp, f"day={d}")
            if os.path.isdir(src):
                shutil.move(src, os.path.join(self.root, f"day={d}"))
        shutil.rmtree(tmp, ignore_errors=True)

    def upsert(self, df):
        days = [r.day for r in df.select("day").distinct().collect()]
        cols = df.columns

        def merge(old):
            w = Window.partitionBy("id_station", "time").orderBy(F.col("ingest_batch").desc())
            both = old.select(*cols).unionByName(df.select(*cols))
            return both.withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn")
        self._rewrite_days(days, merge)

    def delete(self, station, day):
        self._rewrite_days([day], lambda old: old.where(F.col("id_station") != station))

    def compact(self):
        pass

    def read(self):
        return self.spark.read.parquet(self.root)

    def live_files(self):
        files = {p: s for p, s in self.disk_files().items() if p.endswith(".parquet")}
        return {"data_files": len(files), "data_bytes": sum(files.values()), "delete_files": 0, "delete_bytes": 0}


ADAPTERS = {"delta": DeltaAdapter, "iceberg": IcebergAdapter, "hudi": HudiAdapter, "parquet": ParquetAdapter}
