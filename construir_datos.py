#!/usr/bin/env python3
"""
construir_datos.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Lee los ZIPs de votaciones/ y genera datos/<LEG>.json
con las votaciones ya procesadas, listas para que el
HTML las cargue directamente sin JSZip.

Uso:
  python construir_datos.py            # todas las legislaturas
  python construir_datos.py XV XIV     # solo esas
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import zipfile, json, re, sys, unicodedata
from datetime import date
from pathlib import Path

VOTACIONES_DIR = Path("votaciones")
DATOS_DIR      = Path("datos")

# ── Misma tabla GRUPO_META que el HTML ────────────────────
GRUPO_META = {
    # XV (2023-)
    'GP':              'pp',
    'GS':              'psoe',
    'GVOX':            'vox',
    'GSUMAR':          'sumar',
    'GR':              'erc',
    'GJxCAT':          'junts',
    'GEH Bildu':       'bildu',
    'GV (EAJ-PNV)':   'pnv',
    'GMx':             'otros',
    # XIV/XIII
    'GUP-EC-GC':       'podemos',
    'GCUP-EC-GC':      'podemos',
    'GCs':             'ciudadanos',
    'GCiudadanos':     'ciudadanos',
    'GPlu':            'otros',
    'gplu':            'otros',
    'GPLU':            'otros',
    # XII
    'GDL':             'pdecat',
    'GC-D':            'pdecat',
    # X/XI
    'GIU':             'iu',
    'GIU-ICV-EUiA-CHA':'iu',
    'GCiU':            'ciu',
    'GCIU-U':          'ciu',
    'GUPyD':           'upyd',
    'GUPYD':           'upyd',
    'GCUP':            'podemos',
    'GUpC':            'podemos',
    'GUEM':            'podemos',
    # Común a varias
    'GMIX':            'otros',
    'GMI':             'otros',
}

# ── Helpers ───────────────────────────────────────────────
def infer_legislatura(fecha_str: str) -> str:
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', fecha_str or '')
    if not m:
        return 'XV'
    d = date(int(m[3]), int(m[2]), int(m[1]))
    if d >= date(2023, 8, 17):  return 'XV'
    if d >= date(2019, 12, 3):  return 'XIV'
    if d >= date(2019, 3, 5):   return 'XIII'
    if d >= date(2016, 7, 19):  return 'XII'
    if d >= date(2016, 1, 13):  return 'XI'
    if d >= date(2011, 12, 13): return 'X'
    return 'anterior'

def infer_tipo(titulo: str) -> str:
    a = titulo.lower()
    if 'proyecto de ley' in a:                                        return 'Proyecto de ley'
    if 'proposición de ley orgánica' in a or 'proposicion de ley organica' in a: return 'Proposición de ley orgánica'
    if 'proposición de ley' in a or 'proposicion de ley' in a:       return 'Proposición de ley'
    if 'real decreto-ley' in a or 'decreto-ley' in a or 'convalidación' in a: return 'Convalidación decreto'
    if 'investidura' in a:                                            return 'Investidura'
    if 'moción de censura' in a:                                      return 'Moción de censura'
    if 'proposición no de ley' in a:                                  return 'Proposición no de ley'
    if 'moción' in a:                                                 return 'Moción'
    if 'presupuesto' in a:                                            return 'Presupuestos'
    if 'enmienda' in a:                                               return 'Enmienda'
    return 'Votación'

MONTHS = ['','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
def format_fecha(fecha_str: str) -> str:
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', fecha_str or '')
    if not m:
        return fecha_str or ''
    return f"{int(m[1])} {MONTHS[int(m[2])]} {m[3]}"

def normalize_voto(voto: str) -> str:
    v = unicodedata.normalize('NFD', voto or '').encode('ascii', 'ignore').decode().lower()
    if v == 'si':           return 'af'
    if v == 'no':           return 'ec'
    if v.startswith('abstenc'): return 'ab'
    return 'nv'

# ── Parse one JSON votacion ────────────────────────────────
next_id = [0]

def parse_votacion(data: dict, filename: str) -> dict | None:
    try:
        info   = data.get('informacion', {})
        totals = data.get('totales', {})
        vots   = data.get('votaciones', [])

        fecha   = info.get('fecha', '')
        titulo  = info.get('textoExpediente') or info.get('tituloSubGrupo') or filename.replace('.json', '')
        subtit  = ' · '.join(filter(None, [info.get('titulo'), info.get('tituloSubGrupo'), info.get('textoSubGrupo')]))

        raw_grupos = {}          # grupo → [diputado, ...]
        votos_ind  = {}          # diputado → {voto, grupo, pid}
        votos_agg  = {}          # pid → {af, ec, ab}

        for v in vots:
            grupo  = v.get('grupo', '')
            nombre = v.get('diputado', '')
            pid    = GRUPO_META.get(grupo, 'otros')
            if grupo and nombre:
                raw_grupos.setdefault(grupo, [])
                if nombre not in raw_grupos[grupo]:
                    raw_grupos[grupo].append(nombre)
                voto_key = normalize_voto(v.get('voto', ''))
                votos_ind[nombre] = {'voto': voto_key, 'grupo': grupo, 'pid': pid}
            if pid:
                votos_agg.setdefault(pid, {'af': 0, 'ec': 0, 'ab': 0})
                vk = normalize_voto(v.get('voto', ''))
                if vk in ('af', 'ec', 'ab'):
                    votos_agg[pid][vk] += 1

        af = totals.get('afavor', 0) or 0
        ec = totals.get('enContra', 0) or 0

        next_id[0] += 1
        sesion = info.get('sesion')
        num_v  = info.get('numeroVotacion')

        return {
            'id':               next_id[0],
            'legislatura':      infer_legislatura(fecha),
            '_rawGrupos':       raw_grupos,
            'votosIndividuales': votos_ind,
            'dedupKey':         f"{sesion}-{num_v}",
            'groupKey':         f"{sesion}-{(info.get('textoExpediente') or '')[:80]}-{info.get('textoSubGrupo') or ''}",
            'sesionNum':        sesion,
            'numVotacion':      num_v,
            'fecha':            format_fecha(fecha),
            'tipo':             infer_tipo(titulo),
            'titulo':           titulo,
            'descripcion':      subtit or titulo,
            'votRef':           f"Sesión {sesion or '?'}, votación {num_v or '?'}",
            'aprobada':         af > ec,
            'votos':            votos_agg,
            'source':           'repo',
        }
    except Exception as e:
        print(f"    ⚠ parse error {filename}: {e}")
        return None

# ── Process one legislature ────────────────────────────────
def build_legislatura(leg: str) -> int:
    src = VOTACIONES_DIR / leg
    DATOS_DIR.mkdir(exist_ok=True)
    out_path = DATOS_DIR / f"{leg}.json"

    # Load existing to avoid reprocessing
    existing = {}
    if out_path.exists():
        try:
            for v in json.loads(out_path.read_text()):
                existing[v['dedupKey']] = v
        except Exception:
            pass

    nuevos = 0
    for zip_path in sorted(src.glob("*.zip")):
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in sorted(zf.namelist()):
                    if not name.endswith('.json'):
                        continue
                    raw = zf.read(name)
                    try:
                        data = json.loads(raw.decode('utf-8'))
                    except UnicodeDecodeError:
                        data = json.loads(raw.decode('latin-1'))
                    v = parse_votacion(data, name)
                    if v and v['dedupKey'] not in existing:
                        existing[v['dedupKey']] = v
                        nuevos += 1
        except zipfile.BadZipFile as e:
            print(f"  ⚠ ZIP corrupto {zip_path.name}: {e}")

    # Sort by date desc, then sesion desc
    all_vots = sorted(existing.values(),
        key=lambda v: (v.get('fecha', ''), v.get('sesionNum') or 0, v.get('numVotacion') or 0),
        reverse=True)

    out_path.write_text(json.dumps(all_vots, ensure_ascii=False, separators=(',', ':')))
    print(f"  {leg}: {nuevos} nuevas  →  {len(all_vots)} total  ({out_path})")
    return nuevos

# ── Main ───────────────────────────────────────────────────
def main():
    legs = sys.argv[1:] or [p.name for p in sorted(VOTACIONES_DIR.iterdir()) if p.is_dir()]
    total = 0
    for leg in legs:
        if not (VOTACIONES_DIR / leg).exists():
            print(f"  ⚠ No existe votaciones/{leg}/")
            continue
        total += build_legislatura(leg)
    # Write datos/index.json listing available legislature files
    available = sorted(p.stem for p in DATOS_DIR.glob("*.json") if p.stem != 'index')
    (DATOS_DIR / 'index.json').write_text(json.dumps(available, ensure_ascii=False))
    print(f"\nTotal nuevas votaciones: {total}")
    print(f"datos/index.json → {available}")

if __name__ == '__main__':
    main()
