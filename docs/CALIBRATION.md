# CALIBRATION — disparadores de propagación

Serie real: hidrograma cincominutal del aforo de la **Rambla del Poyo, DANA del 29/10/2024** (`tests/fixtures/historical/`, origen `datadista/datasets`, SAIH-CHJ). Reproducir: `python scripts/calibrate.py`.

## Qué se probó

- El motor real (`engine/propagation.py`) alimentado con la serie como si un colector la leyera cada **5 min** o cada **15 min** (cadencia real del planificador).
- Rejilla de `min_flow_m3s` y subida %/h para cada nivel.
- **Acierto** = el disparo va seguido, en las 3 h siguientes, de un caudal ≥ 100 m³/s. **Falsa alarma** = disparo sin eso. *Es un criterio del proyecto, no oficial.*

## Lo que muestra la serie

| Hora local (29/10) | Caudal |
|---|---|
| 11:00 | 0,3 m³/s (el cauce estaba seco hasta entonces) |
| 12:00 | **248,6** (primera onda) |
| 16:00 | 28,7 (valle entre ondas) |
| 17:00 | 71,7 |
| 18:00 | **809,6** |
| 18:55 | **2.282,9** (máximo; a partir de las 19:00 el sensor falla) |

## Valores elegidos (`engine/river_links.yaml`)

| Nivel | Condición (2 lecturas consecutivas) | min caudal |
|---|---|---|
| VIGILANCIA | lluvia ≥ 20 mm/h **o** subida ≥ 30 % en 1 h | 5 m³/s |
| ALERTA | lluvia ≥ 40 mm/h **o** subida ≥ 100 % en 1 h | 50 m³/s |

Cauce que estaba seco y empieza a correr: la "subida" no es expresable en %, así que cuenta solo si supera el caudal mínimo del nivel.

## Resultados reales con esos valores

| Cadencia | Nivel | Disparo 1.ª onda | Disparo 2.ª onda (la dañina) | Antelación al pico (18:55) | Antelación a los 809 m³/s (18:00) |
|---|---|---|---|---|---|
| 5 min | VIGILANCIA | 11:25 | 16:50 | 2,1 h | 1,2 h |
| 5 min | ALERTA | 11:30 | 16:55 | 2,0 h | 1,1 h |
| 15 min | VIGILANCIA | 11:40 | 17:10 | 1,8 h | 0,8 h |
| 15 min | ALERTA | 11:40 | 17:10 | 1,75 h | 0,8 h |

- **Aciertos:** 2 de 2 ondas detectadas, con cualquier combinación probada salvo ALERTA con mínimo 500 m³/s (que solo detecta la segunda y 1 h antes del pico).
- **Falsas alarmas en esta serie: 0 con todas las combinaciones.** Ruido de cauce seco (0 → 1,1 → 1,3 m³/s) con los valores elegidos: **no dispara** (test `test_ruido_en_cauce_seco_no_dispara`). Con el disparador anterior (1 lectura, mínimo 1 m³/s) sí disparaba con 1,1 m³/s.
- Pasar de 5 a 15 min de cadencia cuesta ~15-20 min de antelación.

## Límites (léelos antes de fiarte)

1. **Un solo episodio.** No hay datos de cauce seco con ruido ni de crecidas moderadas: **no se puede estimar una tasa real de falsas alarmas**. Solo se descartan valores absurdos.
2. **VIGILANCIA y ALERTA no se separan en esta serie**: el cauce pasa de 0 a 249 m³/s en una hora, así que ambos saltan casi a la vez. La diferencia solo se verá en crecidas graduales.
3. Los **mínimos de caudal (5 y 50 m³/s) son juicio del proyecto**, no umbrales oficiales: en un río grande (Ebro) 5 m³/s es caudal de estiaje y el nivel VIGILANCIA saltaría con cualquier subida. Hay que **calibrarlos por enlace** con series de cada río cuando haya datos.
4. **Lluvia:** los umbrales 20/40 mm/h son los de la especificación, **sin calibrar** (no hay serie de lluvia del episodio). Con AEMET (dato horario, no solapado) "2 lecturas consecutivas" significa 2 horas seguidas, así que el disparo por lluvia llegará tarde; Cantábrico, con lluvia acumulada en 1 h cada 5 min, no tiene ese problema.
5. El sensor dejó de medir a las 19:00 (`FALLO`): el motor no inventa propagación con dato viejo (test incluido).
6. Los enlaces del Poyo **no dan ETA** (sin distancia ni velocidad verificadas): el disparo se muestra como "subida detectada en cabecera".
