# SOURCES_REPORT — HidroRed España (Fase 0)

- **Fecha de verificación:** 2026-11-11, 11:30–12:10 UTC.
- **Método:** peticiones reales con `curl` y un navegador headless (Playwright/Chromium) usando siempre el User-Agent identificable `HidroRed-Research/0.1 (proyecto ciudadano hidrologia; verificacion de fuentes)`. Nunca se suplantó un navegador ni se desactivó la verificación TLS.
- **Entorno:** contenedor cloud con salida HTTPS a través de un proxy de egreso (IP no española). **Esto condiciona varios resultados** (ver "Limitaciones del entorno").
- **Muestras reales:** `tests/fixtures/{fuente}/`. Cuando no hubo respuesta, se guarda `ACCESS_FAILURE.txt` con el comando y el error literal.
- Todo lo que no se pudo comprobar con una petición real está marcado **NO VERIFICADO** y no debe usarse como cierto.

## Resumen de veredictos

| # | Fuente | Veredicto | Formato | Umbrales oficiales | Timestamp por lectura |
|---|--------|-----------|---------|--------------------|-----------------------|
| 1 | **SAI Cantábrico** (CH Cantábrico) | **USABLE** | GeoJSON (POST) | Sí (3 niveles, caudal y nivel) | Sí, por variable |
| 2 | **ACA Cataluña — API SDIM2** | **USABLE** | JSON (GET) | No publicados en la API | Sí |
| 3 | ACA Cataluña — `gn9e-3qhr` (Socrata) | USABLE (solo embalses, diario) | JSON/CSV | No aplica | Diario |
| 4 | DGT — cámaras DATEX II (NAP) | **USABLE** | XML DATEX II v3.7 | No aplica | Sí (publicación) |
| 5 | AEMET OpenData | **USABLE** (radar nacional: 404) | JSON en 2 pasos + tar de XML CAP | Sí, avisos por zona (CAP) | Sí (`fint`, UTC, horario) |
| 6 | Hidrosur (Andalucía) | USABLE CON SCRAPING FRÁGIL | HTML + GeoJSON estático | Sí (capa estática, niveles) | Solo global de página |
| 7 | SAIH Guadalquivir | USABLE CON SCRAPING FRÁGIL | HTML (ASP.NET) | NO VERIFICADO | Solo global de página |
| 8 | SAIH Tajo | USABLE CON SCRAPING FRÁGIL | JSON con tokens cifrados | Sí (71 aforos, 3 niveles) | **No** en el listado |
| 9 | SAIH Segura | USABLE CON SCRAPING FRÁGIL | JSON (POST) | No (lo dice la propia web) | **No**; sin coordenadas |
| 10 | MITECO — FeatureServer SAIH (ArcGIS) | USABLE solo como **inventario estático** | GeoJSON/JSON | No | No hay lecturas |
| 11 | SAIH Júcar | **NO USABLE** con UA identificable | — | — | — |
| 12 | **SAIH Ebro** | **NO VERIFICABLE desde este entorno** | — | — | — |
| 13 | SAIH Duero | **NO VERIFICABLE desde este entorno** | — | — | — |
| 14 | SAIH Miño-Sil | **NO VERIFICABLE desde este entorno** | — | — | — |

## Limitaciones del entorno (honestidad)

1. **SAIH Ebro es inalcanzable desde aquí.** `www.saihebro.com` y `saihebro.com` (DNS → 192.148.213.77) aceptan el `CONNECT` del proxy pero la conexión se corta a los 10 s exactos, en 8 de 8 intentos, con TLS 1.3 y 1.2. El proxy lo registra como `ws_closed_mid_exchange ... tunnel closed (code 1006) after 10s`. Es un fallo de red entre el egreso y el servidor (posible filtrado geográfico o por rango de IP; **causa NO VERIFICADA**), no un bloqueo de política del entorno. Por tanto **no he podido verificar** `tabla-aforos`, `tabla-embalses` ni `ficha-estacion`. Evidencia: `tests/fixtures/saih_ebro/`.
2. **SAIH Duero:** `www.saihduero.es` → `502` del gateway al `CONNECT` ("host allowed, but the gateway could not connect to it"). `saihduero.es` → reset a los 2 s.
3. **SAIH Miño-Sil** y **`wms.mapama.gob.es`**: `curl: (60) SSL certificate problem: unable to get local issuer certificate`. La cadena de certificados no valida a través del proxy. No desactivo la verificación TLS, así que quedan sin verificar.
4. **AEMET:** verificado después con API key (inyectada por el proxy; nunca escrita en el repositorio). El radar nacional devolvió 404.

Ebro, Duero, Miño-Sil y el WMS de MITECO hay que reprobarlas desde una red española (o tu máquina) antes de dar un veredicto definitivo.

---

## 1. SAI Cantábrico (Confederación Hidrográfica del Cantábrico) — USABLE

- **URL exacta:** `https://visor.saichcantabrico.es/wp-admin/admin-ajax.php`
- **Método:** `POST`, cuerpo `application/x-www-form-urlencoded`: `action=peticion_cincominutal&tipo=todas`
- **Formato:** JSON `{"success": true, "data": <GeoJSON FeatureCollection>}`. 255 estaciones en una sola respuesta (~278 KB).
- **Cómo se encontró:** el JavaScript del visor está ofuscado; el endpoint se obtuvo observando las peticiones reales del visor con un navegador headless.
- **Campos reales** (`properties`; presentes según tipo de estación):
  - Identidad: `codigo_general`, `Cod_Roea`, `nombre`, `rio`, `municipio`, `provincia`, `sistema`, `zona_hidrologica`, `tipo_estacion`, `parametros_medidos`, `fuera_servicio`, `camara`.
  - Posición: `lat`, `lon` (WGS84, como cadenas) y `geometry.coordinates` `[lon, lat]`.
  - Caudal (114 estaciones): `caudal` (m³/s), `fecha_caudal`, `seguimiento_caudal`, `prealerta_caudal`, `alerta_caudal`, `color_caudal`, `tendencia_caudal`, `tipo_caudal`.
  - Nivel (136): `nivel` (m), `fecha_nivel`, `seguimiento_nivel`, `prealerta_nivel`, `alerta_nivel`, `color_nivel`, `tendencia_nivel`.
  - Lluvia (146): `precipit_1h`, `precipit_12h`, `precipit_24h` (mm), `fecha_precipitacion`.
  - Embalse (25): `nivel_embalse`, `volumen_embalse`, `porcentaje_llenado_embalse`, `volumenTotal_embalse`, `fecha_embalse`.
  - Otros: temperatura, piezómetros (66), nivómetros (9).
  - `fecha` (timestamp general de la estación).
- **Zona horaria:** las fechas van sin zona (`"2026-11-11 12:35:00"`). Petición hecha a las 11:42 UTC → son **hora local peninsular (Europe/Madrid)**.
- **Frecuencia real:** cincominutal (el propio `action` lo dice; fechas en múltiplos de 5 min, 7 min de retraso en la muestra). Confirmado con segunda muestra en la Fase 1 (ver anexo al final).
- **Umbrales oficiales:** **sí**, tres niveles por estación y variable: `seguimiento_*` → amarillo, `prealerta_*` → naranja, `alerta_*` → rojo. El visor usa esos mismos colores.
- **robots.txt:** `Disallow: /wp-admin/` con **`Allow: /wp-admin/admin-ajax.php`** explícito.
- **Términos (aviso legal del visor, texto real):** "La información contenida en este sitio web puede ser utilizada en parte o en su integridad, sin necesidad de autorización expresa, siempre que se cite la fuente [...]". Prohíbe el *framing* y cobrar por dar acceso a la información. No se puede sugerir que la CHC patrocina o apoya la reutilización.
- **Riesgos:** endpoint interno de WordPress, sin contrato de API; puede cambiar sin aviso. El raíz REST `https://serviciovisor.saichcantabrico.es/saiRestService/` devuelve 403 (no usar).
- **Fixture:** `tests/fixtures/saih_cantabrico/`.

## 2. ACA Cataluña — API SDIM2 (tiempo real) — USABLE

- **URLs exactas (GET, JSON):**
  - Catálogo: `https://aplicacions.aca.gencat.cat/sdim2/apirest/catalog?componentType=aforament` (también `embassament`, `pluviometre`).
  - Última lectura de todos los sensores: `https://aplicacions.aca.gencat.cat/sdim2/apirest/data/AFORAMENT-EST`
  - Serie de un sensor: `https://aplicacions.aca.gencat.cat/sdim2/apirest/data/AFORAMENT-EST/{sensor}?limit=N`
- **Campos reales:**
  - Catálogo: `sensor`, `description` (`Cabal riu`, `Nivell riu`...), `unit` (`m³/s`, `cm`, `l/s`), `location` (`"lat lon"`), `component`, `componentDesc`, `state`, `timeZone` (`CET`), `additionalInfo.Temps mostreig (min)`, `componentAdditionalInfo.Riu/Conca/Província/...`.
  - Datos: `sensors[].sensor`, `observations[].value` (cadena), `timestamp` (`"11/11/2026T11:15:00"`), `time` (epoch ms).
- **Cobertura:** 176 sensores de aforo (84 caudal río m³/s, 75 nivel río cm), 33 de embalse (nivel msnm, volumen hm³, %), 60 pluviómetros (intensidad mm/h — **no** acumulado 1 h/24 h).
- **Frecuencia real:** observaciones cada 5 min en la muestra (11:15, 11:10, 11:05...).
- **Umbrales oficiales:** no aparecen en la API → la UI debe decir "umbral no publicado".
- **Ojo:** nivel en **cm** (hay que convertir a m); `timestamp` textual parece UTC a juzgar por `time` (**comprobar al implementar**).
- **Términos:** **NO VERIFICADO** para SDIM2 (no encontré página de condiciones de la API). El dataset Socrata declara "See Terms of Use" (condiciones de datos abiertos de la Generalitat).
- **Fixture:** `tests/fixtures/aca/sdim2_*.json`.

## 3. ACA Cataluña — recurso `gn9e-3qhr` — USABLE (alcance limitado)

- **URL exacta:** `https://analisi.transparenciacatalunya.cat/resource/gn9e-3qhr.json` (Socrata SODA; admite `$limit`, `$order`, `$select`, `$group`).
- **Método/formato:** GET, JSON.
- **Qué es de verdad:** "Quantitat d'aigua als embassaments de les Conques Internes de Catalunya". **Solo 9 embalses, un dato diario** (agregado del día anterior). No tiene caudales ni lluvia.
- **Campos reales:** `dia`, `estaci`, `nivell_absolut` (msnm), `percentatge_volum_embassat` (%), `volum_embassat` (hm³). **Sin coordenadas ni código de estación.**
- **Frecuencia real:** diaria (metadato "Diària"; último `dia` = 2026-11-11).
- **Umbrales:** no.
- **Licencia:** `SEE_TERMS_OF_USE`, atribución "Agència Catalana de l'Aigua (ACA)".
- **Fixture:** `tests/fixtures/aca/gn9e-3qhr_latest.json`.

## 4. DGT — cámaras — USABLE

- **URL exacta que funciona:** `https://nap.dgt.es/datex2/v3/dgt/DevicePublication/camaras_datex2_v37.xml`
  (pedí `..._v36.xml` y redirige a `v37`; la versión del nombre cambia → resolver la redirección, no fijar el número).
- **Método/formato:** GET, XML DATEX II v3 (`DevicePublication`, perfil DGT), 3,7 MB.
- **Campos reales:** `publicationTime`, y por `device`: `@id`, `typeOfDevice` (= `camera`, 1975 dispositivos), `lastUpdateOfDeviceInformation`, `roadName`, `roadDestination`, `latitude`, `longitude`, `kilometerPoint`, `province`, `tpegDirectionRoad`, `deviceUrl` (p. ej. `https://etraffic.dgt.es/camarasEtraffic/176130.jpg`).
- **Frecuencia:** `publicationTime` = 11:00:01+01:00 en una descarga de las 12:50 locales → **parece horaria (NO VERIFICADO con segunda muestra)**. La imagen JPG se refresca aparte (frecuencia NO VERIFICADA).
- **Lo que NO existe / falla:**
  - `https://infocar.dgt.es/etraffic/data/camaras/camaras.json` → redirige al HTML de eTraffic. **No existe como JSON.**
  - `https://infocar.dgt.es/datex2/dgt/CCTVSiteTablePublication/all/content.xml` → `502`.
  - API CKAN del NAP (`/api/3/action/package_search`) → `403`.
- **Términos:** licencia del NAP **NO VERIFICADA** (el catálogo devolvió 403 a la API; hay que leer las condiciones en la web del NAP antes de publicar imágenes).
- **Fixture:** `tests/fixtures/dgt/`.

## 5. AEMET OpenData — USABLE (verificado con API key el 2026-11-11)

Base: `https://opendata.aemet.es/opendata/api/`. Autenticación por cabecera `api_key` (o parámetro `?api_key=`). **Flujo en dos pasos:** la primera llamada devuelve `{"descripcion","estado","datos","metadatos"}`; `datos` y `metadatos` son URLs temporales (`https://opendata.aemet.es/opendata/sh/...`) que se descargan sin key.

| Recurso | Ruta | Resultado real |
|---|---|---|
| Observación convencional | `observacion/convencional/todas` | **OK.** JSON, 9.723 registros de 855 estaciones (3,2 MB) |
| Avisos CAP | `avisos_cap/ultimoelaborado/area/esp` | **OK.** `application/x-gtar` (5,2 MB) con 515 ficheros XML CAP v1.2 |
| Inventario de estaciones | `valores/climatologicos/inventarioestaciones/todasestaciones` | **OK.** JSON, 926 estaciones |
| Radar nacional | `red/radar/nacional` | **FALLA:** `{"descripcion": "Error al obtener los datos", "estado": 404}` en 2 intentos. Ruta o disponibilidad **NO VERIFICADA** |

- **Trampas reales para el conector:**
  1. Sin `api_key`: **HTTP 200 con cuerpo vacío** (no 401).
  2. Key inválida: HTTP 401 con `{"estado": 401}`.
  3. Error de recurso: **HTTP 200 con `"estado": 404` dentro del JSON**. Hay que mirar siempre `estado`, nunca solo el código HTTP.
  4. Codificación `ISO-8859-15` declarada en cabeceras.
- **Observación — campos reales:** `idema`, `ubi` (nombre), `lat`, `lon`, `alt`, `fint` (fin del periodo, **UTC**, p. ej. `2026-11-11T11:00:00+0000`), `prec` (mm acumulados en los 60 min anteriores a `fint`), `ta`, `tamin`, `tamax`, `hr`, `vv`, `vmax`, `dv`, `dmax`, `pres`, `pres_nmar`, `tpr`, `ts`, `vis`, `inso`, `nieve`, `pacutp`...
  - Sirve para `rain_1h_mm` (`prec`). **No trae acumulado de 24 h**: hay que sumar las 24 horas de `prec` (la respuesta cubría 00:00–11:00 UTC del día; ventana exacta **NO VERIFICADA**).
- **Frecuencia real:** horaria. Descarga a las 12:03 UTC → último `fint` = 11:00 UTC. Metadato: `periodicidad: "continuamente"`.
- **Inventario — campos reales:** `indicativo`, `nombre`, `provincia`, `altitud`, `latitud` (`"394924N"`, grados-minutos-segundos), `longitud` (`"025309E"`), `indsinop`. Periodicidad: 1 vez al día.
- **Avisos CAP — campos reales (por XML):** `identifier`, `sent`, `info/event` ("Aviso de lluvias de nivel amarillo"), `severity` (Minor/Moderate/Severe/Extreme), `onset`, `expires`, `headline`, `description` ("Precipitación acumulada en 12 horas: 40 mm."), `parameter` `AEMET-Meteoalerta nivel` (verde/amarillo/naranja/rojo), `AEMET-Meteoalerta parametro` (`P2;Precipitación acumulada en 12 horas;40 mm`), `AEMET-Meteoalerta probabilidad`, `area/areaDesc`, `area/polygon`, `geocode` zona Meteoalerta. Periodicidad declarada: emisión en cualquier momento, horas preferentes 09:00, 11:30, 23:00 y 23:50 h.o.p.
- **Umbrales oficiales:** sí para **avisos meteorológicos por zona** (nivel y umbral vienen en cada CAP). No son umbrales por estación hidrológica.
- **Términos (texto real de los metadatos):** "© AEMET. Autorizado el uso de la información y su reproducción citando a AEMET como autora de la misma." Nota legal: `https://www.aemet.es/es/nota_legal`.
- **Límite de peticiones de la API:** NO VERIFICADO.
- **Fixture:** `tests/fixtures/aemet/` (paso 1 de cada ruta, datos, metadatos, un CAP de muestra y listado del tar). No contiene la key.

## 6. Hidrosur (Cuencas Mediterráneas Andaluzas) — USABLE CON SCRAPING FRÁGIL

- **URLs exactas:**
  - `https://www.redhidrosurmedioambiente.es/saih/resumen/rios` — GET, **HTML**, tabla de 40 ríos.
  - `https://www.redhidrosurmedioambiente.es/saih/assets/visorSAIH/capas/Aforos.json` — GET, **GeoJSON estático**, 38 aforos.
  - Otras páginas existentes (no analizadas): `/saih/resumen/embalses`, `/saih/resumen/precipitacion`, `/saih/mapa/tiempo/real`.
- **Campos reales (tabla ríos):** `Número`, `Nombre`, `Nivel medio (m)`, `Caudal medio (m³/s)`, `Tendencia`, máximos históricos (fecha, nivel, caudal). Decimales con coma. Pie: "Datos actualizados a: 11-11-2026 12:00:00".
- **Campos reales (capa Aforos):** `COD_`, `Nombre`, `Latitud`, `Longitud`, `Río`, `Provincia`, `Municipio`, **`Aviso`, `Prealerta`, `Alerta`** (niveles en m), `Max_Nivel`, `Fecha_Max`.
- **Frecuencia real:** sello global "12:00:00" visto a las 12:55 locales → **parece horaria (NO VERIFICADO)**. Son valores **medios**, no instantáneos.
- **Umbrales oficiales:** sí, en la capa estática (3 niveles de nivel). Cruce por `COD_` = `Número` (**cruce NO VERIFICADO estación a estación**).
- **robots.txt:** `User-agent: *` sin restricciones.
- **Términos (texto real):** contenidos "propiedad de la empresa o de terceros con licencia"; "los datos [...] no están verificados [...] carecen de valor oficial". **No hay permiso expreso de reutilización** → pedir autorización antes de publicar.
- **Fixture:** `tests/fixtures/hidrosur/`.

## 7. SAIH Guadalquivir — USABLE CON SCRAPING FRÁGIL

- **URLs exactas:** `https://www.chguadalquivir.es/saih/AforosSE.aspx` (también enlazadas `aforosJA.aspx`, `AforosCO.aspx`, `AforosGR.aspx`; solo se descargó SE). Índice: `https://www.chguadalquivir.es/saih/AforosMapa.aspx`.
- **Método/formato:** GET, **HTML ASP.NET WebForms**; cada estación es una mini-tabla: `['A12 El Pedroso'] / ['Nivel','','0,51 m.s.n.m'] / ['Caudal','','2,96 m³/s']`.
- **Campos reales:** código+nombre, nivel (unidad `m.s.n.m` o `m.l.a` según estación), caudal (`m³/s` o el literal **`Sin datos`**). Sello global: "Aviso: Datos no contrastados. Actualizados: 11/11/2026 12:37:53". **Sin coordenadas** en la página.
- **Frecuencia real:** sello 11 min anterior a la descarga; periodo exacto NO VERIFICADO.
- **Umbrales:** existen páginas `av_Mapa.aspx` (Avenidas) y `FichaAviso.aspx`; **contenido NO VERIFICADO**. `ListaRT.aspx` exige login.
- **robots.txt:** no restringe `/saih/`.
- **Términos (texto real):** "Salvo que se indique lo contrario, la reproducción queda autorizada siempre que se cite su origen."
- **Fixture:** `tests/fixtures/saih_guadalquivir/`.

## 8. SAIH Tajo — USABLE CON SCRAPING FRÁGIL

- **Motor:** SPA propia (Onsen UI + Mustache). Todo se pide a `https://saihtajo.chtajo.es/index.php?w=<acción>&x=<token cifrado>`. Los tokens `x` **no se pueden construir**: hay que encadenar HTML de portada → `get-wrapperentorno` → `get-menu` → enlace deseado (4 peticiones). Los tokens fueron idénticos en dos descargas separadas 10 min (estabilidad a largo plazo NO VERIFICADA).
- **Recursos verificados (GET, JSON):**
  - `w=get-aforosenrio` → `response.aforos[]` (71 estaciones): `codigo`, `nombre`, `senal`, `value`, `unidad` (68 en `m`, 3 en `m³/s`), **`umbral1`, `umbral2`, `umbral3`**, `estado` (`Normalidad`/`Umbral amarillo`/...), `tendencia`, `estacion.utm{x,y,z,huso}`, municipio, provincia.
  - `w=get-datos-tiempo-real` → árbol de estaciones con UTM, pero `senales: []` (los valores se piden estación a estación con `get-estacion`).
  - Existe también `w=get-embalses` (no descargado).
- **Umbrales oficiales:** **sí**: amarillo/naranja/rojo, "los establecidos en el Protocolo de Comunicación y Avisos de la Información Hidrológica en caso de crecidas" (texto de la propia respuesta). Monótonos en las 71 estaciones.
- **Problemas serios:**
  1. **El listado no trae fecha/hora de la lectura** → no se puede cumplir la regla de DATO_OBSOLETO sin pedir cada estación.
  2. Algunos niveles son **cotas absolutas** (AR04 = 744,556 m), no alturas sobre escala.
  3. `robots.txt`: `Disallow: /*.php$`, `Disallow: /?w=`. Nuestras URLs (`/index.php?w=...`) no casan literalmente con esos patrones, pero la intención parece ser excluir estos endpoints → **zona gris; consultar a la CHT antes de usar**.
- **Términos:** aviso legal no leído (robots lo excluye) → NO VERIFICADO.
- **¿Comparte motor y rutas con Miño-Sil?** **NO VERIFICADO.** No pude abrir `saih.chminosil.es` (error de certificado). No lo afirmo ni lo niego.
- **Fixture:** `tests/fixtures/saih_tajo/`.

## 9. SAIH Segura — USABLE CON SCRAPING FRÁGIL

- **URL exacta:** `https://saihweb.chsegura.es/apps/iVisor/obtener_datos.php` — `POST`, cuerpo `action=consultar_cauces_topo` → JSON (33 puntos).
- **Campos reales:** `CodPuntoMedicion`, `NombreCortoPM`, `UltimoDatoNivel` (m, coma decimal), `UltimoDatoCaudal` (m³/s, coma decimal; `"-"` = desbordamiento), `CotaMaximaSeccion`, `PorcentajeNivel`, `ColorFondo`; `x`,`y` son **píxeles** del esquema, no coordenadas.
- **Carencias:** sin lat/lon, sin timestamp por lectura (solo `fechaactual` incrustada en `topo_cauces1.php`), sin río.
- **Umbrales:** **no**. La web lo dice: "Los colores de la leyenda [...] no [se corresponden] con umbrales de comunicación de avisos".
- **Otros:** `https://saihweb.chsegura.es/robots.txt` redirige a un login CAS (no hay robots público). Otras acciones vistas, no probadas: `LeerDatos`, `Embalses`.
- **Términos:** NO VERIFICADO. Página marcada "DATOS PROVISIONALES SUJETOS A REVISIÓN".
- **Fixture:** `tests/fixtures/saih_segura/`.

## 10. MITECO — servicio real de estaciones SAIH

- **Servicio que funciona:** `https://services-eu1.arcgis.com/RvnYk1PBUJ9rrAuT/arcgis/rest/services/SAIH/FeatureServer` (ArcGIS REST, propietario `visorDGA_miteco`, capacidades `Query,Extract`). Es **ArcGIS FeatureServer, no WFS** (interfaz WFS: NO VERIFICADA).
  - Capas: `1` Red Integrada de Estaciones de Aforos (SAIH-ROEA), `3` Aforo en embalse SAIH, `4` Estaciones pluviométricas SAIH, `5` Aforo en río SAIH (Caudal) — 884 entidades.
  - Consulta: `.../FeatureServer/5/query?where=1%3D1&outFields=*&f=geojson&outSR=4326`
  - Campos reales: `IDPUNTO`, `IDSAIH` (cuenca, p. ej. `ACA`), `TIPO` + geometría punto.
- **Es solo inventario:** no hay lecturas, ni nombre, ni río; último cambio de datos en 2023. Sirve para **dar coordenadas** a fuentes que no las publican (Segura, Guadalquivir), si el `IDPUNTO` casa (**NO VERIFICADO**).
- **WMS:** `https://wms.mapama.gob.es/sig/agua/aforos` aparece catalogado como WMS "Red Hidrométrica - Aforo", pero desde aquí falla la validación TLS → **NO VERIFICADO**.
- **Confirmado:** el panel `https://miteco.maps.arcgis.com/apps/dashboards/912dfee767264e3884f7aea8eb1e0673` (Boletín Hidrológico) es un *dashboard*, no un servicio de datos.
- **Licencia:** campo `licenseInfo` vacío → NO VERIFICADA.
- **Fixture:** `tests/fixtures/miteco/`.

## 11. SAIH Júcar — NO USABLE (con nuestras reglas)

- `https://saih.chj.es/` → HTTP 200 con página de WAF: **"Request Rejected. The requested URL was rejected."** al usar el User-Agent identificable. `robots.txt` → 404.
- No probé con User-Agent de navegador: sería saltarse un control anti-bot y contradice la regla 4. Para usar esta fuente hay que **pedir acceso a la CHJ**.
- **Fixture:** `tests/fixtures/saih_jucar/root_request_rejected.html`.

## 12–14. SAIH Ebro, Duero, Miño-Sil — NO VERIFICABLES desde este entorno

Ver "Limitaciones del entorno". Sin respuesta real no hay URL, campos, frecuencia, umbrales ni términos que reportar: **todo NO VERIFICADO**. Dato lateral: `https://saih.chebro.es/` existe y devuelve `403 Forbidden` (Apache); `https://www.chebro.es/` responde 200 y enlaza `/web/guest/saih`.

---

## 15. Euskalmet (País Vasco) — USABLE (verificado con clave el 2026-11-12)

- API oficial https://api.euskadi.eus/euskalmet, clave gratuita, autenticación JWT RS256 firmada con la clave privada del usuario.
- 154 estaciones: 59 de aforo (GAUGING), 61 meteorológicas, 26 de calidad del agua y 8 boyas.
- Nivel de la lámina de agua (`measuresForWater/sheet_level_*`, unidad METERS publicada por `/euskalmet/measures`) cada 10 min,
  hora en UTC (`dateRange` en epoch ms), `null` cuando falta el dato. Retraso medido: unos 7 min.
- Conector `euskalmet`: 48 estaciones de nivel (inventario en `engine/euskalmet_stations.json`). Una petición por estación y ciclo (12 s en total).
- Contrastado con la web oficial (www.euskalmet.euskadi.eus/vamet/...): los valores de todos los tramos comunes coinciden exactamente.
- NO VERIFICADO: unidad del caudal calculado (la API no la publica); acumulados de lluvia (solo tramos de 10 min). Sin umbrales publicados.
- Tobillas (C00B) publica una cota (694 m), no un calado: sale SUSPECT, sin semáforo.
- El endpoint agregado por día rellena los huecos con 0.0: no se usa.

## Orden de implementación propuesto (por fiabilidad)

1. **SAI Cantábrico** — una petición, GeoJSON, coordenadas, timestamps por variable, umbrales oficiales, robots lo permite, reutilización autorizada citando fuente. Cubre todo el esquema común.
2. **ACA SDIM2** — API JSON limpia; sin umbrales; confirmar términos.
3. **AEMET OpenData** — API oficial, licencia clara (citar a AEMET), lluvia horaria y avisos CAP. Radar pendiente.
4. **DGT cámaras (DATEX II)** — XML estable; confirmar licencia del NAP.
5. **Hidrosur** — scraping HTML + capa de umbrales; pedir permiso de reutilización.
6. **SAIH Guadalquivir** — scraping HTML por zonas; faltan coordenadas (cruzar con MITECO).
7. **SAIH Tajo** — tiene umbrales, pero tokens cifrados, sin timestamp y robots dudoso: hablar antes con la CHT.
8. **SAIH Segura** — sin coordenadas, sin timestamp, sin umbrales.
9. **MITECO FeatureServer** — no es fuente de lecturas; usar como inventario auxiliar.
10. **Ebro, Duero, Miño-Sil, Júcar** — reprobar desde red española; Júcar requiere permiso.

## Decisión para la Fase 1

La instrucción era "SAIH Ebro (o el mejor veredicto USABLE del informe)". El Ebro **no es alcanzable desde este contenedor**, así que no puedo construir ni contrastar honestamente su conector aquí. La Fase 1 se construye sobre **SAI Cantábrico**, el mejor veredicto USABLE. El conector del Ebro queda pendiente de verificación desde una red que llegue a `saihebro.com`.

---

## Anexo (Fase 1): comprobaciones adicionales sobre SAI Cantábrico

- **Frecuencia confirmada con dos muestras reales:** descarga ~11:42 UTC → `fecha` más reciente 12:35 local; descarga 11:50:56 UTC → 12:45 local. Fechas siempre en múltiplos de 5 min, con ~5–7 min de retraso de publicación.
- **Zona horaria confirmada:** fechas en hora local peninsular (12:45 local = 11:45 UTC en noviembre).
- **Contraste con la web oficial:** 232 medidas (nivel y caudal) y 328 umbrales de la respuesta coinciden con el texto de la tabla del visor oficial capturado en el mismo ciclo (`tests/reference/saih_cantabrico/`).
- **Colores de umbral confirmados en la captura del visor:** seguimiento = amarillo, prealerta = naranja, alerta = rojo.
- **Centinelas reales encontrados:** fecha `1970-01-01 00:00:00` (sin dato); el visor muestra `-`. No apareció `-999` en datos reales (el conector lo trata igualmente como ausente).
- **Rarezas reales:** umbrales parciales (solo amarillo, o amarillo+naranja) en ~34 estaciones; un embalse con volumen `-0.02` hm³ (Leurtza Superior → SUSPECT); una estación fuera de servicio (1407 → MISSING); variables de una misma estación con horas distintas (p. ej. caudal de las 03:40 junto a nivel de las 12:30; el visor lo pinta en gris).

---

## Anexo (Fase 2): hallazgos nuevos

- **ACA publica umbrales, pero no en SDIM2.** El visor oficial `https://aetr.aca.gencat.cat/` usa otra API (`https://api.aetr.aca.gencat.cat`): `Threshold/product/{id}` (umbrales por producto en cm y m³/s), `timeline/{id}` (series de caudal, nivel y embalses) y `catalog/elements/...`. Requiere un `POST /Authorization/public` que hace el propio visor. **Contenido de los umbrales NO VERIFICADO; no se usa.**
- **ACA: un embalse puede compartir componente con su aforo de salida** (p. ej. `080581-002`, Foix: embalse + "Q sortida"). El conector lo trata como una sola estación.
- **AEMET: la web oficial no tiene ya fichas por estación en la URL antigua** (`ultimosdatos?k=...&l=...` → 404). La página "Hoy y últimos días" carga `https://www.aemet.es/es/api-eltiempo/udat/tablas-graficas/horario/6/esp/{fecha}` (XML por estación y hora). Se usó como referencia L8: 517 valores de lluvia horaria coinciden con OpenData, 0 difieren.
- **AEMET OpenData trae ~12 horas por estación** (547 estaciones con 12 registros horarios), no 24.
- **MITECO FeatureServer, capa 1 (SAIH-ROEA):** sí trae nombre, río, municipio, cota y superficie de cuenca. De ahí salen las coordenadas de Jaca (A018), Yesa (A101), Caparroso (A005) y Zaragoza (A011). La capa 5 incluye el punto "AFORO RAMBLA POYO" (39,47537, −0,5818).
- **Hidrograma real de la Rambla del Poyo (29/10/2024):** dataset público `datadista/datasets/dana-valencia` (AGPL-3.0). Máximo registrado 2.282,9 m³/s a las 18:55; a partir de las 19:00 el sensor falla.
- **Wikipedia** limitó las peticiones desde este entorno (HTTP 429) al pedir coordenadas: no se reintentó.
