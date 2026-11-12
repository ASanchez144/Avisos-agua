# Referencia L8 — SAI Cantábrico

Texto y captura de la **web oficial** usados para el contraste real (ley L8).

| Fichero | Qué es |
|---|---|
| `visor_tabla.json` | Texto visible, celda a celda, de la tabla "Tabla" del visor oficial (`#tabla-datos`), 136 estaciones de cauce. |
| `visor_tabla.png` | Captura de pantalla del visor en ese mismo instante. |

- **Web oficial:** https://visor.saichcantabrico.es/ (botón "Tabla").
- **Capturado:** 2026-11-11T11:50:54Z con `scripts/capture_reference.js` (navegador headless, User-Agent identificable del proyecto).
- **Fixture emparejada:** `tests/fixtures/saih_cantabrico/peticion_cincominutal_todas.json`, descargada 2 segundos después (2026-11-11T11:50:56Z), dentro del mismo ciclo cincominutal.
- **Columnas de `rows`:** 0 zona · 1 código · 2 río · 3 estación · 4 nivel (m) · 5 tendencia · 6-8 umbrales de nivel · 9-10 máximo histórico · 11 caudal (m³/s) · 12 tendencia · 13-15 umbrales de caudal · 16 actualización (`HH:MM | DD-MM-AAAA`, hora local peninsular).

Ejemplo (fila 1): estación 1424 Ribera de Piquín → nivel `0.14` m, caudal `0.75` m³/s, umbrales de nivel `2.10 / 2.60 / 3.50`, actualización `12:45 | 11-11-2026`.

**No modificar.** El hash de estos ficheros está en `tests/HARNESS.sha256`.
