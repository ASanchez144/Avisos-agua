# Referencia oficial Euskalmet (ley 8)

Ficheros que la web oficial https://www.euskalmet.euskadi.eus carga para dibujar la gráfica de cada estación:

    GET https://www.euskalmet.euskadi.eus/vamet/stations/readings/<estación>/2026/11/12/webmet00-readingsData.json

Capturados el 2026-11-12 (`captured_at_utc.txt`), justo después de la fixture `tests/fixtures/euskalmet/readings_hourly.json`
(API https://api.euskadi.eus/euskalmet). Claves "HH:MM" = hora LOCAL (Europe/Madrid) del inicio del tramo de 10 min.
La web va un tramo por detrás de la API; los tramos comunes coinciden exactamente (tests/test_euskalmet.py).

Estaciones: C084 Behobia, C0AB Nanclares, C081 Martutene, C0B0 La Merced. Sin claves ni datos personales.
