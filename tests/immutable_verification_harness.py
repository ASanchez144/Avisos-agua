"""ARNÉS DE VERIFICACIÓN INMUTABLE — HidroRed España (v2).

NO MODIFICAR tras su creación. Su hash está en tests/HARNESS.sha256 y lo
vigila scripts/check_harness_hash.sh. Si un test falla se corrige el conector,
nunca el arnés. Si una ley parece incorrecta, se consulta al responsable.

Historial: v2 (2026-11-11, aprobada por el responsable). Único cambio respecto
a v1: un conector puede declarar en el registro las variables que su fuente NO
publica (`unsupported_fields`). Para ellas se omite la inyección de L7 (no hay
campo crudo donde inyectar) y, a cambio, se exige que esas variables sean nulas
en el 100% de las lecturas reales. Las leyes L1–L8 no cambian.

Leyes, aplicadas a CADA lectura de CADA conector (esquema común):

  L1  flow_m3s >= 0, no NaN, <= 15000.
  L2  level_m entre -2.0 y 60.0.
  L3  rain_1h_mm >= 0 y rain_24h_mm >= rain_1h_mm.
  L4  lat entre 27.5 y 43.9, lon entre -18.5 y 4.5.
  L5  Si hay umbrales: yellow < orange < red. Los umbrales nulos están permitidos.
  L6  timestamp_utc no está en el futuro (tolerancia 5 min) y no tiene más de
      7 días de antigüedad en una lectura "en vivo".
  L7  Un valor fuera de rango NO se corrige ni se recorta: la lectura se marca
      quality=SUSPECT y se excluye de alertas.
  L8  Contraste real: al menos una lectura por conector coincide con el valor
      visible en la web oficial (referencia en tests/reference/).

Cómo se aplican:

  * L1–L6 se evalúan aquí de forma independiente (no se reutiliza el código
    de /engine). Una lectura que incumple alguna debe salir quality=SUSPECT;
    una lectura quality=OK no puede incumplir ninguna.
  * L7 se comprueba (a) sobre los datos reales: toda lectura que incumple una
    ley es SUSPECT y no produce NORMAL/VIGILANCIA/PREALERTA/ALERTA; y (b)
    inyectando valores fuera de rango en la respuesta real de la fuente: el
    valor debe salir EXACTAMENTE igual (sin recorte) y la lectura SUSPECT.
  * L8 compara la fixture real con el texto capturado de la web oficial en el
    mismo ciclo de medida.

Tolerancia de L8 (justificación): solo se comparan valores cuya fecha de
medida en la web oficial es idéntica al timestamp_utc de la lectura, es decir,
la MISMA medida. La única diferencia legítima es el redondeo de presentación
de la web. Por eso la tolerancia es media unidad del último decimal mostrado:
"0.75" → ±0.005; "147" → ±0.5; "0.6" → ±0.05. No se admite ninguna
tolerancia física ni temporal.

Modos:

  * Por defecto: fixtures reales de la Fase 0; "ahora" = instante de captura.
  * En vivo: HIDRORED_HARNESS_LIVE=1 hace UNA petición real por conector y
    aplica L1–L7 con "ahora" = reloj actual. L8 usa siempre el par congelado
    fixture + referencia (los valores en vivo ya habrán cambiado).

Ejecución:  python -m pytest tests/immutable_verification_harness.py -v -rP
"""
from __future__ import annotations

import math
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from engine.status import station_status  # noqa: E402
from harness_connectors import CASES  # noqa: E402

LIVE = os.environ.get("HIDRORED_HARNESS_LIVE") == "1"
MODES = ["fixture", "live"]
SCHEMA = {
    "station_id", "source", "name", "lat", "lon", "river", "flow_m3s", "level_m",
    "rain_1h_mm", "rain_24h_mm", "reservoir_pct", "reservoir_hm3", "thresholds",
    "timestamp_utc", "fetched_at_utc", "quality",
}
QUALITIES = {"OK", "SUSPECT", "MISSING"}
ALERT_OR_GREEN = {"NORMAL", "VIGILANCIA", "PREALERTA", "ALERTA"}
CASE_IDS = [c.source for c in CASES]


# ------------------------------------------------------------------ leyes

def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def law_L1(r, now) -> bool:
    v = r.flow_m3s
    return v is None or (_is_number(v) and not math.isnan(v) and 0 <= v <= 15000)


def law_L2(r, now) -> bool:
    v = r.level_m
    return v is None or (_is_number(v) and not math.isnan(v) and -2.0 <= v <= 60.0)


def law_L3(r, now) -> bool:
    r1, r24 = r.rain_1h_mm, r.rain_24h_mm
    for v in (r1, r24):
        if v is not None and (not _is_number(v) or math.isnan(v)):
            return False
    if r1 is not None and r1 < 0:
        return False
    if r1 is not None and r24 is not None and r24 < r1:
        return False
    return True


def law_L4(r, now) -> bool:
    lat, lon = r.lat, r.lon
    if not (_is_number(lat) and _is_number(lon)):
        return False
    if math.isnan(lat) or math.isnan(lon):
        return False
    return 27.5 <= lat <= 43.9 and -18.5 <= lon <= 4.5


def law_L5(r, now) -> bool:
    if not r.thresholds:
        return True
    present = [r.thresholds.get(k) for k in ("yellow", "orange", "red")]
    present = [v for v in present if v is not None]
    if any(not _is_number(v) or math.isnan(v) for v in present):
        return False
    return all(a < b for a, b in zip(present, present[1:]))


def law_L6(r, now) -> bool:
    ts = r.timestamp_utc
    if ts is None:
        return True  # sin medida no hay fecha que juzgar (la lectura no puede ser OK: ver test)
    if ts.tzinfo is None:
        return False
    return now - timedelta(days=7) <= ts <= now + timedelta(minutes=5)


LAWS = {"L1": law_L1, "L2": law_L2, "L3": law_L3, "L4": law_L4, "L5": law_L5, "L6": law_L6}


def broken_laws(r, now) -> list[str]:
    return [name for name, law in LAWS.items() if not law(r, now)]


# --------------------------------------------------------------- lecturas

@lru_cache(maxsize=None)
def _load(source: str, mode: str):
    case = next(c for c in CASES if c.source == source)
    if mode == "fixture":
        return tuple(case.parse_fixture()), case.fixture_now
    readings = tuple(case.fetch_live())  # una sola petición real por sesión
    return readings, datetime.now(timezone.utc)


def load(case, mode):
    if mode == "live" and not LIVE:
        pytest.skip("modo en vivo desactivado (HIDRORED_HARNESS_LIVE=1 para activarlo)")
    return _load(case.source, mode)


def describe(r) -> str:
    return (
        f"{r.station_id} q={r.quality} flow={r.flow_m3s} level={r.level_m} rain1h={r.rain_1h_mm} "
        f"rain24h={r.rain_24h_mm} lat={r.lat} lon={r.lon} th={r.thresholds} ts={r.timestamp_utc}"
    )


# ------------------------------------------------- integridad del registro

def test_hay_al_menos_un_conector_registrado():
    assert len(CASES) >= 1
    assert len(set(CASE_IDS)) == len(CASE_IDS)


def test_todo_conector_del_repositorio_esta_en_el_arnes():
    declared = set()
    for path in (ROOT / "connectors").glob("*.py"):
        match = re.search(r'^SOURCE\s*=\s*["\']([^"\']+)["\']', path.read_text(encoding="utf-8"), re.M)
        if match:
            declared.add(match.group(1))
    assert declared, "ningún módulo de /connectors declara SOURCE"
    assert declared <= set(CASE_IDS), f"conectores sin caso en el arnés: {sorted(declared - set(CASE_IDS))}"


# ------------------------------------------------- esquema y datos mínimos

@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_esquema_comun_en_cada_lectura(case, mode):
    readings, now = load(case, mode)
    assert len(readings) > 0, "el conector no devolvió ninguna lectura"
    ids = [r.station_id for r in readings]
    assert len(ids) == len(set(ids)), "station_id repetido"
    for r in readings:
        d = r.to_dict()
        assert set(d) == SCHEMA, f"esquema incorrecto en {r.station_id}: {sorted(set(d) ^ SCHEMA)}"
        assert d["source"] == case.source
        assert d["quality"] in QUALITIES
        assert isinstance(r.fetched_at_utc, datetime) and r.fetched_at_utc.tzinfo is not None
        if r.thresholds is not None:
            assert {"yellow", "orange", "red"} <= set(r.thresholds)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_hay_lecturas_ok_y_una_lectura_ok_tiene_fecha_y_algun_valor(case, mode):
    readings, now = load(case, mode)
    ok = [r for r in readings if r.quality == "OK"]
    assert ok, "ninguna lectura con quality=OK: el conector no está aportando datos válidos"
    for r in ok:
        assert r.timestamp_utc is not None, f"lectura OK sin timestamp: {describe(r)}"
        values = (r.flow_m3s, r.level_m, r.rain_1h_mm, r.rain_24h_mm, r.reservoir_pct, r.reservoir_hm3)
        assert any(v is not None for v in values), f"lectura OK sin ningún valor: {describe(r)}"


# ------------------------------------------------------------------ L1–L6

@pytest.mark.parametrize("law", list(LAWS))
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_L1_a_L6_ninguna_lectura_ok_incumple_la_ley(case, mode, law):
    readings, now = load(case, mode)
    offenders = [describe(r) for r in readings if r.quality == "OK" and not LAWS[law](r, now)]
    assert not offenders, f"{law} incumplida por lecturas quality=OK:\n" + "\n".join(offenders)


# --------------------------------------------------------------------- L7

@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_L7_toda_lectura_que_incumple_una_ley_es_suspect(case, mode):
    readings, now = load(case, mode)
    offenders = [
        f"{broken_laws(r, now)} {describe(r)}"
        for r in readings
        if broken_laws(r, now) and r.quality != "SUSPECT"
    ]
    assert not offenders, "lecturas fuera de ley sin marcar SUSPECT:\n" + "\n".join(offenders)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_L7_suspect_y_missing_quedan_fuera_de_alertas_y_nunca_en_verde(case, mode):
    readings, now = load(case, mode)
    offenders = []
    for r in readings:
        if r.quality in ("SUSPECT", "MISSING"):
            status = station_status(r, now)["status"]
            if status in ALERT_OR_GREEN:
                offenders.append(f"status={status} {describe(r)}")
    assert not offenders, "lecturas no fiables con semáforo:\n" + "\n".join(offenders)


def _injections(now):
    """(descripción, valores crudos inyectados, valores que deben salir intactos)."""
    return [
        ("L1 caudal sobre el máximo", {"flow_m3s": 15000.5}, {"flow_m3s": 15000.5}),
        ("L1 caudal negativo", {"flow_m3s": -3.25}, {"flow_m3s": -3.25}),
        ("L2 nivel sobre el máximo", {"level_m": 75.25}, {"level_m": 75.25}),
        ("L2 nivel bajo el mínimo", {"level_m": -2.5}, {"level_m": -2.5}),
        ("L3 lluvia 1h negativa", {"rain_1h_mm": -1.5}, {"rain_1h_mm": -1.5}),
        ("L3 lluvia 24h < 1h", {"rain_1h_mm": 50.0, "rain_24h_mm": 10.0}, {"rain_1h_mm": 50.0, "rain_24h_mm": 10.0}),
        ("L4 latitud fuera de España", {"lat": 50.0}, {"lat": 50.0}),
        ("L4 longitud fuera de España", {"lon": 9.75}, {"lon": 9.75}),
        ("L5 umbrales desordenados", {"thresholds.yellow": 5.0, "thresholds.orange": 4.0}, {}),
        ("L6 fecha en el futuro", {"timestamp_utc": now + timedelta(hours=1)}, {}),
        ("L6 fecha de hace 8 días", {"timestamp_utc": now - timedelta(days=8)}, {}),
    ]


@pytest.mark.parametrize("index", range(11))
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_L7_valor_fuera_de_rango_no_se_corrige_ni_se_recorta(case, index):
    now = case.fixture_now
    label, overrides, intact = _injections(now)[index]
    not_published = sorted(set(overrides) & set(case.unsupported_fields))
    if not_published:
        pytest.skip(f"[{label}] la fuente {case.source} no publica {not_published}")
    r = case.inject(overrides)
    assert broken_laws(r, now), f"[{label}] la inyección no llegó a la lectura: {describe(r)}"
    for field, value in intact.items():
        assert getattr(r, field) == value, (
            f"[{label}] {field} se alteró: entró {value!r}, salió {getattr(r, field)!r}"
        )
    if "thresholds.yellow" in overrides:
        assert r.thresholds["yellow"] == overrides["thresholds.yellow"]
        assert r.thresholds["orange"] == overrides["thresholds.orange"]
    assert r.quality == "SUSPECT", f"[{label}] debía ser SUSPECT: {describe(r)}"
    assert station_status(r, now)["status"] not in ALERT_OR_GREEN, f"[{label}] genera semáforo"


# ------------------------------------------- variables no publicadas (v2)

DECLARABLE = {
    "flow_m3s", "level_m", "rain_1h_mm", "rain_24h_mm",
    "thresholds.yellow", "thresholds.orange", "thresholds.red",
}
MEASURED = {"flow_m3s", "level_m", "rain_1h_mm", "rain_24h_mm"}


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_v2_solo_se_pueden_declarar_no_publicadas_variables_de_medida_o_umbral(case):
    declared = set(case.unsupported_fields)
    assert declared <= DECLARABLE, f"no declarables: {sorted(declared - DECLARABLE)} (lat, lon y fecha son obligatorias)"
    assert MEASURED - declared, "un conector debe publicar al menos una variable de medida inyectable"


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_v2_una_variable_declarada_no_publicada_es_nula_en_todas_las_lecturas(case, mode):
    readings, now = load(case, mode)
    offenders = []
    for r in readings:
        for field in case.unsupported_fields:
            if field.startswith("thresholds."):
                value = (r.thresholds or {}).get(field.split(".", 1)[1])
            else:
                value = getattr(r, field)
            if value is not None:
                offenders.append(f"{field}={value!r} en {r.station_id}")
    assert not offenders, "variables declaradas como no publicadas que sí se emiten:\n" + "\n".join(offenders[:20])


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_L7_la_inyeccion_neutra_no_marca_suspect(case):
    """Control: sin valores fuera de rango, la misma estación sale OK."""
    r = case.inject({})
    assert broken_laws(r, case.fixture_now) == []
    assert r.quality == "OK", describe(r)


# --------------------------------------------------------------------- L8

def _tolerance(shown: str) -> float:
    decimals = len(shown.split(".")[1]) if "." in shown else 0
    return 0.5 * 10 ** (-decimals) + 1e-9


def _contrast(case):
    readings = {r.station_id: r for r in case.parse_fixture()}
    compared, mismatches = [], []
    for official in case.official_values():
        r = readings.get(official.station_id)
        if r is None or r.quality != "OK":
            continue
        if official.field.startswith("threshold:"):
            _, variable, colour = official.field.split(":")
            if not r.thresholds or r.thresholds.get("variable") != variable:
                continue
            ours = r.thresholds.get(colour)
        else:
            if official.timestamp_utc is None or official.timestamp_utc != r.timestamp_utc:
                continue  # no es la misma medida: no se compara
            ours = getattr(r, official.field)
        if ours is None:
            continue
        shown = float(official.shown)
        line = f"{official.station_id} {official.field}: web oficial={official.shown} conector={ours}"
        compared.append((official.field, line))
        if abs(ours - shown) > _tolerance(official.shown):
            mismatches.append(line)
    return compared, mismatches


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_L8_existe_referencia_de_la_web_oficial(case):
    files = [p for p in case.reference_dir.rglob("*") if p.is_file()]
    assert case.reference_dir.is_dir() and files, f"falta la referencia en {case.reference_dir}"
    assert (ROOT / "tests" / "reference") in case.reference_dir.parents
    assert len(case.official_values()) >= 1


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_L8_las_lecturas_coinciden_con_la_web_oficial(case):
    compared, mismatches = _contrast(case)
    measured = [line for field, line in compared if not field.startswith("threshold:")]
    assert len(measured) >= 1, "ninguna lectura comparable con la web oficial"
    assert not mismatches, "discrepancias con la web oficial:\n" + "\n".join(mismatches)
    thresholds = len(compared) - len(measured)
    print(f"[{case.source}] L8: {len(measured)} medidas y {thresholds} umbrales coinciden con la web oficial")
    for line in measured[:5]:
        print("   ", line)


# ---------------------------------------------------------------- resumen

@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_resumen(case, mode):
    readings, now = load(case, mode)
    by_quality = {q: sum(1 for r in readings if r.quality == q) for q in sorted(QUALITIES)}
    by_law = {name: sum(1 for r in readings if not law(r, now)) for name, law in LAWS.items()}
    print(f"[{case.source}] modo={mode} ahora={now.isoformat()} lecturas={len(readings)}")
    print(f"    calidad: {by_quality}")
    print(f"    lecturas que incumplen cada ley (todas SUSPECT): {by_law}")
    assert sum(by_quality.values()) == len(readings)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-rP", *sys.argv[1:]]))
