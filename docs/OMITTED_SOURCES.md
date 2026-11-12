# Fuentes omitidas en la Fase 2 y por qué

Regla aplicada: un conector solo para fuentes con veredicto **USABLE** en `SOURCES_REPORT.md`. No se inventan sustitutos.

## Con conector (3)

| Fuente | Conector | Aporta |
|---|---|---|
| SAI Cantábrico | `connectors/saih_cantabrico.py` | caudal, nivel, lluvia 1 h y 24 h, embalses, umbrales oficiales |
| ACA Cataluña (API SDIM2) | `connectors/aca.py` | caudal, nivel, embalses. Sin umbrales |
| AEMET OpenData | `connectors/aemet.py` | lluvia de la última hora por estación, avisos CAP con polígonos, inventario |

## Omitidas

| Fuente | Veredicto Fase 0 | Motivo de la omisión |
|---|---|---|
| ACA — dataset `gn9e-3qhr` | USABLE (limitado) | Redundante y peor: son los mismos embalses que ya da SDIM2 en tiempo real, pero con un dato diario y **sin coordenadas** (todas las lecturas incumplirían L4). |
| ACA — lluvia (pluviómetros SDIM2) | — | Publica intensidad instantánea en mm/h, no acumulado de 1 h. Mapearla a `rain_1h_mm` sería inventar. |
| ACA — umbrales | — | El visor oficial `aetr.aca.gencat.cat` carga umbrales desde `api.aetr.aca.gencat.cat/Threshold/...`, pero tras una autorización "public" propia del visor. No verificado ni usado: hoy ACA sale como "umbral no publicado". |
| DGT — cámaras (DATEX II) | USABLE | No es una fuente de lecturas hidrológicas: no encaja en el esquema común ni en el arnés (exige valores medidos). Además la licencia del NAP está NO VERIFICADA. Queda como módulo aparte pendiente. |
| AEMET — radar nacional | — | La ruta devolvió `estado 404` en todos los intentos. |
| AEMET — `rain_24h_mm` | — | La API trae ~12 h por estación: no se puede sumar 24 h sin inventar. |
| Hidrosur | USABLE CON SCRAPING FRÁGIL | No es USABLE: HTML frágil, valores medios horarios y sin permiso expreso de reutilización. |
| SAIH Guadalquivir | USABLE CON SCRAPING FRÁGIL | No es USABLE: HTML por zonas, sin coordenadas ni fecha por lectura. |
| SAIH Tajo | USABLE CON SCRAPING FRÁGIL | No es USABLE: tokens cifrados, sin fecha por lectura y `robots.txt` dudoso. Requiere hablar con la CHT. |
| SAIH Segura | USABLE CON SCRAPING FRÁGIL | No es USABLE: sin coordenadas, sin fecha por lectura, sin umbrales. |
| MITECO FeatureServer SAIH | Inventario | No da lecturas. Sí se usó para coordenadas y cotas oficiales de `engine/river_links.yaml`. |
| SAIH Júcar | NO USABLE | El WAF rechaza el User-Agent identificable. No se rodea. |
| SAIH Ebro | NO VERIFICABLE | Inalcanzable desde el entorno de verificación (corte de conexión a los 10 s). |
| SAIH Duero | NO VERIFICABLE | 502 del gateway. |
| SAIH Miño-Sil | NO VERIFICABLE | Cadena de certificados TLS no validable; no se desactiva la verificación. |

## Consecuencias que conviene saber

- **Los enlaces de propagación del Aragón–Ebro y del Barranco del Poyo no tienen caudal en vivo** (Ebro y Júcar sin conector). El de Jaca puede dispararse por lluvia en la estación AEMET de Jaca; los del Poyo, hoy, no pueden dispararse. Los enlaces del Eo (Cantábrico) sí funcionan en vivo.
- **Las estaciones AEMET salen casi siempre como "dato antiguo":** AEMET publica el acumulado horario con más de una hora de retraso y la regla del proyecto marca obsoleto a partir de 60 min. El motor de propagación sí las usa (admite hasta 120 min).
