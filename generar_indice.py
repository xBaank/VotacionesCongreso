#!/usr/bin/env python3
"""
generar_indice.py
Genera votaciones/index.json con la lista de todos los ZIPs por legislatura.
Se ejecuta tras descargar_votaciones.py en el workflow.
"""
import json
from pathlib import Path

VOTACIONES_DIR = Path("votaciones")
INDEX_FILE     = VOTACIONES_DIR / "index.json"

index = {}
for leg_dir in sorted(VOTACIONES_DIR.iterdir()):
    if not leg_dir.is_dir():
        continue
    zips = sorted(f.name for f in leg_dir.glob("*.zip"))
    if zips:
        index[leg_dir.name] = zips

INDEX_FILE.write_text(json.dumps(index, indent=2))
total = sum(len(v) for v in index.values())
print(f"✓ index.json actualizado: {total} ZIPs en {len(index)} legislaturas")
