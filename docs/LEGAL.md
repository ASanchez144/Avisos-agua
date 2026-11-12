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

### ACA — Agència Catalana de l'Aigua (conector `aca`)

- **Recursos:** `GET https://aplicacions.aca.gencat.cat/sdim2/apirest/catalog?componentType=...` y `.../data/...` (4 peticiones cada 15 min).
- **robots.txt:** `https://aplicacions.aca.gencat.cat/robots.txt` devuelve 404 (sin restricciones declaradas).
- **Términos:** **NO VERIFICADO.** No se encontró página de condiciones de la API SDIM2. El dataset equivalente de datos abiertos declara "See Terms of Use" y atribución "Agència Catalana de l'Aigua (ACA)". Citar siempre a la ACA y **confirmar las condiciones antes de publicar**.

### AEMET OpenData (conector `aemet`)

- **Recursos:** observación convencional, avisos CAP e inventario, con API key personal (`AEMET_API_KEY`, nunca en el repositorio).
- **Términos (texto real de los metadatos de la API):** "© AEMET. Autorizado el uso de la información y su reproducción citando a AEMET como autora de la misma." Nota legal: https://www.aemet.es/es/nota_legal
- **Obligación:** citar "Fuente: AEMET". Límite de peticiones de la API: NO VERIFICADO.

### Otros datos y servicios usados

- **Mapa base:** teselas de OpenStreetMap (© colaboradores de OpenStreetMap, ODbL), con atribución visible en el mapa. Su política de uso de teselas no admite uso intensivo: para producción hay que usar un proveedor propio o contratado.
- **Coordenadas y cotas de `engine/river_links.yaml`:** FeatureServer SAIH de MITECO (licencia NO VERIFICADA; campo `licenseInfo` vacío).
- **Episodio histórico de test** (`tests/fixtures/historical/`): hidrograma de la Rambla del Poyo del 29/10/2024, del repositorio público `datadista/datasets` (licencia AGPL-3.0), datos originales del SAIH de la CHJ. Solo se usa en tests.

## Fuentes investigadas, todavía sin conector

| Fuente | Términos leídos | Estado |
|---|---|---|
| ACA — dataset `gn9e-3qhr` | Metadato `license: SEE_TERMS_OF_USE`; atribución "Agència Catalana de l'Aigua (ACA)" | Texto de las condiciones NO VERIFICADO |
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
