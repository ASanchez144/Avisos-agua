"""Calibra los disparadores con la serie real de la DANA (Rambla del Poyo, 29/10/2024).

Uso:  python scripts/calibrate.py [--markdown]
Criterio de acierto (DEL PROYECTO, no oficial): un disparo es acierto si en las 3 h siguientes el
caudal llega a >= HIT_FLOW m3/s; si no, es falsa alarma. Hay UN solo episodio: los resultados
sirven para descartar parámetros absurdos, no para afirmar una tasa de falsas alarmas general.
"""
from __future__ import annotations

import csv
import itertools
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connectors.base import Reading  # noqa: E402
from engine.propagation import load_links, evaluate  # noqa: E402

CSV = ROOT / "tests" / "fixtures" / "historical" / "cincominutales-rambla-poyo-29102024.csv"
LINK = "poyo-aforo-paiporta"
STATION = "saih_jucar:rambla_poyo"
MADRID = ZoneInfo("Europe/Madrid")
HIT_FLOW = 100.0
HORIZON = timedelta(hours=3)
PEAK = datetime(2024, 10, 29, 17, 55, tzinfo=timezone.utc)   # 18:55 local
WAVE2 = datetime(2024, 10, 29, 16, 0, tzinfo=timezone.utc)   # 17:00 local, inicio de la onda principal


def series() -> list[Reading]:
    out = []
    with open(CSV, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ts = datetime.strptime(row["Fecha"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=MADRID).astimezone(timezone.utc)
            if row["Estado"] == "FALLO" or row["Caudal"] == "":
                continue
            out.append(Reading(
                station_id=STATION, source="saih_jucar", name="Rambla del Poyo", lat=39.47537, lon=-0.5818, river="Poyo",
                flow_m3s=float(row["Caudal"].replace(",", ".")), level_m=None, rain_1h_mm=None, rain_24h_mm=None,
                reservoir_pct=None, reservoir_hm3=None, thresholds=None, timestamp_utc=ts, fetched_at_utc=ts, quality="OK"))
    return out


def run(table, data: list[Reading], step_min: int):
    """Simula un colector que lee cada `step_min` minutos. Devuelve disparos por nivel: [(inicio, fin)]."""
    start = data[0].timestamp_utc
    end = PEAK + timedelta(hours=1)
    sampled = [r for r in data if int((r.timestamp_utc - start).total_seconds() // 60) % step_min == 0]
    runs = {"VIGILANCIA": [], "ALERTA": []}
    active: dict[str, datetime] = {}
    t = start
    while t <= end:
        visible = [r for r in sampled if r.timestamp_utc <= t]
        levels = {e["level"] for e in evaluate(table, lambda s: visible, t) if e["link_id"] == LINK}
        on = {"ALERTA": "ALERTA" in levels, "VIGILANCIA": bool(levels)}
        for lv in runs:
            if on[lv] and lv not in active:
                active[lv] = t
            if not on[lv] and lv in active:
                runs[lv].append((active.pop(lv), t))
        t += timedelta(minutes=step_min)
    for lv, t0 in active.items():
        runs[lv].append((t0, end))
    return runs


def judge(runs, data):
    flows = [(r.timestamp_utc, r.flow_m3s) for r in data]
    hits = false = 0
    for t0, _ in runs:
        if any(t0 <= ts <= t0 + HORIZON and q >= HIT_FLOW for ts, q in flows):
            hits += 1
        else:
            false += 1
    first = runs[0][0] if runs else None
    return hits, false, first


def fmt(t):
    return t.astimezone(MADRID).strftime("%d/%m %H:%M") if t else "—"


def main(markdown: bool) -> None:
    base = load_links(ROOT / "engine" / "river_links.yaml")
    data = series()
    print(f"Serie: {len(data)} lecturas con dato; pico {max(r.flow_m3s for r in data)} m3/s a las {fmt(PEAK)}.\n")
    grids = {
        "VIGILANCIA": (("min_flow_m3s", [0.5, 1, 2, 5, 10, 20]), ("flow_rise_pct_1h", [30, 50])),
        "ALERTA": (("min_flow_m3s", [20, 50, 100, 200, 500]), ("flow_rise_pct_1h", [100, 200])),
    }
    for step in (5, 15):
        print(f"### Cadencia de lectura: cada {step} min")
        print("| nivel | min_flow | subida %/h | 1.er disparo (local) | antelación al pico | antelación a la onda principal (17:00) | aciertos | falsas alarmas |")
        print("|---|---|---|---|---|---|---|---|")
        for level, ((_, flows), (_, rises)) in grids.items():
            for mf, rise in itertools.product(flows, rises):
                table = base.with_level(level, min_flow_m3s=mf, flow_rise_pct_1h=rise)
                runs = run(table, data, step)[level]
                hits, false, first = judge(runs, data)
                lead_peak = f"{(PEAK - first).total_seconds() / 3600:.1f} h" if first else "—"
                lead_w2 = f"{(WAVE2 - first).total_seconds() / 3600:.1f} h" if first else "—"
                mark = " ◀" if (level, mf, rise) in {("VIGILANCIA", 5, 30), ("ALERTA", 50, 100)} else ""
                print(f"| {level} | {mf} | {rise} | {fmt(first)} | {lead_peak} | {lead_w2} | {hits} | {false} |{mark}")
        print()


if __name__ == "__main__":
    main("--markdown" in sys.argv)
