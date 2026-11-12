"""Registro de conectores para el arnés de verificación.

Este fichero SÍ se puede ampliar: cada conector nuevo añade aquí su caso.
El arnés (immutable_verification_harness.py) comprueba que todo módulo de
/connectors que declare SOURCE tenga un caso registrado, así que no se puede
"olvidar" un conector para esquivar las leyes.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from connectors import saih_cantabrico
from connectors.base import Reading

TESTS = Path(__file__).resolve().parent


@dataclass(frozen=True)
class OfficialValue:
    """Un valor tal y como se ve en la web oficial."""
    station_id: str
    field: str                 # "flow_m3s" | "level_m" | "threshold:<variable>:<yellow|orange|red>"
    shown: str                 # texto exacto mostrado en la web oficial
    timestamp_utc: Optional[datetime]  # fecha de medida mostrada por la web oficial


@dataclass(frozen=True)
class HarnessCase:
    source: str
    fixture_now: datetime                                  # instante real de captura de la fixture
    parse_fixture: Callable[[], list[Reading]]             # lecturas de la fixture real
    fetch_live: Callable[[], list[Reading]]                # lecturas reales en vivo (1 petición)
    inject: Callable[[dict[str, Any]], Reading]            # fixture real + valores crudos inyectados
    reference_dir: Path                                    # carpeta en tests/reference/
    official_values: Callable[[], list[OfficialValue]]     # valores de la web oficial
    # Variables que la fuente NO publica (arnés v2). El arnés exige que sean nulas
    # en todas las lecturas reales; no vale para saltarse una variable que sí se emite.
    unsupported_fields: frozenset = frozenset()


# ---------------------------------------------------------------- Cantábrico

_CANT_FIXTURE = TESTS / "fixtures" / "saih_cantabrico" / "peticion_cincominutal_todas.json"
_CANT_FETCHED = TESTS / "fixtures" / "saih_cantabrico" / "peticion_cincominutal_todas.fetched_at_utc.txt"
_CANT_REFERENCE = TESTS / "reference" / "saih_cantabrico"
_CANT_INJECT_STATION = "1424"
_MADRID = ZoneInfo("Europe/Madrid")
_NUMERIC = re.compile(r"-?\d+(\.\d+)?")

# campo del esquema -> campo crudo de la fuente
_CANT_RAW = {
    "flow_m3s": "caudal",
    "level_m": "nivel",
    "rain_1h_mm": "precipit_1h",
    "rain_24h_mm": "precipit_24h",
    "thresholds.yellow": "seguimiento_nivel",
    "thresholds.orange": "prealerta_nivel",
    "thresholds.red": "alerta_nivel",
}
_CANT_DATES = ("fecha", "fecha_caudal", "fecha_nivel", "fecha_precipitacion")


def _cant_now() -> datetime:
    return datetime.strptime(_CANT_FETCHED.read_text().strip(), "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )


def _cant_parse_fixture() -> list[Reading]:
    return saih_cantabrico.parse(_CANT_FIXTURE.read_bytes(), _cant_now())


def _cant_fetch_live() -> list[Reading]:
    return saih_cantabrico.SaihCantabricoConnector().fetch()


def _cant_inject(overrides: dict[str, Any]) -> Reading:
    payload = copy.deepcopy(json.loads(_CANT_FIXTURE.read_bytes()))
    feature = next(
        f for f in payload["data"]["features"]
        if f["properties"].get("codigo_general") == _CANT_INJECT_STATION
    )
    props = feature["properties"]
    for field, value in overrides.items():
        if field == "timestamp_utc":
            local = value.astimezone(_MADRID).strftime("%Y-%m-%d %H:%M:%S")
            for key in _CANT_DATES:
                props[key] = local
        elif field == "lat":
            props["lat"] = value
            feature["geometry"]["coordinates"][1] = value
        elif field == "lon":
            props["lon"] = value
            feature["geometry"]["coordinates"][0] = value
        else:
            props[_CANT_RAW[field]] = value
    payload["data"]["features"] = [feature]
    return saih_cantabrico.parse(json.dumps(payload).encode(), _cant_now())[0]


def _cant_official_values() -> list[OfficialValue]:
    """Lee tests/reference/saih_cantabrico/visor_tabla.json (texto de la tabla del visor oficial).

    Columnas: 1 código · 4 nivel · 6-8 umbrales nivel · 11 caudal · 13-15 umbrales
    caudal · 16 "HH:MM | DD-MM-AAAA" (hora local peninsular).
    """
    table = json.loads((_CANT_REFERENCE / "visor_tabla.json").read_text())
    out: list[OfficialValue] = []
    for row in table["rows"]:
        station_id = f"{saih_cantabrico.SOURCE}:{row[1]}"
        try:
            ts = datetime.strptime(row[16], "%H:%M | %d-%m-%Y").replace(tzinfo=_MADRID).astimezone(timezone.utc)
        except ValueError:
            ts = None  # el visor muestra "-" cuando la estación no tiene fecha de medida
        columns = {
            "level_m": 4,
            "threshold:level_m:yellow": 6, "threshold:level_m:orange": 7, "threshold:level_m:red": 8,
            "flow_m3s": 11,
            "threshold:flow_m3s:yellow": 13, "threshold:flow_m3s:orange": 14, "threshold:flow_m3s:red": 15,
        }
        for field, index in columns.items():
            if _NUMERIC.fullmatch(row[index]):  # el visor muestra "" o "-" si no hay valor
                out.append(OfficialValue(station_id, field, row[index], ts))
    return out


CASES: list[HarnessCase] = [
    HarnessCase(
        source=saih_cantabrico.SOURCE,
        fixture_now=_cant_now(),
        parse_fixture=_cant_parse_fixture,
        fetch_live=_cant_fetch_live,
        inject=_cant_inject,
        reference_dir=_CANT_REFERENCE,
        official_values=_cant_official_values,
    ),
]


# ------------------------------------------------------------------- común

class UnsupportedVariable(Exception):
    """La fuente no publica esa variable: no hay campo crudo donde inyectar."""


# ----------------------------------------------------------------------- ACA

from decimal import Decimal  # noqa: E402

from connectors import aca  # noqa: E402

_ACA_FIX = TESTS / "fixtures" / "aca"
_ACA_REFERENCE = TESTS / "reference" / "aca"
_ACA_COMPONENT = "080060-001"
_ACA_SENSORS = {"flow_m3s": "CALC001658", "level_m": "080060-001-ANA01"}
_ACA_UNSUPPORTED = {"rain_1h_mm", "rain_24h_mm", "thresholds.yellow", "thresholds.orange", "thresholds.red"}


def _aca_now() -> datetime:
    text = (_ACA_FIX / "live.fetched_at_utc.txt").read_text().strip()
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _aca_payloads() -> dict[str, Any]:
    names = ("catalog_aforament", "catalog_embassament", "data_AFORAMENT-EST", "data_EMBASSAMENT-EST")
    return {n: json.loads((_ACA_FIX / f"live_{n}.json").read_bytes()) for n in names}


def _aca_parse(payloads: dict[str, Any]) -> list[Reading]:
    raw = {k: json.dumps(v).encode() for k, v in payloads.items()}
    return aca.parse(
        [raw["catalog_aforament"], raw["catalog_embassament"]],
        [raw["data_AFORAMENT-EST"], raw["data_EMBASSAMENT-EST"]],
        _aca_now(),
    )


def _aca_inject(overrides: dict[str, Any]) -> Reading:
    unsupported = set(overrides) & _ACA_UNSUPPORTED
    if unsupported:
        raise UnsupportedVariable(f"aca no publica {sorted(unsupported)}")
    payloads = _aca_payloads()
    observations = {s["sensor"]: s["observations"][0] for s in payloads["data_AFORAMENT-EST"]["sensors"]}
    catalog = [s for s in payloads["catalog_aforament"]["providers"][0]["sensors"] if s["component"] == _ACA_COMPONENT]
    lat, lon = catalog[0]["location"].split()
    for field, value in overrides.items():
        if field == "flow_m3s":
            observations[_ACA_SENSORS[field]]["value"] = repr(value)
        elif field == "level_m":
            observations[_ACA_SENSORS[field]]["value"] = repr(value * 100)  # la fuente da cm
        elif field == "timestamp_utc":
            for sensor in _ACA_SENSORS.values():
                observations[sensor]["time"] = int(value.timestamp() * 1000)
        elif field == "lat":
            lat = repr(value)
        elif field == "lon":
            lon = repr(value)
    for sensor in catalog:
        sensor["location"] = f"{lat} {lon}"
    return next(r for r in _aca_parse(payloads) if r.station_id == f"{aca.SOURCE}:{_ACA_COMPONENT}")


def _aca_official_values() -> list[OfficialValue]:
    """Datos que el visor oficial https://aetr.aca.gencat.cat/ carga para pintar aforos y
    embalses (tests/reference/aca/). El visor da el nivel en cm: se pasa a m desplazando
    la coma con Decimal (conversión exacta, sin redondeo)."""
    layers = {
        "aca.sensor.river_flow": ("flow_m3s", 0), "aca.sensor.river_level": ("level_m", -2),
        "aca.sensor.capacity": ("reservoir_pct", 0), "aca.sensor.volume": ("reservoir_hm3", 0),
    }
    codes: dict[str, str] = {}
    for name in ("catalog_aforaments.json", "catalog_embassaments.json"):
        for feature in json.loads((_ACA_REFERENCE / name).read_text())["features"]:
            codes[feature["id"]] = feature["properties"]["code"]
    out: list[OfficialValue] = []
    for name in ("timeline_aca.sensor.river_flow.json", "timeline_aca.sensor.capacity.json"):
        for layer in json.loads((_ACA_REFERENCE / name).read_text()):
            if layer.get("alias") not in layers:
                continue
            field, shift = layers[layer["alias"]]
            for element, series in layer["values"].items():
                if element not in codes:
                    continue
                for stamp, shown in series:
                    if not _NUMERIC.fullmatch(shown):
                        continue
                    ts = datetime.strptime(stamp, "%m/%d/%Y %H:%M:%S %z").astimezone(timezone.utc)
                    text = format(Decimal(shown).scaleb(shift), "f") if shift else shown
                    out.append(OfficialValue(f"{aca.SOURCE}:{codes[element]}", field, text, ts))
    return out


CASES.append(HarnessCase(
    source=aca.SOURCE, fixture_now=_aca_now(), parse_fixture=lambda: _aca_parse(_aca_payloads()),
    fetch_live=lambda: aca.AcaConnector().fetch(), inject=_aca_inject,
    reference_dir=_ACA_REFERENCE, official_values=_aca_official_values,
    unsupported_fields=frozenset(_ACA_UNSUPPORTED),
))


# --------------------------------------------------------------------- AEMET

import gzip  # noqa: E402

from connectors import aemet  # noqa: E402

_AEMET_FIX = TESTS / "fixtures" / "aemet"
_AEMET_REFERENCE = TESTS / "reference" / "aemet"
_AEMET_STATION = "3526X"
_AEMET_UNSUPPORTED = {"flow_m3s", "level_m", "rain_24h_mm", "thresholds.yellow", "thresholds.orange", "thresholds.red"}


def _aemet_now() -> datetime:
    text = (_AEMET_FIX / "observacion.fetched_at_utc.txt").read_text().strip()
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _aemet_raw() -> bytes:
    return gzip.open(_AEMET_FIX / "observacion_convencional_todas_datos.json.gz").read()


def _aemet_inject(overrides: dict[str, Any]) -> Reading:
    unsupported = set(overrides) & _AEMET_UNSUPPORTED
    if unsupported:
        raise UnsupportedVariable(f"aemet no publica {sorted(unsupported)}")
    records = [r for r in json.loads(_aemet_raw().decode("iso-8859-15")) if r["idema"] == _AEMET_STATION]
    record = max(records, key=lambda r: r["fint"])
    raw_keys = {"rain_1h_mm": "prec", "lat": "lat", "lon": "lon"}
    for field, value in overrides.items():
        if field == "timestamp_utc":
            record["fint"] = value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
        else:
            record[raw_keys[field]] = value
    return aemet.parse_observations(json.dumps([record]).encode(), _aemet_now())[0]


def _aemet_official_values() -> list[OfficialValue]:
    """Datos que la web oficial www.aemet.es sirve para su tabla "Hoy y últimos días"
    (tests/reference/aemet/web_tablas_graficas_horario_esp.xml)."""
    xml = (_AEMET_REFERENCE / "web_tablas_graficas_horario_esp.xml").read_text(encoding="iso-8859-15")
    out: list[OfficialValue] = []
    for station in re.finditer(r'<estacion [^>]*id_c="([^"]+)"[^>]*>(.*?)</estacion>', xml, re.S):
        for period in re.finditer(r'<periodo utc="([^"]+)"[^>]*>(.*?)</periodo>', station.group(2), re.S):
            rain = re.search(r"<precipitacion>([^<]*)</precipitacion>", period.group(2))
            if rain and _NUMERIC.fullmatch(rain.group(1)):
                ts = datetime.strptime(period.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                out.append(OfficialValue(f"{aemet.SOURCE}:{station.group(1)}", "rain_1h_mm", rain.group(1), ts))
    return out


CASES.append(HarnessCase(
    source=aemet.SOURCE, fixture_now=_aemet_now(),
    parse_fixture=lambda: aemet.parse_observations(_aemet_raw(), _aemet_now()),
    fetch_live=lambda: aemet.AemetConnector().fetch(), inject=_aemet_inject,
    reference_dir=_AEMET_REFERENCE, official_values=_aemet_official_values,
    unsupported_fields=frozenset(_AEMET_UNSUPPORTED),
))


# ----------------------------------------------------------------- Euskalmet

from connectors import euskalmet  # noqa: E402

_EUS_FIX = TESTS / "fixtures" / "euskalmet"
_EUS_REFERENCE = TESTS / "reference" / "euskalmet"
_EUS_STATION = "C084"
# La API publica el caudal sin unidad, la lluvia solo por tramos de 10 min y ningún umbral.
_EUS_UNSUPPORTED = {"flow_m3s", "rain_1h_mm", "rain_24h_mm", "thresholds.yellow", "thresholds.orange", "thresholds.red"}


def _eus_now() -> datetime:
    text = (_EUS_FIX / "readings_hourly.fetched_at_utc.txt").read_text().strip()
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _eus_responses() -> dict[str, dict[str, Any]]:
    raw = json.loads((_EUS_FIX / "readings_hourly.json").read_text(encoding="utf-8"))["responses"]
    return {path: json.loads(body) for path, body in raw.items()}


def _eus_parse(responses: dict[str, dict[str, Any]], inventory: list[dict[str, Any]]) -> list[Reading]:
    payloads: dict[str, list[bytes]] = {}
    for path in sorted(responses, reverse=True):  # la hora más reciente primero
        station = path.split("/")[3]
        payloads.setdefault(station, []).append(json.dumps(responses[path]).encode("iso-8859-1"))
    return euskalmet.parse(inventory, payloads, _eus_now())


def _eus_inject(overrides: dict[str, Any]) -> Reading:
    unsupported = set(overrides) & _EUS_UNSUPPORTED
    if unsupported:
        raise UnsupportedVariable(f"euskalmet no publica {sorted(unsupported)}")
    responses = _eus_responses()
    inventory = copy.deepcopy(euskalmet.load_inventory())
    station = next(s for s in inventory if s["id"] == _EUS_STATION)
    path = max(p for p in responses if p.split("/")[3] == _EUS_STATION)
    hour = responses[path]
    index = max(i for i, v in enumerate(hour["values"]) if v is not None)
    for field, value in overrides.items():
        if field == "level_m":
            hour["values"][index] = value
        elif field == "timestamp_utc":
            start = value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
            current = hour["values"][index]
            hour["values"] = [None] * len(hour["values"])
            index = value.astimezone(timezone.utc).minute // 10
            hour["values"][index] = current
            ms = int(start.timestamp() * 1000)
            hour["dateRange"] = f"Date:({ms}..{ms + 3599999})"
        elif field in ("lat", "lon"):
            station[field] = value
    for other in [p for p in responses if p.split("/")[3] == _EUS_STATION and p != path]:
        del responses[other]  # solo la hora inyectada
    return next(r for r in _eus_parse(responses, inventory) if r.station_id == f"{euskalmet.SOURCE}:{_EUS_STATION}")


def _eus_official_values() -> list[OfficialValue]:
    """Series que la web oficial www.euskalmet.euskadi.eus carga para su gráfica de estación
    (tests/reference/euskalmet/web_<estación>_<AAAAMMDD>.json). Horas "HH:MM" locales = inicio del
    tramo de 10 min. Solo se compara la medida de nivel que usa el conector (inventario)."""
    measure = {s["id"]: s["level_measure"] for s in euskalmet.load_inventory()}
    out: list[OfficialValue] = []
    for file in sorted(_EUS_REFERENCE.glob("web_*.json")):
        _, station, day = file.stem.split("_")
        for entry in json.loads(file.read_bytes().decode("iso-8859-1")).values():
            if entry.get("type") != "measuresForWater" or entry.get("name") != measure.get(station):
                continue
            for series in entry["data"].values():
                for clock, shown in series.items():
                    local = datetime.strptime(f"{day} {clock}", "%Y%m%d %H:%M").replace(tzinfo=_MADRID)
                    out.append(OfficialValue(f"{euskalmet.SOURCE}:{station}", "level_m", repr(shown),
                                             local.astimezone(timezone.utc)))
    return out


CASES.append(HarnessCase(
    source=euskalmet.SOURCE, fixture_now=_eus_now(),
    parse_fixture=lambda: _eus_parse(_eus_responses(), euskalmet.load_inventory()),
    fetch_live=lambda: euskalmet.EuskalmetConnector().fetch(), inject=_eus_inject,
    reference_dir=_EUS_REFERENCE, official_values=_eus_official_values,
    unsupported_fields=frozenset(_EUS_UNSUPPORTED),
))


# ------------------------------------------------------------------ Hidrosur

from connectors import hidrosur  # noqa: E402

_HS_FIX = TESTS / "fixtures" / "hidrosur"
_HS_REFERENCE = TESTS / "reference" / "hidrosur"
_HS_STATION = "9"
_HS_UNSUPPORTED = {"rain_1h_mm", "rain_24h_mm"}  # la tabla de ríos no trae lluvia


def _hs_now() -> datetime:
    text = (_HS_FIX / "fetched_at_utc.txt").read_text().strip()
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _hs_parse(table: str, layer: dict[str, Any]) -> list[Reading]:
    return hidrosur.parse(table.encode("utf-8"), json.dumps(layer).encode(), _hs_now())


def _hs_inject(overrides: dict[str, Any]) -> Reading:
    unsupported = set(overrides) & _HS_UNSUPPORTED
    if unsupported:
        raise UnsupportedVariable(f"hidrosur no publica {sorted(unsupported)}")
    table = (_HS_FIX / "resumen_rios.html").read_text(encoding="utf-8")
    layer = json.loads((_HS_FIX / "capa_aforos.json").read_text(encoding="utf-8"))
    place = next(f["properties"] for f in layer["features"] if str(f["properties"]["COD_"]) == _HS_STATION)
    row_re = re.compile(r"(<tr[^>]*>\s*<td[^>]*>\s*" + _HS_STATION + r"\s*</td>.*?</tr>)", re.S)
    row = row_re.search(table).group(1)
    cells = re.findall(r"(<td[^>]*>)(.*?)(</td>)", row, re.S)
    new_cells = [c[1] for c in cells]
    keys = {"thresholds.yellow": "Aviso", "thresholds.orange": "Prealerta", "thresholds.red": "Alerta",
            "lat": "Latitud", "lon": "Longitud"}
    for field, value in overrides.items():
        if field == "level_m":
            new_cells[2] = repr(value).replace(".", ",")
        elif field == "flow_m3s":
            new_cells[3] = repr(value).replace(".", ",")
        elif field == "timestamp_utc":
            local = value.astimezone(_MADRID).strftime("%d-%m-%Y %H:%M:%S")
            table = re.sub(r"Datos actualizados a:\s*\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}", "Datos actualizados a: " + local, table)
        else:
            place[keys[field]] = value
    rebuilt = row
    for (open_, old, close), new in zip(cells, new_cells):
        rebuilt = rebuilt.replace(open_ + old + close, open_ + new + close, 1)
    table = table.replace(row, rebuilt)
    return next(r for r in _hs_parse(table, layer) if r.station_id == f"{hidrosur.SOURCE}:{_HS_STATION}")


def _hs_official_values() -> list[OfficialValue]:
    """Gráficas oficiales /saih/mapa/tiempo/real/grafica/<código> (tests/reference/hidrosur/): serie
    horaria del nivel (m., hora local "dd/mm/aa HH:MM") y líneas "Nivel 1/2/3" = umbrales."""
    out: list[OfficialValue] = []
    for file in sorted(_HS_REFERENCE.glob("grafica_*.html")):
        page = file.read_text(encoding="utf-8")
        station = f"{hidrosur.SOURCE}:{int(file.stem.split('_')[1][:3])}"
        labels = json.loads(re.search(r"var labels = (\[.*?\]);", page, re.S).group(1))
        serie = re.search(r"var serie1 = (\[.*?\]);", page, re.S).group(1)
        values = [v.strip() for v in serie.strip("[]").split(",")]
        for label, shown in zip(labels, values):
            if _NUMERIC.fullmatch(shown):
                ts = datetime.strptime(label, "%d/%m/%y %H:%M").replace(tzinfo=_MADRID).astimezone(timezone.utc)
                out.append(OfficialValue(station, "level_m", shown, ts))
        for n, colour in ((1, "yellow"), (2, "orange"), (3, "red")):
            m = re.search(r"label: 'Nivel " + str(n) + r"'.*?return ([-\d.]+);", page, re.S)
            if m:
                out.append(OfficialValue(station, f"threshold:level_m:{colour}", m.group(1), None))
    return out


CASES.append(HarnessCase(
    source=hidrosur.SOURCE, fixture_now=_hs_now(),
    parse_fixture=lambda: _hs_parse((_HS_FIX / "resumen_rios.html").read_text(encoding="utf-8"),
                                    json.loads((_HS_FIX / "capa_aforos.json").read_text(encoding="utf-8"))),
    fetch_live=lambda: hidrosur.HidrosurConnector().fetch(), inject=_hs_inject,
    reference_dir=_HS_REFERENCE, official_values=_hs_official_values,
    unsupported_fields=frozenset(_HS_UNSUPPORTED),
))
