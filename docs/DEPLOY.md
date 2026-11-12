# DEPLOY — coste 0 €

Arquitectura: **Neon** (Postgres) ← **GitHub Actions** (colector cada 15 min) · **Vercel Hobby** (web + API de solo lectura).

> ⚠️ **No probado de extremo a extremo.** Neon, Vercel y GitHub Actions no se han podido ejecutar desde el entorno de desarrollo (sin acceso a tu cuenta de Neon, sin Vercel, sin Actions). Los workflows y `vercel.json` están validados solo en sintaxis. Sigue los pasos y **comprueba cada paso** con la sección "Cómo comprobarlo".
>
> ⚠️ **Vercel Hobby es solo para uso personal no comercial.** Si el proyecto va a tener uso comercial, Hobby no vale (y deja de ser 0 €).

## 1. Neon

1. En tu proyecto Neon (`bitter-rain-15014027`, rama `production`) abre **Connect** y copia la cadena **con pooler** (el host lleva `-pooler`). Con `neon` en tu PC:

```bash
neon login
```

```bash
neon connection-string production --project-id bitter-rain-15014027 --pooled
```

   (o cópiala de la consola de Neon: *Connect → Connection pooling*).
2. Forma de la cadena: `postgresql://usuario:clave@ep-xxxx-pooler.region.aws.neon.tech/neondb?sslmode=require`. **No la pegues en ningún chat ni en ningún fichero del repo.**
3. Las tablas se crean solas: el colector aplica las migraciones (Alembic) en cada ciclo. Para crearlas ya, desde tu PC:

```bash
DATABASE_URL="<la cadena>" python -c "from backend.db import Database; Database('$DATABASE_URL')"
```

## 2. Secretos en GitHub

Repositorio → **Settings → Secrets and variables → Actions → New repository secret**:

| Secreto | Valor |
|---|---|
| `DATABASE_URL` | la cadena de Neon con pooler |
| `AEMET_API_KEY` | tu clave de AEMET OpenData (si no, la lluvia y los avisos salen SIN DATOS) |

El repositorio debe ser **público** (Actions es gratis solo así; ahora lo es). Los secretos no aparecen en los logs.

### Euskalmet (opcional: ríos del País Vasco)

Añade en GitHub Secrets **y** en Vercel (Settings → Environment Variables, Production):

| Nombre | Valor |
|---|---|
| `EUSKALMET_PRIVATE_KEY` | el contenido completo de tu clave privada `.pem` (desde `-----BEGIN` hasta `END-----`) |
| `EUSKALMET_EMAIL` | el email con el que diste de alta la clave en Euskalmet |

El colector firma un JWT nuevo en cada ciclo. Sin estas dos variables Euskalmet no se consulta (no aparece como caído).

### Hidrosur (opcional, ver docs/LEGAL.md)

`HIDROSUR_ENABLED=1` en Vercel (Environment Variables) y como **variable** (no secreto) de GitHub Actions. Sin ella no se consulta.

## 3. Primera ejecución del colector

Pestaña **Actions → collector → Run workflow**. Debe terminar en verde en ~1 min. En el log aparece un JSON con una entrada por fuente (`saih_cantabrico`, `aca`, `aemet`, `aemet:avisos`) con `"ok": true` y el nº de lecturas. Un conector que falla sale con `"ok": false` y su error, **sin tumbar el ciclo** (el job solo falla si no hay base de datos).

Después se ejecuta solo cada 15 min (GitHub puede retrasarlo unos minutos). El workflow **keepalive** lo vuelve a habilitar cada semana (GitHub desactiva los programados tras 60 días sin actividad).

## 4. Vercel

1. **Add New → Project → Import** `ASanchez144/Avisos-agua`. **Root Directory: la raíz** (no `frontend`).
2. Framework Preset: *Other*. No toques los comandos: `vercel.json` ya define el build (`cd frontend && npm ci && npm run build`), la salida (`frontend/dist`) y la función Python `api/index.py`.
3. **Environment Variables** (Production): `DATABASE_URL` = la misma cadena con pooler. (Para ver solo la demo: `DEMO_LIVE_FALLBACK=true` y sin `DATABASE_URL`.)
4. **Deploy.**

La API se sirve en `https://<tu-proyecto>.vercel.app/api/...` y la web en la raíz. Las respuestas se cachean 60 s en el borde de Vercel.

## 5. Cómo comprobarlo

```bash
curl -s https://<tu-proyecto>.vercel.app/api/stations | head -c 300
```

Debe devolver JSON con `"demo": false` y estaciones. Luego abre la web: mapa con marcadores y **sin** la etiqueta violeta "DATOS DE DEMOSTRACIÓN".

En Neon, *SQL Editor*:

```sql
SELECT source, ok, n_readings, finished_at_utc, error FROM source_runs ORDER BY id DESC LIMIT 8;
```

```sql
SELECT count(*) FROM readings;
```

Si `source_runs` no avanza cada ~15 min, mira la pestaña Actions.

## 6. Tamaño (plan gratuito de Neon: 0,5 GB)

El colector borra lecturas de más de **7 días** en cada ciclo. Estimación (medida en Postgres 16, 118 B de carga por fila y ~350 B con índices): ~46.500 lecturas nuevas al día (Cantábrico 17.280 + ACA 8.832 + AEMET 20.424) × 7 días ≈ 326.000 filas ≈ **115–150 MB**, un 25–30 % del límite. Si se añaden fuentes, recalcula. Neon también guarda historial de la rama (restauración): vigílalo en *Usage* en la consola.

## 7. Variables

| Variable | Dónde | Para qué |
|---|---|---|
| `DATABASE_URL` | GitHub Secrets + Vercel | Postgres de Neon (con pooler). Vacío = SQLite local |
| `AEMET_API_KEY` | GitHub Secrets (y `.env` local) | AEMET OpenData |
| `DEMO_LIVE_FALLBACK` | Vercel / `.env` | `true` = solo datos de ejemplo, etiquetados |
| `HIDRORED_TEST_PG_URL` | solo tests | Postgres para los tests de la capa de datos |

## 8. Docker (opcional, local)

`docker compose up --build` sigue funcionando como opción local (SQLite o `DATABASE_URL`). **Nunca se ha ejecutado**: el entorno de desarrollo no tiene Docker.
