# Cómo se hizo Aguas Arriba (con IA y herramientas gratuitas)

> Información no oficial. En emergencia llama al 112 y sigue a AEMET y Protección Civil.

## Por qué

Con cada borrasca la pregunta es la misma: *¿cómo va el río de mi pueblo y va a subir?* Los datos existen: las confederaciones hidrográficas miden caudales, niveles, embalses y lluvia cada 5-15 minutos (los SAIH), AEMET publica lluvia y avisos y algunas confederaciones tienen cámaras en sus estaciones. Pero están repartidos en una decena de webs distintas, cada una con su formato, pensadas para técnicos y casi nunca para el móvil.

Aguas Arriba los junta en un solo mapa, en lenguaje claro y con una regla de oro: **si un dato no es fiable o es viejo, se dice; nunca se pinta en verde lo que no se sabe**.

## Cómo se hizo

Todo el código lo escribió una IA (Claude, de Anthropic) trabajando como ingeniero, con una persona marcando el rumbo, revisando y tomando las decisiones. Reglas fijas desde el primer día:

1. No inventar URLs, campos ni umbrales: todo se comprueba con una petición real antes de usarlo.
2. Si una fuente falla, la web dice "SIN DATOS". Dato de más de 60 min (120 en AEMET): "dato antiguo".
3. Solo umbrales de aviso oficiales. Si la fuente no los publica: "umbral no publicado", sin semáforo.
4. Scraping responsable: identificarse, respetar `robots.txt`, como mucho 1 petición cada 15 min por recurso.
5. Todo cambio con tests. Antes de decir "funciona", se ejecuta y se enseña la salida real.

### Fase 0 — Verificar las fuentes (antes de programar nada)
Se probaron con peticiones reales AEMET, los SAIH de 9 confederaciones, la ACA (Cataluña), Hidrosur, MITECO y la DGT. Resultado honesto: muchas webs oficiales no se dejan leer de forma automática (formatos frágiles, tokens cifrados, cortafuegos que rechazan bots, o simplemente inalcanzables desde fuera de España). Quedó un informe (`docs/SOURCES_REPORT.md`) con muestras reales guardadas.

### Fase 1 — Un conector y un "arnés" de verificación
Primer conector: el SAI del Cantábrico (el más limpio: datos cada 5 min, coordenadas y umbrales oficiales). Y un **arnés inmutable** de 8 leyes que toda lectura debe cumplir (caudales y niveles en rangos físicos, coordenadas dentro de España, umbrales ordenados, fechas no futuras…). Un valor imposible no se corrige: se marca como sospechoso y no genera alertas. La ley 8 obliga a contrastar con la web oficial: 232 medidas y 328 umbrales coincidieron exactamente.

### Fase 2 — Más fuentes y un motor de propagación
ACA y AEMET (lluvia horaria y avisos con sus polígonos). Un motor que, si llueve fuerte o el caudal sube rápido en cabecera, avisa río abajo con un **rango** de horas, nunca una hora exacta, y con la etiqueta "estimación orientativa". Se calibró con un episodio real: el hidrograma de la Rambla del Poyo en la DANA del 29/10/2024 (datos públicos). La segunda onda, la dañina, se habría detectado unas 2 h antes del pico de las 18:55. Donde no hay una distancia o una velocidad verificadas (ramblas), no se da hora: solo "subida detectada en cabecera".

### Fase 3 — La web
React, modo oscuro, pensada para el móvil. Marcadores con color, icono **y** texto (accesible). Panel por estación: nivel frente a umbrales oficiales, caudal explicado en litros por segundo y piscinas olímpicas por minuto, lluvia en litros por metro cuadrado, embalses y una gráfica de lluvia y caudal. Modo demostración claramente etiquetado.

### Fase 6 — Ponerlo en marcha gratis
- **Código:** GitHub (público).
- **Base de datos:** Neon (Postgres gratuito), con borrado automático de lecturas de más de 7 días para caber en 0,5 GB.
- **Web y API:** Vercel (plan gratuito).
- **Recogida de datos:** GitHub Actions cada 15 min; y como respaldo, la propia web pide datos nuevos si los que hay tienen más de 15 min.
- **Cámaras:** las 147 cámaras oficiales de la CH del Cantábrico en sus estaciones de aforo, que enfocan el cauce y la regla de nivel. Se muestran tal cual, enlazadas al origen, sin análisis. Si la foto es vieja: "Cámara sin señal".

**Coste: 0 €.**

## Herramientas (todas gratuitas)

| Para qué | Herramienta |
|---|---|
| Programar | Claude Code (IA), Python, FastAPI, React, Tailwind, Leaflet |
| Mapa base | OpenStreetMap |
| Base de datos | Neon (plan gratuito) |
| Web y API | Vercel Hobby |
| Recogida cada 15 min | GitHub Actions |
| Tests | pytest, Vitest, Playwright |

## Lo que todavía no está (y por qué)

- **Ebro, Júcar, Duero y Miño-Sil**: sus webs no respondieron desde el entorno de desarrollo. Hay un script (`scripts/probe_sources.py`) para probarlas desde España; con sus respuestas reales se escribirán los conectores.
- **Galicia**: MeteoGalicia y Augas de Galicia tienen una API oficial y gratuita de caudales y niveles, pero hace falta pedir una clave por email.
- **Segura**: publica sus pluviómetros y aforos en un visor ArcGIS, pero sin la hora de la medida; no se muestra un dato sin hora.
- **Cámaras de otras cuencas**: no se ha encontrado ninguna otra red pública de cámaras que enfoque ríos. Las de tráfico de la DGT miran la carretera.
- Los umbrales de disparo del motor de propagación se calibraron con un solo episodio: hay que afinarlos con más datos.

## Fuentes de datos

Confederación Hidrográfica del Cantábrico (SAI), Agència Catalana de l'Aigua, AEMET y MITECO (inventario de estaciones). Hidrograma de la DANA: repositorio público `datadista/datasets`. Mapa: © colaboradores de OpenStreetMap.
