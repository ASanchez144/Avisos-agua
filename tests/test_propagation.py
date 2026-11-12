"""Motor de propagación: series sintéticas + episodio real (DANA 29/10/2024, Rambla del Poyo)."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from connectors.base import Reading
from engine.geo import haversine_km
from engine.propagation import LABEL, describe_links, evaluate, load_links

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


def test_toda_distancia_declara_su_fuente_y_su_estado():
    for l in LINKS.links:
        assert l.distance_status in ("VERIFICADA", "ESTIMADA", "SIN_DISTANCIA")
        assert l.distance_source.strip()
        assert (l.distance_km is None) == (l.distance_status == "SIN_DISTANCIA")
    assert not any(l.distance_status == "VERIFICADA" for l in LINKS.links)


def test_poligonal_es_cota_inferior_y_se_marca_como_tal():
    l = link("aragon-yesa-caparroso")
    recta = haversine_km(l.origin.lat, l.origin.lon, l.destination.lat, l.destination.lon)
    assert l.distance_km == pytest.approx(recta, abs=0.1)
    assert l.lower_bound is True and "ETA puede ser menor que el real" in l.distance_source
    assert link("aragon-jaca-yesa").distance_km > haversine_km(42.57849, -0.55427, 42.61594, -1.21105)


def test_poyo_sin_distancia_ni_velocidad_verificada_no_tiene_eta():
    for id_ in ("poyo-chiva-aforo", "poyo-aforo-paiporta"):
        l = link(id_)
        assert l.distance_km is None and l.regime == "rambla"
    rambla = LINKS.regimes["rambla"]
    assert rambla.speed_kmh_min is None and rambla.speed_kmh_max is None and rambla.status == "SIN_REFERENCIA"
    assert all(not d["eta_available"] and d["eta_hours_min"] is None for d in describe_links(LINKS) if d["regime"] == "rambla")


def test_velocidad_de_rio_6_a_14_con_fuente():
    rio = LINKS.regimes["rio"]
    assert (rio.speed_kmh_min, rio.speed_kmh_max) == (6.0, 14.0) and rio.source.strip()


def test_dos_niveles_y_parametros_configurables():
    t = LINKS.triggers
    assert set(t.levels) == {"VIGILANCIA", "ALERTA"} and t.consecutive_readings == 2
    assert t.levels["VIGILANCIA"].rain_mm_h == 20.0 and t.levels["VIGILANCIA"].flow_rise_pct_1h == 30.0
    assert t.levels["ALERTA"].min_flow_m3s > t.levels["VIGILANCIA"].min_flow_m3s >= 5.0


# ------------------------------------------------------------ disparadores

def lluvia(station, valores, now=NOW, paso=60):
    """Serie de lluvia: valores de más antiguo a más reciente, cada `paso` min, la última hace 5 min."""
    n = len(valores)
    return [lectura(station, minutes_ago=5 + paso * (n - 1 - i), now=now, rain_1h_mm=v) for i, v in enumerate(valores)]


def caudal(station, valores, now=NOW, paso=15):
    """Serie de caudal: la última hace 5 min; `paso` min entre lecturas."""
    n = len(valores)
    return [lectura(station, minutes_ago=5 + paso * (n - 1 - i), now=now, flow_m3s=v) for i, v in enumerate(valores)]


def test_sin_datos_no_hay_propagacion():
    assert activos(Datos()) == []


def test_lluvia_con_2_lecturas_seguidas_de_20_mm_h_da_vigilancia():
    est = activos(Datos(*lluvia(JACA, [20.0, 25.0])))
    t = next(e for e in est if e["link_id"] == "aragon-jaca-yesa")["trigger"]
    assert t["level"] == "VIGILANCIA" and t["type"] == "lluvia" and t["consecutive_readings"] == 2


def test_lluvia_con_2_lecturas_de_40_mm_h_da_alerta():
    est = activos(Datos(*lluvia(JACA, [41.0, 45.0])))
    assert next(e for e in est if e["link_id"] == "aragon-jaca-yesa")["level"] == "ALERTA"


def test_una_sola_lectura_de_lluvia_no_dispara():
    assert activos(Datos(*lluvia(JACA, [80.0]))) == []
    assert activos(Datos(*lluvia(JACA, [5.0, 80.0]))) == []   # la anterior no cumple


def test_lluvia_de_19_9_no_dispara():
    assert activos(Datos(*lluvia(JACA, [19.9, 19.9]))) == []


def test_las_lecturas_consecutivas_no_pueden_estar_muy_separadas():
    serie = [lectura(JACA, minutes_ago=200, rain_1h_mm=30.0), lectura(JACA, minutes_ago=5, rain_1h_mm=30.0)]
    assert activos(Datos(*serie)) == []


def test_subida_de_caudal_del_50_por_ciento_en_1_h_con_2_lecturas_da_vigilancia():
    # cada lectura se compara con la de hace una hora: 10->15 y 12->18 (+50 %)
    datos = Datos(lectura(JACA, minutes_ago=80, flow_m3s=10.0), lectura(JACA, minutes_ago=65, flow_m3s=12.0),
                  lectura(JACA, minutes_ago=20, flow_m3s=15.0), lectura(JACA, minutes_ago=5, flow_m3s=18.0))
    t = next(e for e in activos(datos) if e["link_id"] == "aragon-jaca-yesa")["trigger"]
    assert t["type"] == "subida_caudal" and t["level"] == "VIGILANCIA" and t["value"] == pytest.approx(50.0)


def test_subida_del_29_por_ciento_no_dispara():
    datos = Datos(lectura(JACA, minutes_ago=80, flow_m3s=10.0), lectura(JACA, minutes_ago=65, flow_m3s=10.0),
                  lectura(JACA, minutes_ago=20, flow_m3s=12.9), lectura(JACA, minutes_ago=5, flow_m3s=12.9))
    assert activos(datos) == []


def test_una_sola_lectura_con_subida_no_dispara():
    datos = Datos(lectura(JACA, minutes_ago=65, flow_m3s=10.0), lectura(JACA, minutes_ago=5, flow_m3s=40.0))
    assert activos(datos) == []


def test_ruido_en_cauce_seco_no_dispara():
    """Caso real que disparaba el sistema anterior: 0 -> 1,1 m3/s desde cauce seco."""
    datos = Datos(lectura(JACA, minutes_ago=80, flow_m3s=0.0), lectura(JACA, minutes_ago=65, flow_m3s=0.0),
                  lectura(JACA, minutes_ago=20, flow_m3s=1.1), lectura(JACA, minutes_ago=5, flow_m3s=1.3))
    assert activos(datos) == []


def test_cauce_seco_que_empieza_a_correr_dispara_solo_por_encima_del_minimo():
    seco = lambda q: Datos(lectura(JACA, minutes_ago=80, flow_m3s=0.0), lectura(JACA, minutes_ago=65, flow_m3s=0.0),
                           lectura(JACA, minutes_ago=20, flow_m3s=q), lectura(JACA, minutes_ago=5, flow_m3s=q))
    assert activos(seco(4.9)) == []
    assert activos(seco(5.0)) != []
    assert next(e for e in activos(seco(60.0)) if e["link_id"] == "aragon-jaca-yesa")["level"] == "ALERTA"


def test_sin_lectura_de_hace_una_hora_no_se_inventa_la_subida():
    datos = Datos(lectura(JACA, minutes_ago=200, flow_m3s=1.0), lectura(JACA, minutes_ago=20, flow_m3s=50.0),
                  lectura(JACA, minutes_ago=5, flow_m3s=60.0))
    assert activos(datos) == []


@pytest.mark.parametrize("extra", [dict(quality="SUSPECT"), dict(quality="MISSING"), dict(minutes_ago=200)])
def test_dato_no_fiable_u_obsoleto_no_dispara(extra):
    assert activos(Datos(lectura(JACA, rain_1h_mm=80.0, **extra), lectura(JACA, rain_1h_mm=80.0, **extra))) == []


def test_umbrales_de_disparo_configurables():
    custom = LINKS.with_level("VIGILANCIA", rain_mm_h=50.0).with_level("ALERTA", rain_mm_h=90.0)
    assert evaluate(custom, Datos(*lluvia(JACA, [30.0, 30.0])).history, NOW) == []
    una = LINKS.with_triggers(consecutive_readings=1)
    assert evaluate(una, Datos(*lluvia(JACA, [30.0])).history, NOW) != []


# --------------------------------------------------------------------- ETA

def lluvia_fuerte():
    return Datos(*lluvia(JACA, [40.0, 45.0]))


def test_eta_es_siempre_un_rango_de_horas_y_nunca_una_hora_exacta():
    for e in activos(lluvia_fuerte()):
        assert e["label"] == LABEL == "estimación orientativa"
        assert 0 < e["eta_hours_min"] < e["eta_hours_max"]
        assert not any("arriv" in k or "llegada_utc" in k or k.endswith("_at") for k in e)


def test_eta_es_distancia_entre_velocidad_de_onda_y_marca_cota_inferior():
    l = link("aragon-jaca-yesa")
    e = next(x for x in activos(lluvia_fuerte()) if x["link_id"] == l.id)
    assert e["eta_hours_min"] <= l.distance_km / 14.0 and e["eta_hours_max"] >= l.distance_km / 6.0
    assert e["eta_hours_max"] - l.distance_km / 6.0 < 0.011
    assert e["distance_status"] == "ESTIMADA" and e["distance_is_lower_bound"] is True and e["speed_kmh"] == [6.0, 14.0]


def test_la_onda_se_propaga_aguas_abajo_acumulando_el_rango():
    est = {e["link_id"]: e for e in activos(lluvia_fuerte())}
    assert list(est) == ["aragon-jaca-yesa", "aragon-yesa-caparroso", "aragon-caparroso-ebro-zaragoza"]
    assert est["aragon-yesa-caparroso"]["eta_hours_min"] > est["aragon-jaca-yesa"]["eta_hours_min"]
    assert est["aragon-caparroso-ebro-zaragoza"]["eta_hours_max"] > est["aragon-yesa-caparroso"]["eta_hours_max"]
    assert est["aragon-yesa-caparroso"]["via"] == ["aragon-jaca-yesa"]


def test_rambla_sin_referencia_avisa_sin_rango_horario():
    l = link("poyo-aforo-paiporta")
    p = l.origin.station_id
    datos = Datos(lectura(p, minutes_ago=80, flow_m3s=0.0), lectura(p, minutes_ago=65, flow_m3s=0.0),
                  lectura(p, minutes_ago=20, flow_m3s=300.0), lectura(p, minutes_ago=5, flow_m3s=400.0))
    e = next(x for x in activos(datos) if x["link_id"] == l.id)
    assert e["eta_available"] is False and e["eta_hours_min"] is None and e["eta_hours_max"] is None
    assert e["distance_status"] == "SIN_DISTANCIA" and e["speed_status"] == "SIN_REFERENCIA"
    assert "subida detectada en cabecera" in e["message"] and e["level"] == "ALERTA"


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


def test_dana_detecta_las_dos_ondas_pero_no_da_eta_en_ramblas():
    serie = serie_dana()
    primera = next(x for x in en("12:00", serie) if x["link_id"] == "poyo-aforo-paiporta")
    assert primera["trigger"]["type"] == "subida_caudal" and primera["eta_available"] is False
    segunda = next(x for x in en("17:30", serie) if x["link_id"] == "poyo-aforo-paiporta")
    assert segunda["level"] == "ALERTA" and segunda["label"] == "estimación orientativa"


def test_dana_la_segunda_onda_se_avisa_mas_de_una_hora_antes_del_pico():
    serie = serie_dana()
    primera = None
    for minutos in range(14 * 60, 19 * 60, 5):
        if en(f"{minutos // 60:02d}:{minutos % 60:02d}", serie):
            primera = minutos
            break
    assert primera is not None and (18 * 60 + 55) - primera >= 60


def test_dana_el_valle_entre_ondas_apaga_el_aviso():
    assert en("16:00", serie_dana()) == []


def test_dana_tras_el_fallo_del_sensor_no_se_inventa_propagacion_con_dato_viejo():
    assert en("22:30", serie_dana()) == []
