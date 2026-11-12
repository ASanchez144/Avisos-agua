"""Genera engine/euskalmet_stations.json desde la API real de Euskalmet (se ejecuta a mano, rara vez).

Uso:
    EUSKALMET_PRIVATE_KEY="$(cat privada.pem)" EUSKALMET_EMAIL=tu@email python scripts/euskalmet_inventory.py
    (o EUSKALMET_JWT=<token> python scripts/euskalmet_inventory.py)

Qué hace (todo con peticiones reales, 1 s entre peticiones):
1. GET /euskalmet/stations → ids de estación.
2. GET /euskalmet/stations/{id}/current → tipo, nombre, municipio, coordenadas (GOOGLE = WGS84 lon/lat).
3. Solo estaciones de aforo (stationType GAUGING) de río: se excluyen mareógrafos (M…) y embalses (E04…),
   cuyo "nivel" es del mar o una cota absoluta, no el calado del río.
4. GET /euskalmet/readings/aggregated/byDay/forStation/{id}/at/AAAA/MM/DD → qué sensor mide
   measuresForWater/sheet_level_* (nivel de la lámina de agua; unidad METERS según /euskalmet/measures).
   Si hay varios, se elige el que tiene más tramos con dato hoy; empate → orden alfabético.

Nunca se escribe ninguna clave en el fichero de salida.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connectors.euskalmet import BASE, USER_AGENT, auth_headers  # noqa: E402

OUT = ROOT / "engine" / "euskalmet_stations.json"


def get(client: httpx.Client, path: str):
    time.sleep(1)
    resp = client.get(BASE + path)
    resp.raise_for_status()
    return json.loads(resp.content.decode("iso-8859-1"))


def main() -> int:
    client = httpx.Client(headers={"User-Agent": USER_AGENT, **auth_headers()}, timeout=60)
    today = datetime.now(timezone.utc)
    ids = sorted({s["stationId"] for s in get(client, "/stations")})
    stations = []
    for sid in ids:
        if sid.startswith(("M", "E")):
            continue
        meta = get(client, f"/stations/{sid}/current")
        if meta.get("stationType") != "GAUGING":
            continue
        pos = meta["position"]["position"]["GOOGLE"]
        agg = get(client, f"/readings/aggregated/byDay/forStation/{sid}/at/{today:%Y/%m/%d}")
        candidates = []
        for item in agg.get("items", []):
            if item.get("measureType") == "measuresForWater" and str(item.get("measureId", "")).startswith("sheet_level_"):
                filled = sum(1 for r in item["readings"] for v in r["values"] if v is not None)
                candidates.append((-filled, item["sensorId"], item["measureId"]))
        if not candidates:
            print(f"{sid}: sin sensor de nivel, se omite", file=sys.stderr)
            continue
        _, sensor, measure = sorted(candidates)[0]
        stations.append({
            "id": sid, "name": meta["name"]["SPANISH"].strip(), "municipality": meta["municipality"]["SPANISH"].strip(),
            "lat": pos["y"], "lon": pos["x"], "level_sensor": sensor, "level_measure": measure,
        })
        print(f"{sid} {stations[-1]['name']}: {sensor} {measure}", file=sys.stderr)
    OUT.write_text(json.dumps({
        "source": "https://api.euskadi.eus/euskalmet (stations/current + readings/aggregated/byDay)",
        "generated_at_utc": today.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stations": stations,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(stations)} estaciones → {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
