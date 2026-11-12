#!/usr/bin/env python3
"""Sondea las fuentes que no se pudieron probar desde el contenedor de desarrollo.

Ejecútalo en TU PC (IP española). Solo necesita `requests`:
    pip install requests
    python scripts/probe_sources.py                # todas
    python scripts/probe_sources.py ebro jucar     # solo algunas

Qué hace, por cada fuente:
  1. Lee robots.txt del host y NO pide las rutas que prohíbe (lo anota en el informe).
  2. Pide las URLs de la lista TARGETS (solo URLs verificadas o la portada del organismo).
  3. En modo descubrimiento, de la portada de Ebro/Júcar/Duero/Miño-Sil enlaza hasta 6 páginas del
     mismo sitio cuyo texto o URL contenga aforo/embalse/tabla/estacion/caudal/nivel/tiempo real.
     No inventa rutas: solo sigue enlaces que la propia página publica.
  4. Guarda cada respuesta REAL en tests/fixtures/<fuente>/ con su URL y fecha (<nombre>.meta.json).
  5. Escribe probe_report.json en la raíz del proyecto.

Pide como máximo 1 vez cada URL, con 2 s entre peticiones, User-Agent identificable, sin cookies ni
claves. Si el servidor rechaza el acceso (403, "Request Rejected"), se anota y NO se insiste.

Después: comprime `tests/fixtures/` y `probe_report.json` y devuélvemelos (ver README).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

ROOT = Path(__file__).resolve().parent.parent
UA = "HidroRed/0.1 (radar ciudadano hidrologico no oficial; prueba de fuentes)"
PAUSE_S = 2.0
TIMEOUT_S = 40
MAX_DISCOVERED = 6
KEYWORDS = re.compile(r"aforo|embalse|tabla|estaci[oó]n|caudal|nivel|tiempo[- ]?real|datos", re.I)
BIG_BYTES = 1_000_000

# fuente -> {"discover": bool, "urls": [(nombre, método, url, datos_form_o_None)]}
TARGETS: dict[str, dict] = {
    "saih_ebro": {"discover": True, "urls": [("portada", "GET", "https://www.saihebro.com/", None)]},
    "saih_jucar": {"discover": True, "urls": [("portada", "GET", "https://saih.chj.es/", None)]},
    "saih_duero": {"discover": True, "urls": [("portada", "GET", "https://www.saihduero.es/", None)]},
    "saih_minosil": {"discover": True, "urls": [("portada", "GET", "https://saih.chminosil.es/", None)]},
    "saih_tajo": {"discover": False, "urls": [("portada", "GET", "https://saihtajo.chtajo.es/", None)]},
    "saih_segura": {"discover": False, "urls": [
        ("ivisor_inicial", "GET", "https://saihweb.chsegura.es/apps/iVisor/inicial.php", None),
        ("cauces_topo", "POST", "https://saihweb.chsegura.es/apps/iVisor/obtener_datos.php", {"action": "consultar_cauces_topo"}),
    ]},
    "saih_guadalquivir": {"discover": False, "urls": [("aforos_sevilla", "GET", "https://www.chguadalquivir.es/saih/AforosSE.aspx", None)]},
    "hidrosur": {"discover": False, "urls": [
        ("resumen_rios", "GET", "https://www.redhidrosurmedioambiente.es/saih/resumen/rios", None),
        ("capas_aforos", "GET", "https://www.redhidrosurmedioambiente.es/saih/assets/visorSAIH/capas/Aforos.json", None),
    ]},
    "dgt": {"discover": False, "urls": [("camaras_datex2", "GET", "https://nap.dgt.es/datex2/v3/dgt/DevicePublication/camaras_datex2_v37.xml", None)]},
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "recurso"


def robots_allows(robots_txt: str | None, path: str) -> bool:
    """Evaluación sencilla de robots.txt (grupo `*`; la regla más larga gana)."""
    if not robots_txt:
        return True
    applies, best, allowed = False, -1, True
    for raw in robots_txt.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            applies = value == "*"
        elif applies and key in ("allow", "disallow") and value:
            pattern = re.escape(value).replace(r"\*", ".*")
            pattern = pattern[:-2] + "$" if pattern.endswith(r"\$") else pattern
            if re.match(pattern, path) and len(value) > best:
                best, allowed = len(value), key == "allow"
    return allowed


def save(source: str, name: str, resp: requests.Response, root: Path, stamp: str) -> dict:
    folder = root / "tests" / "fixtures" / source
    folder.mkdir(parents=True, exist_ok=True)
    ctype = resp.headers.get("Content-Type", "")
    ext = "json" if "json" in ctype else "xml" if "xml" in ctype else "html" if "html" in ctype else "txt"
    body = resp.content
    base = f"probe_{stamp}_{_slug(name)}"
    if len(body) > BIG_BYTES:
        (folder / f"{base}.{ext}.gz").write_bytes(gzip.compress(body))
        file = f"{base}.{ext}.gz"
    else:
        (folder / f"{base}.{ext}").write_bytes(body)
        file = f"{base}.{ext}"
    meta = {
        "url": resp.request.url, "method": resp.request.method, "status": resp.status_code, "content_type": ctype,
        "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "fetched_at_utc": stamp, "file": file,
        "elapsed_s": round(resp.elapsed.total_seconds(), 2),
    }
    (folder / f"{base}.meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    return meta


def verdict(meta: dict) -> str:
    if meta["status"] != 200:
        return f"HTTP {meta['status']}"
    if meta["bytes"] < 400:
        return "respuesta muy corta (¿bloqueo o error?)"
    return "OK"


class Prober:
    def __init__(self, session: requests.Session | None = None, root: Path = ROOT, pause: float = PAUSE_S) -> None:
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = UA
        self.root, self.pause = root, pause
        self.robots: dict[str, str | None] = {}
        self.stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def _robots(self, url: str) -> str | None:
        host = urlsplit(url)
        key = f"{host.scheme}://{host.netloc}"
        if key not in self.robots:
            try:
                r = self.session.get(key + "/robots.txt", timeout=TIMEOUT_S)
                self.robots[key] = r.text if r.status_code == 200 else None
            except requests.RequestException:
                self.robots[key] = None
            time.sleep(self.pause)
        return self.robots[key]

    def fetch(self, source: str, name: str, method: str, url: str, form: dict | None) -> dict:
        entry = {"name": name, "method": method, "url": url}
        parts = urlsplit(url)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        if not robots_allows(self._robots(url), path or "/"):
            return {**entry, "result": "OMITIDA: robots.txt no lo permite"}
        try:
            resp = self.session.request(method, url, data=form, timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            return {**entry, "result": f"FALLO DE RED: {type(exc).__name__}: {exc}"[:300]}
        finally:
            time.sleep(self.pause)
        meta = save(source, name, resp, self.root, self.stamp)
        return {**entry, **meta, "result": verdict(meta), "_html": resp.text if "html" in meta["content_type"] and meta["bytes"] < 3_000_000 else ""}

    def discover(self, base_url: str, html: str) -> list[tuple[str, str]]:
        host = urlsplit(base_url).netloc
        found: dict[str, str] = {}
        for href, label in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            text = re.sub(r"<[^>]+>", " ", label)
            url = urljoin(base_url, href.strip())
            if urlsplit(url).netloc != host or url.startswith("javascript"):
                continue
            if re.search(r"\.(png|jpg|gif|css|js|pdf|ico|svg)(\?|$)", url, re.I):
                continue
            if KEYWORDS.search(url) or KEYWORDS.search(text):
                found.setdefault(url, " ".join(text.split())[:40])
        return list(found.items())[:MAX_DISCOVERED]

    def run(self, only: list[str] | None = None) -> dict:
        report: dict = {"generated_at_utc": self.stamp, "user_agent": UA, "python": sys.version.split()[0], "sources": {}}
        for source, cfg in TARGETS.items():
            if only and source not in only:
                continue
            results = []
            for name, method, url, form in cfg["urls"]:
                r = self.fetch(source, name, method, url, form)
                html = r.pop("_html", "")
                results.append(r)
                if cfg["discover"] and r.get("result") == "OK" and html:
                    for link, label in self.discover(url, html):
                        d = self.fetch(source, f"descubierta_{label or 'enlace'}", "GET", link, None)
                        d.pop("_html", None)
                        d["descubierta_desde"] = url
                        results.append(d)
            ok = sum(1 for r in results if r["result"] == "OK")
            report["sources"][source] = {"ok": ok, "total": len(results), "results": results}
            print(f"[{source}] {ok}/{len(results)} OK")
            for r in results:
                print(f"    {r['result']:<40} {r['method']} {r['url']}")
        return report


def main(argv: list[str]) -> int:
    only = [a for a in argv if not a.startswith("-")] or None
    unknown = [a for a in (only or []) if a not in TARGETS]
    if unknown:
        print(f"Fuentes desconocidas: {unknown}. Disponibles: {list(TARGETS)}", file=sys.stderr)
        return 2
    report = Prober().run(only)
    out = ROOT / "probe_report.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\nInforme: {out}\nMuestras: {ROOT / 'tests' / 'fixtures'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
