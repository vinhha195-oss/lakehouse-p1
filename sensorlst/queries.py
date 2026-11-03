"""Analytical queries of the sensor-LST workload, run against a temp view `t` of the current snapshot.

They follow the monitoring use case of TSM-Bench: recent-window aggregation, top-k, join with
station metadata, selective range scan, and a full scan that doubles as the correctness checksum.
"""
from __future__ import annotations

import pandas as pd


def _ts(x: pd.Timestamp) -> str:
    return x.strftime("%Y-%m-%d %H:%M:%S")


def _day(x: pd.Timestamp) -> str:
    return x.strftime("%Y-%m-%d")


def make_queries(event_time_end: str) -> dict[str, str]:
    end = pd.Timestamp(event_time_end)
    d1, d3 = end - pd.Timedelta(hours=24), end - pd.Timedelta(hours=72)
    r0 = end - pd.Timedelta(hours=30)
    return {
        # Q1: hourly averages per station over the last 24 h (dashboard refresh)
        "Q1_window_agg": f"""SELECT id_station, date_trunc('HOUR', time) h, avg(s0), avg(s1), avg(s2), count(*)
            FROM t WHERE day >= '{_day(d1)}' AND time >= TIMESTAMP '{_ts(d1)}'
            GROUP BY id_station, date_trunc('HOUR', time)""",
        # Q2: top-5 stations by peak value over the last 72 h (alerting)
        "Q2_topk": f"""SELECT id_station, max(s3) m FROM t
            WHERE day >= '{_day(d3)}' AND time >= TIMESTAMP '{_ts(d3)}'
            GROUP BY id_station ORDER BY m DESC LIMIT 5""",
        # Q3: daily regional average via join with the station dimension (whole history)
        "Q3_join": """SELECT m.region, t.day, avg(t.s4), count(*) FROM t JOIN stations m
            ON t.id_station = m.id_station GROUP BY m.region, t.day""",
        # Q4: one station, one sensor, a 2-hour range (point-ish lookup)
        "Q4_range": f"""SELECT time, s1 FROM t WHERE id_station = 'st1'
            AND day IN ('{_day(r0)}', '{_day(r0 + pd.Timedelta(hours=2))}')
            AND time >= TIMESTAMP '{_ts(r0)}' AND time < TIMESTAMP '{_ts(r0 + pd.Timedelta(hours=2))}'""",
        # Q5: full scan / checksum
        "Q5_scan": "SELECT count(*) n, sum(s0) s FROM t",
    }
