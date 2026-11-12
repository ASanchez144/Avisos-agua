# LEGAL — términos de uso de cada fuente

Estado a 2026-11-11. Solo se cita lo que se ha leído en la propia fuente; lo demás va marcado **NO VERIFICADO** y debe confirmarse antes de publicar datos de esa fuente.

Aviso permanente del proyecto (obligatorio en la UI y presente en todas las respuestas de la API):

> Información no oficial. En emergencia llama al 112 y sigue a AEMET y Protección Civil.

## Fuentes en uso

### SAI Cantábrico — Confederación Hidrográfica del Cantábrico, O.A. (conector `saih_cantabrico`)

- **Recurso:** `POST https://visor.saichcantabrico.es/wp-admin/admin-ajax.php` (`action=peticion_cincominutal&tipo=todas`).
- **robots.txt** (leído 2026-11-11): `Disallow: /wp-admin/` · `Allow: /wp-admin/admin-ajax.php`. El recurso está permitido expresamente. El cliente lo vuelve a comprobar cada 24 h y deja de pedir si cambia.
- **Aviso legal** (`https://visor.saichcantabrico.es/aviso-legal/`, cita literal):
  > "La información contenida en este sitio web puede ser utilizada en parte o en su integridad, sin necesidad de autorización expresa, siempre que se cite la fuente de los documentos objeto de la reutilización, con excepción de los contenidos sobre los que existan derechos de propiedad intelectual o industrial por parte de terceros."
- **Obligaciones que asumimos:**
  1. Citar la fuente: "Fuente: Confederación Hidrográfica del Cantábrico, O.A. (visor SAI)".
  2. No sugerir que la CHC participa, patrocina o apoya este proyecto.
  3. No hacer *framing* del visor ni cobrar por dar acceso a la información.
  4. La reutilización es bajo nuestra cuenta y riesgo; la CHC no responde del uso.
- **Carga sobre el servidor:** 1 petición cada 15 minutos (el dato cambia cada 5), User-Agent `HidroRed/0.1 (radar ciudadano hidrologico no oficial; scraping responsable)`.
- **Pendiente:** el endpoint es interno del visor, no una API pública documentada. Recomendado escribir a `atencion.ciudadana@chcantabrico.es` informando del uso (el propio aviso legal da esa dirección para dudas).

### ACA — Agència Catalana de l'Aigua (conector `aca`) — ⚠️ RIESGO LEGAL (parcial)

- **Recursos:** `GET https://aplicacions.aca.gencat.cat/sdim2/apirest/catalog?componentType=...` y `.../data/...` (4 peticiones cada 15 min). `robots.txt` → 404 (sin restricciones declaradas).
- **Lo verificado (2026-11-12):** el conjunto de datos abiertos equivalente (`gn9e-3qhr`, embalses) declara `license: SEE_TERMS_OF_USE` y atribución "Agència Catalana de l'Aigua (ACA)", con enlace a las licencias: https://web.gencat.cat/ca/generalitat/dades-indicadors/dades-obertes/llicencies — **Llicència oberta d'ús d'informació - Catalunya**. Permite reutilizar, distribuir, comunicar públicamente y transformar, con estas condiciones (cita literal): "No es pot alterar el contingut de la informació. No es pot desnaturalitzar el sentit de la informació. Cal citar la font de la informació de la manera següent: Generalitat de Catalunya. Departament de [nom departament]. [organisme autònom, empresa pública]... S'ha d'informar de la darrera data d'actualització de la informació." La propia licencia añade que una licencia específica de un conjunto de datos prevalece.
- **Lo NO verificado:** esa licencia está atada al dataset de datos abiertos. **No he encontrado ninguna página de condiciones para la API SDIM2** que usa el conector ni para el visor `aetr.aca.gencat.cat`. Es probable que apliquen las mismas condiciones, pero **no está escrito**: por eso **RIESGO LEGAL** hasta que la ACA lo confirme.
- **Cómo cumplimos lo que sí sabemos:** se cita "Generalitat de Catalunya. Departament de Territori, Habitatge i Transició Ecològica. Agència Catalana de l'Aigua"; se muestra la hora de la última lectura en cada dato; no se altera el contenido. El único cambio es de **unidad** (cm → m en el nivel), que no cambia el sentido de la información: confirmar que la ACA lo ve igual.
- **Acción recomendada:** pedir por escrito a la ACA que confirme que la API SDIM2 se rige por esa licencia, antes de publicar.

### AEMET OpenData (conector `aemet`) — verificado

- **Recursos:** observación convencional, avisos CAP e inventario, con API key personal (`AEMET_API_KEY`, solo en variables de entorno / GitHub Secrets).
- **Términos (https://www.aemet.es/es/nota_legal, sección "Uso y reutilización", 2026-11-12):** reutilización autorizada al amparo de la Ley 18/2015 y el RD 1495/2011, con cesión gratuita y no exclusiva de los derechos para reproducir, distribuir, comunicar y transformar. Condiciones generales (cita): "1. Está prohibido desnaturalizar el sentido de la información. 2. Se debe citar a AEMET como fuente de la información objeto de la reutilización..." Los metadatos de la API repiten: "© AEMET. Autorizado el uso de la información y su reproducción citando a AEMET como autora de la misma."
- **Obligación:** citar "Fuente: AEMET" junto a lluvia y avisos (la UI lo hace).
- **Límite de peticiones de la API:** NO VERIFICADO (la página de condiciones de OpenData devolvió 404; `opendata.aemet.es/robots.txt` → 404). Se hacen 6 peticiones cada 15 min.
- **Aviso:** estas predicciones y datos no son un servicio de emergencia; la nota legal de AEMET lo explica en su sección de responsabilidad.

### Euskalmet — Agencia Vasca de Meteorología (conector `euskalmet`)

- Acceso por la API oficial de Open Data Euskadi (https://api.euskadi.eus/euskalmet) con clave propia gratuita, solicitada por el titular del proyecto.
- Licencia de reutilización: Open Data Euskadi publica sus datos para reutilización con atribución; **NO VERIFICADO** el texto exacto aplicable a esta API. Pendiente de leer y enlazar antes de un uso más allá del proyecto ciudadano.
- Uso: 1 petición por estación cada 15 min (48 peticiones por ciclo), User-Agent identificable, robots.txt respetado. La clave privada no se guarda en el repositorio: va en secretos (GitHub Actions y Vercel).
- Para la verificación (ley 8) se descargaron una vez 4 ficheros de datos que usa la web oficial (`/vamet/stations/readings/...`); robots.txt no lo prohíbe.

### Otros datos y servicios usados

- **Mapa base (RIESGO LEGAL para producción):** teselas de OpenStreetMap (© colaboradores de OpenStreetMap, ODbL), con atribución visible en el mapa. Su política de uso de teselas no admite uso intensivo: para producción hay que usar un proveedor propio o contratado.
- **Coordenadas y cotas de `engine/river_links.yaml`:** FeatureServer SAIH de MITECO (licencia NO VERIFICADA; campo `licenseInfo` vacío).
- **Episodio histórico de test** (`tests/fixtures/historical/`): hidrograma de la Rambla del Poyo del 29/10/2024, del repositorio público `datadista/datasets` (licencia AGPL-3.0), datos originales del SAIH de la CHJ. Solo se usa en tests.

## Fuentes investigadas, todavía sin conector

| Fuente | Términos leídos | Estado |
|---|---|---|
| DGT — NAP DATEX II | El catálogo del NAP devolvió 403 a la API | **NO VERIFICADO**; confirmar antes de mostrar imágenes de cámaras |
| Hidrosur | "Los contenidos del sitio web [...] son propiedad de la empresa o de terceros con licencia"; datos "no están verificados [...] carecen de valor oficial" | **Sin permiso expreso de reutilización → pedir autorización** |
| SAIH Guadalquivir | "Salvo que se indique lo contrario, la reproducción queda autorizada siempre que se cite su origen." | Reutilizable citando origen |
| SAIH Tajo | robots.txt: `Disallow: /*.php$`, `Disallow: /?w=`; aviso legal no leído | **Zona gris → consultar a la CHT** |
| SAIH Segura | "DATOS PROVISIONALES SUJETOS A REVISIÓN"; sin robots público | NO VERIFICADO |
| SAIH Júcar | El WAF rechaza el User-Agent identificable | **No usar sin permiso de la CHJ** |
| MITECO FeatureServer SAIH | `licenseInfo` vacío | NO VERIFICADO |
| SAIH Ebro, Duero, Miño-Sil | Inaccesibles desde el entorno de verificación | NO VERIFICADO |

## Reglas de scraping aplicadas por el código (`connectors/http.py`)

- User-Agent identificable y genérico; nunca se suplanta un navegador.
- robots.txt evaluado según RFC 9309 antes de cada recurso; si lo prohíbe, no se pide.
- Máximo 1 petición por recurso cada 15 minutos; dentro de la ventana se sirve la caché con su hora de descarga original.
- Si una fuente rechaza el acceso (WAF, 403, login), se respeta: no se rodea.
