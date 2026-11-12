# HidroRed España

Radar ciudadano de caudales, embalses y lluvia en España con datos públicos.

> **Información no oficial. En emergencia llama al 112 y sigue a AEMET y Protección Civil.**

## Qué hay

| Parte | Contenido |
|---|---|
| `connectors/` | Conectores con esquema común: SAI Cantábrico, ACA (Cataluña) y AEMET (lluvia horaria, avisos CAP, inventario). Cliente HTTP responsable y robots.txt. |
| `engine/` | Validación (→ `SUSPECT`), estado de estación y motor de propagación (`river_links.yaml`). |
| `backend/` | API FastAPI, SQLite, planificador cada 15 min, modo demostración. |
| `frontend/` | React + Tailwind + Lucide + Leaflet, modo oscuro, móvil primero. |
| `tests/` | Tests, fixtures reales, referencias oficiales y arnés de verificación inmutable. |
| `docs/` | `SOURCES_REPORT.md`, `LEGAL.md`, `OMITTED_SOURCES.md`, capturas. |

## Puesta en marcha con Docker (un comando)

1. Copia la configuración de ejemplo:

```bash
cp .env.example .env
```

2. Pon tu clave de AEMET en `.env` (`AEMET_API_KEY=...`). Se pide gratis en https://opendata.aemet.es/centrodedescargas/altaUsuario y llega por correo. Sin clave todo funciona salvo la lluvia y los avisos de AEMET, que salen como SIN DATOS.

3. Arranca:

```bash
docker compose up --build
```

4. Abre http://localhost:8080 (web) o http://localhost:8000/stations (API). El primer ciclo de datos tarda unos segundos.

Para ver la interfaz con datos de ejemplo (sin consultar ninguna fuente), pon `DEMO_LIVE_FALLBACK=true` en `.env`. Cada pantalla lleva la etiqueta **DATOS DE DEMOSTRACIÓN**.

## Desarrollo sin Docker

```bash
pip install -r requirements.txt
```

```bash
AEMET_API_KEY=tu_clave uvicorn backend.main:app --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

## API

`GET /stations` · `GET /stations/{id}` · `GET /stations/{id}/history?limit=100` · `GET /alerts` · `GET /propagation`

Todas las respuestas llevan `disclaimer` y `demo` (`true` solo en modo demostración).

## Reglas que el código garantiza

- **Estados:** `NORMAL`, `VIGILANCIA`, `PREALERTA`, `ALERTA`, `SIN_DATOS`, `DATO_OBSOLETO` (más de 60 min sin lectura nueva).
- Si la última ejecución de una fuente falló, sus estaciones salen `SIN_DATOS`.
- Sin umbral oficial no hay semáforo: `status: null` y "umbral no publicado".
- Un valor fuera de rango no se corrige ni se recorta: `quality: "SUSPECT"` y fuera de alertas.
- La propagación da siempre un **rango** de horas con la etiqueta "estimación orientativa"; distancias y velocidades no verificadas van marcadas `ESTIMADA`.
- Scraping responsable: User-Agent identificable, robots.txt, 1 petición por recurso cada 15 min.

## Tests

```bash
python -m pytest
```

```bash
python -m pytest tests/immutable_verification_harness.py -o addopts= -v -rP
```

```bash
AEMET_API_KEY=tu_clave HIDRORED_HARNESS_LIVE=1 python -m pytest tests/immutable_verification_harness.py -o addopts= -v -rP
```

```bash
./scripts/check_harness_hash.sh
```

```bash
cd frontend && npm test
```

```bash
cd frontend && npx playwright test --trace off
```

La prueba end-to-end arranca sola el backend en modo demostración y la web compilada; guarda capturas en `docs/screenshots/`.

## Arnés de verificación

`tests/immutable_verification_harness.py` (v2) y `tests/reference/` no se modifican; su hash está en `tests/HARNESS.sha256`. Los conectores nuevos se registran en `tests/harness_connectors.py`; el arnés falla si un conector de `/connectors` no está registrado, o si declara "no publicada" una variable que sí emite.
