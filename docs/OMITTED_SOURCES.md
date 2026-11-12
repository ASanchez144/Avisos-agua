# Fuentes omitidas y por qué

Regla: un conector solo para fuentes con veredicto **USABLE**. No se inventan sustitutos.
Dos motivos distintos, que no se deben confundir:

- **NO_USABLE** — se ha podido comprobar y la fuente no sirve (o no se nos permite usarla).
- **BLOQUEADO_POR_ENTORNO** — la fuente **no se ha podido probar** porque es inalcanzable desde el contenedor de desarrollo (timeout, TLS, filtrado por IP). **No está descartada**: puede funcionar desde una IP española. Se prueban con `scripts/probe_sources.py` (ver README).

## Con conector (3)

| Fuente | Conector | Aporta |
|---|---|---|
| SAI Cantábrico | `connectors/saih_cantabrico.py` | caudal, nivel, lluvia 1 h y 24 h, embalses, umbrales oficiales |
| ACA Cataluña (API SDIM2) | `connectors/aca.py` | caudal, nivel, embalses. Sin umbrales. ⚠️ RIESGO LEGAL (ver LEGAL.md) |
| AEMET OpenData | `connectors/aemet.py` | lluvia de la última hora, avisos CAP con polígonos, inventario |

## NO_USABLE

| Fuente | Motivo comprobado |
|---|---|
| SAIH Júcar (`saih.chj.es`) | El WAF respondió "Request Rejected" al User-Agent identificable: **acceso rechazado explícitamente**. No se rodea. Falta confirmar si con IP española responde igual (está en el script de pruebas); si sigue rechazando, hay que pedir permiso a la CHJ. |
| ACA — dataset `gn9e-3qhr` | Redundante y peor que SDIM2: dato diario, sin coordenadas (incumpliría L4). |
| ACA — pluviómetros SDIM2 | Solo intensidad instantánea (mm/h), no acumulado de 1 h: mapearla sería inventar. |
| AEMET — `rain_24h_mm` | La API trae ~12 h por estación: no se puede sumar 24 h sin inventar. |
| AEMET — radar nacional | La ruta devolvió `estado 404` en todos los intentos. |
| Hidrosur | HTML frágil, valores medios horarios y sin permiso expreso de reutilización. |
| SAIH Guadalquivir | HTML por zonas sin coordenadas ni fecha por lectura (reutilizable citando origen: sería la mejor de este grupo). |
| SAIH Tajo | Tokens cifrados encadenados, sin fecha por lectura y `robots.txt` que excluye `/?w=`. Requiere hablar con la CHT. |
| SAIH Segura | Sin coordenadas, sin fecha por lectura, sin umbrales. |
| MITECO FeatureServer SAIH | No da lecturas. Sí se usa como inventario (coordenadas y cotas de `river_links.yaml`). |
| DGT cámaras (DATEX II) | No es fuente de lecturas hidrológicas; se integra aparte (Bloque 5: solo ver la imagen). Licencia del NAP sin verificar. |

## BLOQUEADO_POR_ENTORNO (no probadas, no descartadas)

| Fuente | Qué pasó desde el contenedor | Siguiente paso |
|---|---|---|
| SAIH Ebro (`saihebro.com`) | Corte de la conexión a los 10 s en 8 de 8 intentos (TLS 1.2 y 1.3) | `probe_sources.py` desde España |
| SAIH Duero (`saihduero.es`) | 502 del gateway al CONNECT | idem |
| SAIH Miño-Sil (`saih.chminosil.es`) | Cadena de certificados no verificable (no se desactiva TLS) | idem |
| MITECO WMS aforos (`wms.mapama.gob.es`) | Cadena de certificados no verificable | idem |
| Overpass (OpenStreetMap) y Wikipedia API | Inalcanzable / 429 | `scripts/measure_channel.py` desde tu PC |

## Consecuencias

- Los enlaces de propagación del **Aragón–Ebro** y del **Barranco del Poyo** no tienen caudal en vivo (Ebro y Júcar sin conector): hoy solo Jaca puede dispararse, por lluvia AEMET; los del Poyo no.
- Las estaciones AEMET salen "dato antiguo" pasados **120 min** (límite configurable en `engine/sources.yaml`; el SAIH, 60).
