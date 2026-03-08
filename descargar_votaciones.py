#!/usr/bin/env python3
"""
descargar_votaciones.py  (multi-legislatura, parallel)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Descarga todos los ZIPs de votaciones del Congreso para
una o varias legislaturas, usando peticiones paralelas.

Uso:
  pip install requests beautifulsoup4

  # Todas las legislaturas (XII → XV):
  python descargar_votaciones.py

  # Solo una o varias:
  python descargar_votaciones.py --leg XV
  python descargar_votaciones.py --leg XIV XV

Los ZIPs se guardan en ./votaciones/<LEGISLATURA>/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import re
import sys
import time
import argparse
import threading
import requests
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── CONFIG ────────────────────────────────────────────────
BASE_URL       = "https://www.congreso.es"
INDEX_URL      = "https://www.congreso.es/es/opendata/votaciones"
TIMEOUT        = 30
RETRIES        = 4    # reintentos por petición
RETRY_BACKOFF  = 2.0  # segundos base (se duplica cada intento)
WORKERS_SCRAPE = 8
WORKERS_DL     = 6
OUTPUT_ROOT    = Path("votaciones")

# Legislaturas: código → (num en URL, fecha inicio, fecha fin, filtro en href)
LEGISLATURAS = {
    # roman_label: (href_filter, start_date, end_date)
    # targetLegislatura uses the roman numeral key directly
    "XV":   ("Leg15", date(2023,  8, 17), date.today()      ),
    "XIV":  ("Leg14", date(2019, 12,  3), date(2023,  8, 16)),
    "XIII": ("Leg13", date(2019,  3,  5), date(2019,  9, 24)),
    "XII":  ("Leg12", date(2016,  7, 19), date(2019,  3,  4)),
    "XI":   ("Leg11", date(2016,  1, 13), date(2016,  7, 18)),
    "X":    ("Leg10", date(2011, 12, 13), date(2016,  1, 12)),
}
# ─────────────────────────────────────────────────────────


# ── RETRY HELPER ─────────────────────────────────────────
def get_with_retry(url: str, stream: bool = False) -> requests.Response:
    """GET con reintentos y backoff exponencial. Imprime cada intento fallido."""
    delay = RETRY_BACKOFF
    for attempt in range(1, RETRIES + 1):
        try:
            r = get_session().get(url, timeout=TIMEOUT, stream=stream)
            if r.status_code < 500:
                return r
            raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            if attempt < RETRIES:
                print(f"  ↻ intento {attempt}/{RETRIES} fallido ({type(e).__name__}), reintentando en {delay:.0f}s…")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"  ✗ intento {attempt}/{RETRIES} fallido ({type(e).__name__}), abandonando.")
                raise


# ── SESIÓN THREAD-LOCAL ───────────────────────────────────
_local = threading.local()

def get_session() -> requests.Session:
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language":           "es-ES,es;q=0.9,en;q=0.8",
            "Accept-Encoding":           "gzip, deflate, br",
            "Connection":                "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest":            "document",
            "Sec-Fetch-Mode":            "navigate",
            "Sec-Fetch-Site":            "none",
            "Sec-Fetch-User":            "?1",
            "Cache-Control":             "max-age=0",
        })
        _local.session = s
    return _local.session


# ── FASE 1: SCRAPING ──────────────────────────────────────

def get_zips_for_date(d: date, leg_label: str, href_filter: str) -> list:
    """Consulta el índice para una fecha+legislatura y devuelve URLs de ZIP."""
    date_str = f"{d.day}/{d.month:02d}/{d.year}"
    url = (
        f"{INDEX_URL}"
        f"?p_p_id=votaciones&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
        f"&targetLegislatura={leg_label}&targetDate={date_str}"
    )
    try:
        r = get_with_retry(url)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ⚠ {leg_label} {d}: sin ZIPs (todos los intentos fallaron)")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    return [
        urljoin(BASE_URL, a["href"])
        for a in soup.find_all("a", href=True)
        if a["href"].endswith(".zip") and href_filter in a["href"]
    ]


def scrape_legislatura(leg_label: str, start: date, end: date, href_filter: str) -> list:
    """Escanea todos los días de una legislatura en paralelo."""
    all_days = []
    d = start
    while d <= end:
        all_days.append(d)
        d += timedelta(days=1)

    total     = len(all_days)
    found     = {}
    completed = 0

    print(f"\n  📅 Legislatura {leg_label}: {total} días ({start} → {end})")

    with ThreadPoolExecutor(max_workers=WORKERS_SCRAPE) as ex:
        futures = {
            ex.submit(get_zips_for_date, d, leg_label, href_filter): d
            for d in all_days
        }
        for fut in as_completed(futures):
            d    = futures[fut]
            zips = fut.result()
            completed += 1

            if zips:
                found[d] = zips
                print(f"    ✓ {d.strftime('%d/%m/%Y')} → {len(zips)} ZIP(s)  [{completed}/{total}]")
            elif completed % 100 == 0:
                print(f"    · {completed}/{total} días ({completed/total*100:.0f}%)")

    # Aplanar, deduplicar, ordenar por fecha
    zip_urls = []
    seen = set()
    for d in sorted(found.keys()):
        for url in found[d]:
            if url not in seen:
                seen.add(url)
                zip_urls.append(url)

    print(f"  → {len(zip_urls)} ZIPs únicos encontrados en {leg_label}")
    return zip_urls


# ── FASE 2: DESCARGA ──────────────────────────────────────

def download_zip(url: str, output_dir: Path) -> tuple:
    """Descarga un ZIP. Devuelve (url, 'ok'|'skip'|'error')."""
    filename = url.split("/")[-1]
    m        = re.search(r"/Sesion(\d+)/(\d{8})/", url)
    prefix   = f"sesion{m.group(1)}_{m.group(2)}_" if m else ""
    dest     = output_dir / f"{prefix}{filename}"

    if dest.exists():
        return url, "skip"

    try:
        r = get_with_retry(url, stream=True)
        if r.status_code == 404:
            return url, "missing"  # enlace roto en el índice del congreso, ignorar
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        return url, "ok"
    except requests.RequestException as e:
        print(f"    ✗ {filename}: {e}")
        if dest.exists():
            dest.unlink()
        return url, "error"


def download_all(zip_urls: list, output_dir: Path) -> tuple:
    """Descarga todos los ZIPs en paralelo."""
    total      = len(zip_urls)
    downloaded = skipped = errors = 0
    completed  = 0

    print(f"\n  📦 Descargando {total} ZIPs → {output_dir}")

    with ThreadPoolExecutor(max_workers=WORKERS_DL) as ex:
        futures = {ex.submit(download_zip, url, output_dir): url for url in zip_urls}
        for fut in as_completed(futures):
            url, result = fut.result()
            name = url.split("/")[-1]
            completed += 1

            if result == "ok":
                downloaded += 1
                print(f"  [{completed}/{total}] ↓ {name}")
            elif result == "skip":
                skipped += 1
            elif result == "missing":
                pass   # enlace roto en el índice, ignorar silenciosamente
            else:
                errors += 1

    return downloaded, skipped, errors


# ── MAIN ──────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Descarga votaciones del Congreso de los Diputados"
    )
    parser.add_argument(
        "--leg", nargs="+",
        choices=list(LEGISLATURAS.keys()),
        default=list(LEGISLATURAS.keys()),
        metavar="LEG",
        help=f"Legislaturas a descargar. Opciones: {', '.join(LEGISLATURAS)}. Por defecto: todas. Ejemplo: --leg XV XIV"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    legs = args.leg  # respeta el orden que pase el usuario

    print("╔══════════════════════════════════════════╗")
    print("║  Descargador de votaciones — Congreso.es ║")
    print("╚══════════════════════════════════════════╝")
    print(f"Legislaturas : {', '.join(legs)}")
    print(f"Directorio   : {OUTPUT_ROOT.resolve()}\n")

    t0     = time.time()
    totals = {"downloaded": 0, "skipped": 0, "errors": 0}

    for leg in legs:
        href_filter, start, end = LEGISLATURAS[leg]
        output_dir = OUTPUT_ROOT / leg
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"━━━ Legislatura {leg} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        zip_urls = scrape_legislatura(leg, start, end, href_filter)

        if not zip_urls:
            print(f"  ⚠ No se encontraron ZIPs para la legislatura {leg}")
            continue

        dl, sk, er = download_all(zip_urls, output_dir)
        totals["downloaded"] += dl
        totals["skipped"]    += sk
        totals["errors"]     += er

        print(f"  ✅ {leg}: {dl} descargados, {sk} ya existían, {er} errores")

    elapsed = time.time() - t0
    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Total descargados  : {totals['downloaded']}
⏭  Ya existían        : {totals['skipped']}
❌ Errores             : {totals['errors']}
⏱  Tiempo total       : {elapsed:.0f}s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 {OUTPUT_ROOT.resolve()}

Arrastra las carpetas (o ZIPs individuales)
a la app del Congreso para importarlos.
Vuelve a ejecutar para actualizar — solo
descarga los ZIPs que aún no existan.
""")


if __name__ == "__main__":
    main()
