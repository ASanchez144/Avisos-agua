"""Motor de propagación: series sintéticas + episodio real (DANA 29/10/2024, Rambla del Poyo)."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from connectors.base import Reading
from engine.geo import haversine_km
from engine.propagation import LABEL, evaluate, load_links

ROOT = Path(__file__).resolve().parent.parent
LINKS = load_links(ROOT / "engine" / "river_links.yaml")
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def lectura(station, minutes_ago=5, now=NOW, **kw) -> Reading:
    base = dict(
        station_id=station, source=station.split(":")[0], name=station, lat=42.0, lon=-1.0, river=None,
        flow_m3s=None, level_m=None, rain_1h_mm=None, rain_24h_mm=None, reservoir_pct=None, reservoir_hm3=None,
        thresholds=None, timestamp_utc=now - timedelta(minutes=minutes_ago), fetched_at_utc=now, quality="OK",
    )
    base.update(kw)
    return Reading(**base)


class Datos:
    """Histórico en memoria: station_id -> lecturas."""

    def __init__(self, *readings: Reading):
        self.by: dict[str, list[Reading]] = {}
        for r in readings:
            self.by.setdefault(r.station_id, []).append(r)

    def history(self, station_id: str) -> list[Reading]:
        return sorted(self.by.get(station_id, []), key=lambda r: r.timestamp_utc, reverse=True)


def activos(datos: Datos, now=NOW, links=LINKS):
    return evaluate(links, datos.history, now)


def link(link_id):
    return next(l for l in LINKS.links if l.id == link_id)


JACA, YESA = "saih_ebro:A018", "saih_ebro:A101"


# ------------------------------------------------------------------- tabla

def test_la_tabla_incluye_la_cadena_del_aragon_y_el_barranco_del_poyo():
    ids = [l.id for l in LINKS.links]
    for esperado in ("aragon-jaca-yesa", "aragon-yesa-caparroso", "aragon-caparroso-ebro-zaragoza", "poyo-chiva-aforo"):
        assert esperado in ids
    assert link("aragon-jaca-yesa").origin.station_id == JACA
    assert link("aragon-jaca-yesa").destination.station_id == YESA


def test_toda_distancia_declara_su_fuente_y_si_es_estimada():
    for l in LINKS.links:
        assert l.distance_km > 0
        assert l.distance_status in ("VERIFICADA", "ESTIMADA")
        assert l.distance_source.strip()
    assert all(l.distance_status == "ESTIMADA" for l in LINKS.links)  # hoy ninguna está verificada sobre el cauce


def test_distancia_poligonal_se_calcula_desde_las_coordenadas_oficiales():
    l = link("aragon-yesa-caparroso")
    recta = haversine_km(l.origin.lat, l.origin.lon, l.destination.lat, l.destination.lon)
    assert l.distance_km == pytest.approx(recta, abs=0.1)
    assert link("aragon-jaca-yesa").distance_km > haversine_km(42.57849, -0.55427, 42.61594, -1.21105)  # pasa por Martes


def test_velocidades_rio_6_a_14_y_ramblas_mas_rapidas_con_fuente():
    rio, rambla = LINKS.regimes["rio"], LINKS.regimes["rambla"]
    assert (rio.speed_kmh_min, rio.speed_kmh_max) == (6.0, 14.0)
    assert rambla.speed_kmh_min > rio.speed_kmh_min and rambla.speed_kmh_max > rio.speed_kmh_max
    assert rio.source.strip() and rambla.source.strip()
    assert rambla.status == "ESTIMADA"
    assert link("poyo-chiva-aforo").regime == "rambla"


def test_disparadores_por_defecto_configurables():
    assert LINKS.triggers.rain_mm_h == 20.0
    assert LINKS.triggers.flow_rise_pct_1h == 30.0


# ------------------------------------------------------------ disparadores

def test_sin_datos_no_hay_propagacion():
    assert activos(Datos()) == []


def test_lluvia_de_20_mm_h_en_cabecera_dispara():
    est = activos(Datos(lectura(JACA, rain_1h_mm=20.0)))
    directo = next(e for e in est if e["link_id"] == "aragon-jaca-yesa")
    assert directo["trigger"] == {
        "type": "lluvia", "value": 20.0, "threshold": 20.0, "unit": "mm/h",
        "station_id": JACA, "observed_at_utc": "2026-11-11T11:55:00Z",
    }


def test_lluvia_de_19_9_no_dispara():
    assert activos(Datos(lectura(JACA, rain_1h_mm=19.9))) == []


def test_subida_de_caudal_del_30_por_ciento_en_una_hora_dispara():
    datos = Datos(lectura(JACA, minutes_ago=65, flow_m3s=10.0), lectura(JACA, minutes_ago=5, flow_m3s=13.0))
    est = activos(datos)
    t = next(e for e in est if e["link_id"] == "aragon-jaca-yesa")["trigger"]
    assert t["type"] == "subida_caudal" and t["value"] == pytest.approx(30.0) and t["unit"] == "% en 1 h"


def test_subida_del_29_por_ciento_no_dispara():
    datos = Datos(lectura(JACA, minutes_ago=65, flow_m3s=10.0), lectura(JACA, minutes_ago=5, flow_m3s=12.9))
    assert activos(datos) == []


def test_sin_lectura_de_hace_una_hora_no_se_inventa_la_subida():
    datos = Datos(lectura(JACA, minutes_ago=200, flow_m3s=1.0), lectura(JACA, minutes_ago=5, flow_m3s=50.0))
    assert activos(datos) == []


def test_cauce_seco_que_empieza_a_correr_dispara_solo_por_encima_del_caudal_minimo():
    seco = lectura(JACA, minutes_ago=65, flow_m3s=0.0)
    assert activos(Datos(seco, lectura(JACA, minutes_ago=5, flow_m3s=0.2))) == []
    assert activos(Datos(seco, lectura(JACA, minutes_ago=5, flow_m3s=5.0))) != []


@pytest.mark.parametrize("extra", [dict(quality="SUSPECT"), dict(quality="MISSING"), dict(minutes_ago=200)])
def test_dato_no_fiable_u_obsoleto_no_dispara(extra):
    assert activos(Datos(lectura(JACA, rain_1h_mm=80.0, **extra))) == []


def test_umbrales_de_disparo_configurables():
    custom = LINKS.with_triggers(rain_mm_h=50.0, flow_rise_pct_1h=30.0)
    assert evaluate(custom, Datos(lectura(JACA, rain_1h_mm=30.0)).history, NOW) == []


# --------------------------------------------------------------------- ETA

def test_eta_es_siempre_un_rango_de_horas_y_nunca_una_hora_exacta():
    for e in activos(Datos(lectura(JACA, rain_1h_mm=40.0))):
        assert e["label"] == LABEL == "estimación orientativa"
        assert 0 < e["eta_hours_min"] < e["eta_hours_max"]
        assert not any("arriv" in k or "llegada_utc" in k or k.endswith("_at") for k in e)


def test_eta_es_distancia_entre_velocidad_de_onda():
    l = link("aragon-jaca-yesa")
    e = next(x for x in activos(Datos(lectura(JACA, rain_1h_mm=40.0))) if x["link_id"] == l.id)
    assert e["eta_hours_min"] == pytest.approx(l.distance_km / 14.0, abs=0.06)
    assert e["eta_hours_max"] == pytest.approx(l.distance_km / 6.0, abs=0.06)
    assert e["eta_hours_min"] <= l.distance_km / 14.0 and e["eta_hours_max"] >= l.distance_km / 6.0  # redondeo hacia fuera
    assert e["distance_status"] == "ESTIMADA" and e["speed_kmh"] == [6.0, 14.0]


def test_la_onda_se_propaga_aguas_abajo_acumulando_el_rango():
    est = {e["link_id"]: e for e in activos(Datos(lectura(JACA, rain_1h_mm=40.0)))}
    assert list(est) == ["aragon-jaca-yesa", "aragon-yesa-caparroso", "aragon-caparroso-ebro-zaragoza"]
    assert est["aragon-yesa-caparroso"]["eta_hours_min"] > est["aragon-jaca-yesa"]["eta_hours_min"]
    assert est["aragon-caparroso-ebro-zaragoza"]["eta_hours_max"] > est["aragon-yesa-caparroso"]["eta_hours_max"]
    assert est["aragon-yesa-caparroso"]["via"] == ["aragon-jaca-yesa"]
    assert est["aragon-jaca-yesa"]["via"] == []


def test_rambla_da_tiempos_de_minutos_u_horas():
    l = link("poyo-aforo-paiporta")
    datos = Datos(lectura(l.origin.station_id, minutes_ago=65, flow_m3s=20.0), lectura(l.origin.station_id, flow_m3s=90.0))
    e = next(x for x in activos(datos) if x["link_id"] == l.id)
    assert e["regime"] == "rambla" and e["speed_status"] == "ESTIMADA"
    assert e["eta_hours_max"] < 3


# ---------------------------------------- episodio real: DANA, 29/10/2024

POYO = "saih_jucar:rambla_poyo"
MADRID = ZoneInfo("Europe/Madrid")


def serie_dana() -> list[Reading]:
    path = ROOT / "tests" / "fixtures" / "historical" / "cincominutales-rambla-poyo-29102024.csv"
    out = []
    with open(path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ts = datetime.strptime(row["Fecha"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=MADRID).astimezone(timezone.utc)
            fallo = row["Estado"] == "FALLO" or row["Caudal"] == ""
            out.append(Reading(
                station_id=POYO, source="saih_jucar", name="Rambla del Poyo", lat=39.47537, lon=-0.5818, river="Poyo",
                flow_m3s=None if fallo else float(row["Caudal"].replace(",", ".")), level_m=None, rain_1h_mm=None,
                rain_24h_mm=None, reservoir_pct=None, reservoir_hm3=None, thresholds=None,
                timestamp_utc=None if fallo else ts, fetched_at_utc=ts, quality="MISSING" if fallo else "OK",
            ))
    return out


def en(hora_local: str, serie):
    now = datetime.strptime("2024-10-29 " + hora_local, "%Y-%m-%d %H:%M").replace(tzinfo=MADRID).astimezone(timezone.utc)
    visibles = [r for r in serie if r.fetched_at_utc <= now]
    return evaluate(LINKS, Datos(*[r for r in visibles if r.timestamp_utc]).history, now)


def test_dana_el_fichero_real_tiene_el_pico_y_el_fallo_documentados():
    serie = serie_dana()
    pico = max((r for r in serie if r.flow_m3s is not None), key=lambda r: r.flow_m3s)
    assert pico.flow_m3s == 2282.904
    assert pico.timestamp_utc == datetime(2024, 10, 29, 17, 55, tzinfo=timezone.utc)  # 18:55 hora local
    assert sum(r.quality == "MISSING" for r in serie) > 100


def test_dana_la_madrugada_previa_con_cauce_seco_no_dispara():
    assert en("03:00", serie_dana()) == []


def test_dana_la_subida_de_la_tarde_dispara_antes_del_pico():
    serie = serie_dana()
    e = next(x for x in en("17:00", serie) if x["link_id"] == "poyo-aforo-paiporta")
    assert e["trigger"]["type"] == "subida_caudal"
    assert e["trigger"]["value"] > 30
    assert e["eta_hours_max"] < 3 and e["label"] == "estimación orientativa"
    assert en("18:55", serie) != []


def test_dana_primer_aviso_de_la_tarde_llega_con_mas_de_una_hora_de_margen_sobre_el_pico():
    serie = serie_dana()
    primera = None
    for minutos in range(12 * 60, 19 * 60, 5):
        hora = f"{minutos // 60:02d}:{minutos % 60:02d}"
        if en(hora, serie):
            primera = minutos
            break
    assert primera is not None
    assert (18 * 60 + 55) - primera >= 60, f"primer disparo a las {primera // 60}:{primera % 60:02d}"


def test_dana_tras_el_fallo_del_sensor_no_se_inventa_propagacion_con_dato_viejo():
    assert en("22:30", serie_dana()) == []
