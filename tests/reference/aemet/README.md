# Referencia L8 — AEMET

Datos que la **web oficial** www.aemet.es sirve para su página "Hoy y últimos días" (https://www.aemet.es/es/eltiempo/observacion/ultimosdatos).

| Fichero | Qué es |
|---|---|
| `web_tablas_graficas_horario_esp.xml` | Respuesta de `https://www.aemet.es/es/api-eltiempo/udat/tablas-graficas/horario/6/esp/20261111T12000`: por estación (`id_c`) y periodo horario (UTC), la `precipitacion` que muestra la web. |

- **Elaborado por AEMET:** 2026-11-11T12:04:17Z (campo `elaborado` del fichero).
- **Fixture emparejada:** `tests/fixtures/aemet/observacion_convencional_todas_datos.json.gz`, descargada de AEMET OpenData a las 12:03:30Z (mismo ciclo horario).
- **Nota:** es la capa de datos de la web oficial, no una captura visual. La URL se obtuvo observando las peticiones de la propia página.
- Se compara `precipitacion` con `rain_1h_mm` solo cuando el periodo UTC coincide con el `timestamp_utc` de la lectura.

**No modificar.** Hash en `tests/HARNESS.sha256`.
