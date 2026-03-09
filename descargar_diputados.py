#!/usr/bin/env python3
"""
descargar_diputados.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Descarga los JSON de diputados por legislatura
desde congreso.es/es/opendata/diputados y los
guarda en diputados/ con nombres normalizados.

Uso:
  python descargar_diputados.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import re
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL   = "https://www.congreso.es"
INDEX_URL  = f"{BASE_URL}/es/opendata/diputados"
OUT_DIR    = Path("diputados")

# Legislaturas que nos interesan (00 = Constituyente, 01..XV)
# El script descarga todas las que encuentre, pero puedes filtrar aquí:
ONLY_LEGS = None  # None = todas; o ej. {'XV', 'XIV', 'XIII', 'XII', 'XI', 'X'}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def download_file(url: str, dest: Path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        f.write(r.read())


def leg_code(filename: str) -> str | None:
    """
    Convierte el nombre de archivo del Congreso a código de legislatura.
    odsDiputados14__ → XIV
    odsDiputados00__ → Constituyente
    DiputadosActivos → XV  (diputados en activo = legislatura actual)
    """
    ROMAN = {
        '00': 'Constituyente',
        '01': 'I',   '02': 'II',  '03': 'III', '04': 'IV',
        '05': 'V',   '06': 'VI',  '07': 'VII', '08': 'VIII',
        '09': 'IX',  '10': 'X',   '11': 'XI',  '12': 'XII',
        '13': 'XIII','14': 'XIV',
    }
    m = re.search(r'odsDiputados(\d{2})', filename)
    if m:
        return ROMAN.get(m.group(1))
    if 'DiputadosActivos' in filename:
        return 'XV'
    return None


def main():
    OUT_DIR.mkdir(exist_ok=True)

    print(f"🔍  Leyendo {INDEX_URL} …")
    try:
        html = fetch(INDEX_URL)
    except Exception as e:
        print(f"  ✗ No se pudo acceder a la página: {e}")
        return

    # Find all JSON links under /webpublica/opendata/diputados/
    json_paths = re.findall(r'href="(/webpublica/opendata/diputados/[^"]+\.json)"', html)
    if not json_paths:
        print("  ✗ No se encontraron enlaces JSON en la página.")
        return

    print(f"  {len(json_paths)} archivos JSON encontrados\n")

    downloaded = 0
    skipped    = 0

    for path in json_paths:
        filename = path.split("/")[-1]
        leg      = leg_code(filename)

        # Skip files we don't care about (e.g. Diputadas, DeclaraciónIntereses, etc.)
        if leg is None:
            continue

        if ONLY_LEGS and leg not in ONLY_LEGS:
            continue

        dest = OUT_DIR / f"diputados_{leg}.json"
        url  = BASE_URL + path

        if dest.exists():
            print(f"  ⏭  {leg:15s}  ya existe, saltando")
            skipped += 1
            continue

        try:
            print(f"  ⬇  {leg:15s}  {filename}", end="", flush=True)
            download_file(url, dest)
            size_kb = dest.stat().st_size // 1024
            print(f"  ✓  ({size_kb} KB)")
            downloaded += 1
        except urllib.error.HTTPError as e:
            print(f"  ✗  HTTP {e.code}")
        except Exception as e:
            print(f"  ✗  {e}")

    print(f"\n✅  {downloaded} descargados, {skipped} ya existían")
    print(f"   Guardados en: {OUT_DIR.resolve()}/")


if __name__ == "__main__":
    main()
