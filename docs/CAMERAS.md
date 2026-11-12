# Cámaras de tráfico (DGT) — solo para ver

**No hay análisis de imagen de ningún tipo** (ni visión artificial, ni IA, ni APIs de pago): la imagen se enseña tal cual y se enlaza al origen.

## Feed verificado

`GET https://nap.dgt.es/datex2/v3/dgt/DevicePublication/camaras_datex2_v37.xml` (DATEX II v3, 3,7 MB, 1.975 cámaras con coordenadas, `publicationTime` 2026-11-12T08:00 +01:00). Probado con `scripts/probe_sources.py` (muestra en `tests/fixtures/dgt/`).
La imagen de cada cámara: `https://etraffic.dgt.es/camarasEtraffic/{id}.jpg` (`Cache-Control: max-age=120`, cabecera `Last-Modified`, **sin CORS**; admite `?_=n` para saltarse la caché).

## Cómo funciona

- **Hotlink:** el navegador pide la imagen directamente a la DGT. El servidor no la descarga ni la guarda.
- **Edad de la imagen:** el navegador no puede leer `Last-Modified` (no hay CORS), así que el backend hace un `HEAD` (nunca descarga la imagen) y lo cachea 2 min. Si la imagen tiene más de 20 min, no responde o no tiene fecha: **"Cámara sin señal"** y no se muestra ninguna imagen.
- **Refresco:** la UI renueva imagen y estado cada 2 min mientras el panel de la estación está abierto.
- **Lista curada (`engine/cameras.yaml`):** solo entra una cámara si una persona ha comprobado que **enfoca el cauce o el puente** (`focus_verified: true` + `verified_by`) y está a menos de 3 km de la estación. La DGT no publica hacia dónde mira cada cámara.

## Revisión visual (2026-11-12) — resultado: ninguna sirve

| Estación | Cámara más cercana | Distancia | Lo que se ve | Veredicto |
|---|---|---|---|---|
| Aforo Rambla del Poyo | 112 (A-3 km 336,6, Godelleta) | 0,7 km | autovía A-3 | **No enfoca el cauce** |
| Ebro en Zaragoza (A011) | 67 (A-2 km 322,4, enlace N-330) | 2,4 km | autovía A-2 | **No enfoca el cauce** |
| Jaca (A018) | 167293 (A-23) | 4,0 km | — | fuera de los 3 km |
| Yesa, Caparroso, Eo en Ribera de Piquín | — | > 25 km | — | ninguna cerca |

Por eso `engine/cameras.yaml` está **vacío** y el panel dice "No hay ninguna cámara verificada a menos de 3 km". Para añadir una: mira su imagen, confirma que se ve el cauce o el puente y añade la entrada (formato en el propio YAML).

## Pendiente

- Términos de uso del NAP/DGT para mostrar imágenes: **NO VERIFICADO** (la API CKAN devolvió 403). Hotlink sin descarga reduce el riesgo, pero hay que confirmarlo.
