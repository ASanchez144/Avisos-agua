# Referencia L8 — ACA (Agència Catalana de l'Aigua)

Datos que el **visor oficial** "Aigua en temps real" (https://aetr.aca.gencat.cat/) carga para pintar aforos y embalses, capturados con `scripts/capture_reference_aca.js` (navegador headless, User-Agent identificable del proyecto).

| Fichero | Qué es |
|---|---|
| `catalog_aforaments.json`, `catalog_embassaments.json` | Catálogo del visor: id de elemento → código de estación (`code`). |
| `timeline_aca.sensor.river_flow.json` | Series que pinta el visor: caudal de río (m³/s), nivel de río (cm) y caudal de canal. |
| `timeline_aca.sensor.capacity.json` | Series de embalse: % de volumen, volumen (hm³) y cota. |
| `visor_aetr.png` | Captura de pantalla del visor en ese instante. |
| `captura.json` | Fecha y lista de ficheros capturados. |

- **Capturado:** 2026-11-11T12:16:00Z.
- **Fixture emparejada:** `tests/fixtures/aca/live_*.json`, descargada de la API SDIM2 4 segundos después (2026-11-11T12:16:04Z).
- **Nota:** es la capa de datos del visor oficial, no texto leído de la pantalla (el visor es un mapa). Las series llevan fecha UTC por punto; solo se compara el punto cuya fecha coincide con la de la lectura.
- El nivel viene en cm; el registro lo pasa a m desplazando la coma (conversión exacta).

**No modificar.** Hash en `tests/HARNESS.sha256`.
