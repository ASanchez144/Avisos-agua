"""Mide la longitud de un cauce con la geometría pública de OpenStreetMap (Overpass).

Uso (desde un PC con acceso a internet normal):
    python scripts/measure_channel.py "Rambla del Poyo" --bbox 39.30,-0.95,39.55,-0.35
    python scripts/measure_channel.py "Barranco del Poyo" --bbox 39.30,-0.95,39.55,-0.35

Imprime la longitud total de los tramos que casan con el nombre y la guarda en
tests/fixtures/osm/<nombre>.json con fecha y URL, para citarla en river_links.yaml.
Solo `requests`. Datos © colaboradores de OpenStreetMap (ODbL).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

UA = "HidroRed/0.1 (radar ciudadano hidrologico no oficial; medicion de cauces)"
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def haversine(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--bbox", required=True, help="sur,oeste,norte,este")
    args = ap.parse_args()
    query = f'[out:json][timeout:60];way["waterway"]["name"~"{args.name}",i]({args.bbox});out geom tags;'
    data, used = None, None
    for url in ENDPOINTS:
        try:
            r = requests.post(url, data={"data": query}, headers={"User-Agent": UA}, timeout=90)
            r.raise_for_status()
            data, used = r.json(), url
            break
        except requests.RequestException as exc:
            print(f"{url}: {exc}", file=sys.stderr)
    if data is None:
        print("No se pudo consultar Overpass.", file=sys.stderr)
        return 1
    total = 0.0
    for way in data["elements"]:
        pts = [(n["lat"], n["lon"]) for n in way.get("geometry", [])]
        km = sum(haversine(a, b) for a, b in zip(pts, pts[1:]))
        total += km
        print(f'  way {way["id"]}: {way["tags"].get("name")} ({way["tags"].get("waterway")}) {km:.2f} km')
    print(f"TOTAL de los tramos que casan con '{args.name}': {total:.2f} km (suma de tramos; revisa que no haya duplicados ni afluentes)")
    out = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "osm"
    out.mkdir(parents=True, exist_ok=True)
    (out / (args.name.lower().replace(" ", "_") + ".json")).write_text(json.dumps(
        {"fetched_at_utc": datetime.now(timezone.utc).isoformat(), "url": used, "query": query, "total_km": round(total, 2), "response": data}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
