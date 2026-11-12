# Referencia oficial Hidrosur (ley 8)

Gráficas oficiales de estación de la Red Hidrosur, tal como las sirve su web:

    GET https://www.redhidrosurmedioambiente.es/saih/mapa/tiempo/real/grafica/<código>   (009R02, 011R02, 013R02, 127R02)

Capturadas el 2026-11-12 (`captured_at_utc.txt`; 009R02 unos minutos antes, durante la exploración). Cada una trae
`labels` (hora local "dd/mm/aa HH:MM"), `serie1` (nivel, unidad "m.") y las líneas "Nivel 1/2/3" (umbrales) en el mismo eje.
Distinta página que la que lee el conector (/saih/resumen/rios + capa Aforos.json). Sin claves ni datos personales.
