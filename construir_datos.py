#!/usr/bin/env python3
"""
construir_datos.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Lee los ZIPs de votaciones/ y genera docs/<LEG>_<YYYY>_<MM>.json
con las votaciones procesadas, listas para el HTML.

También lee diputados/diputados_*.json (generados por
descargar_diputados.py) y produce docs/escanos.json con
los escaños oficiales por legislatura.

Uso:
  python construir_datos.py            # todas las legislaturas
  python construir_datos.py XV XIV     # solo esas
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import zipfile, json, re, sys, unicodedata
from datetime import date
from pathlib import Path

VOTACIONES_DIR = Path("votaciones")
DIPUTADOS_DIR  = Path("diputados")
DATOS_DIR      = Path("docs")

# ── Código de grupo (votaciones) → party id ───────────────
GRUPO_META = {
    'GP':              'pp',
    'GS':              'psoe',
    'GVOX':            'vox',
    'GSUMAR':          'sumar',
    'GR':              'erc',
    'GJxCAT':          'junts',
    'GEH Bildu':       'bildu',
    'GV (EAJ-PNV)':   'pnv',
    'GMx':             'otros',
    'GUP-EC-GC':       'podemos',
    'GCUP-EC-GC':      'podemos',
    'GCs':             'ciudadanos',
    'GCiudadanos':     'ciudadanos',
    'GPlu':            'plural',
    'gplu':            'plural',
    'GPLU':            'plural',
    'GDL':             'pdecat',
    'GC-D':            'pdecat',
    'GCUP-EC-EM':      'podemos',
    'GER':             'erc',
    'GIU':             'iu',
    'GIU-ICV-EUiA-CHA':'iu',
    'GCiU':            'ciu',
    'GCIU-U':          'ciu',
    'GUPyD':           'upyd',
    'GUPYD':           'upyd',
    'GCUP':            'podemos',
    'GUpC':            'podemos',
    'GUPiX-En Comú Podem-En Marea': 'podemos',
    'GUEM':            'podemos',
    'GAMAIPC':         'amaipc',
    'GMIX':            'otros',
    'GMI':             'otros',
}

# ── Nombre completo (opendata diputados) → party id ───────
# Orden importa: más específico primero, más genérico al final.
GRUPO_NOMBRE_PID = [
    ('plurinacional sumar',          'sumar'),
    ('junts per catalunya',          'junts'),
    ('confederal de unidas',         'podemos'),
    ('unidas podemos',               'podemos'),
    ('unidos podemos',               'podemos'),
    ('en comu podem',                'podemos'),
    ('izquierda plural',             'iu'),
    ('izquierda unida',              'iu'),
    ('iniciativa per catalunya',     'iu'),
    ('convergencia i unio',          'ciu'),
    ('convergencia i unio',          'ciu'),
    ('democracia i llibertat',       'pdecat'),
    ('ciudadanos',                   'ciudadanos'),
    ('esquerra republicana',         'erc'),
    ('republicano',                  'erc'),
    ('union progreso y democracia',  'upyd'),
    ('euskal herria bildu',          'bildu'),
    ('bildu',                        'bildu'),
    ('vasco (eaj-pnv)',              'pnv'),
    ('eaj-pnv',                      'pnv'),
    ('vox',                          'vox'),
    ('socialista',                   'psoe'),
    ('popular en el congreso',       'pp'),
    ('partido popular',              'pp'),
    ('plural',                       'plural'),
    ('mixto',                        'otros'),
    ('popular',                      'pp'),
]


def _norm(s):
    return unicodedata.normalize('NFD', s.lower()).encode('ascii', 'ignore').decode()


def nombre_to_pid(nombre_grupo):
    n = _norm(nombre_grupo)
    for substr, pid in GRUPO_NOMBRE_PID:
        if _norm(substr) in n:
            return pid
    return 'otros'


def infer_legislatura(fecha_str):
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


def infer_tipo(titulo):
    a = titulo.lower()
    if 'proyecto de ley' in a:                                                    return 'Proyecto de ley'
    if 'proposición de ley orgánica' in a or 'proposicion de ley organica' in a: return 'Proposición de ley orgánica'
    if 'proposición de ley' in a or 'proposicion de ley' in a:                   return 'Proposición de ley'
    if 'real decreto-ley' in a or 'decreto-ley' in a or 'convalidación' in a:    return 'Convalidación decreto'
    if 'investidura' in a:                                                        return 'Investidura'
    if 'moción de censura' in a:                                                  return 'Moción de censura'
    if 'proposición no de ley' in a:                                              return 'Proposición no de ley'
    if 'moción' in a:                                                             return 'Moción'
    if 'presupuesto' in a:                                                        return 'Presupuestos'
    if 'enmienda' in a:                                                           return 'Enmienda'
    return 'Votación'


MONTHS = ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
          'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


def format_fecha(fecha_str):
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', fecha_str or '')
    if not m:
        return fecha_str or ''
    return f"{int(m[1])} {MONTHS[int(m[2])]} {m[3]}"


def normalize_voto(voto):
    v = _norm(voto or '')
    if v == 'si':               return 'af'
    if v == 'no':               return 'ec'
    if v.startswith('abstenc'): return 'ab'
    return 'nv'


next_id = [0]


def parse_votacion(data, filename):
    try:
        info   = data.get('informacion', {})
        totals = data.get('totales', {})
        vots   = data.get('votaciones', [])

        fecha  = info.get('fecha', '')
        titulo = (info.get('textoExpediente') or
                  info.get('tituloSubGrupo') or
                  filename.replace('.json', ''))
        subtit = ' · '.join(filter(None, [
            info.get('titulo'),
            info.get('tituloSubGrupo'),
            info.get('textoSubGrupo'),
        ]))

        raw_grupos = {}
        votos_ind  = {}
        votos_agg  = {}

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
            'id':                next_id[0],
            'legislatura':       infer_legislatura(fecha),
            '_rawGrupos':        raw_grupos,
            'votosIndividuales': votos_ind,
            'dedupKey':          f"{sesion}-{num_v}",
            'groupKey':          f"{sesion}-{(info.get('textoExpediente') or '')[:80]}-{info.get('textoSubGrupo') or ''}",
            'sesionNum':         sesion,
            'numVotacion':       num_v,
            'fecha':             format_fecha(fecha),
            'tipo':              infer_tipo(titulo),
            'titulo':            titulo,
            'descripcion':       subtit or titulo,
            'votRef':            f"Sesión {sesion or '?'}, votación {num_v or '?'}",
            'aprobada':          af > ec,
            'votos':             votos_agg,
            'source':            'repo',
        }
    except Exception as e:
        print(f"    ⚠ parse error {filename}: {e}")
        return None


# ── Build escanos.json ─────────────────────────────────────
def build_escanos():
    """
    Lee diputados/diputados_<LEG>.json y cuenta escaños únicos
    por partido. Devuelve {"XV": {"pp": 137, ...}, "XIV": {...}}
    """
    if not DIPUTADOS_DIR.exists():
        return {}

    escanos = {}
    for path in sorted(DIPUTADOS_DIR.glob("diputados_*.json")):
        leg = path.stem.replace("diputados_", "")
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"  ⚠ Error leyendo {path.name}: {e}")
            continue

        counts = {}
        for dip in data:
            grupo = dip.get('GRUPOPARLAMENTARIO') or dip.get('grupo', '')
            if not grupo:
                continue
            pid = nombre_to_pid(grupo)
            counts[pid] = counts.get(pid, 0) + 1

        if counts:
            escanos[leg] = counts
            total = sum(counts.values())
            top = sorted(counts.items(), key=lambda x: -x[1])[:4]
            top_str = ', '.join(f"{p}:{n}" for p, n in top)
            print(f"  {leg:15s}  {total} diputados  [{top_str} …]")

    return escanos


# ── Process one legislature ────────────────────────────────
def build_legislatura(leg):
    src = VOTACIONES_DIR / leg
    DATOS_DIR.mkdir(exist_ok=True)

    existing = {}
    for chunk in sorted(DATOS_DIR.glob(f"{leg}_*.json")):
        try:
            for v in json.loads(chunk.read_text(encoding='utf-8')):
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

    MONTH_NUM = {m: f"{i:02d}" for i, m in enumerate(
        ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
         'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'], 1)}
    by_chunk = {}
    for v in existing.values():
        parts = (v.get('fecha') or '').split()
        if len(parts) == 3:
            _, mes, year = parts
            key = f"{year}_{MONTH_NUM.get(mes, '00')}"
        else:
            key = 'unknown'
        by_chunk.setdefault(key, []).append(v)

    written_chunks = []
    for chunk_key, vots in sorted(by_chunk.items()):
        vots.sort(
            key=lambda v: (v.get('sesionNum') or 0, v.get('numVotacion') or 0),
            reverse=True,
        )
        chunk_path = DATOS_DIR / f"{leg}_{chunk_key}.json"
        chunk_path.write_text(
            json.dumps(vots, ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8',
        )
        size_mb = chunk_path.stat().st_size / 1_000_000
        written_chunks.append(chunk_path.stem)
        print(f"    {chunk_path.name}: {len(vots)} votaciones ({size_mb:.1f} MB)")

    print(f"  {leg}: {nuevos} nuevas  →  {len(existing)} total  ({len(written_chunks)} chunks)")
    return nuevos


# ── Main ───────────────────────────────────────────────────
def main():
    DATOS_DIR.mkdir(exist_ok=True)

    # 1. Escaños oficiales desde diputados/
    print("📊  Construyendo escanos.json …")
    escanos = build_escanos()
    if escanos:
        (DATOS_DIR / 'escanos.json').write_text(
            json.dumps(escanos, ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8',
        )
        print(f"  ✓  docs/escanos.json → {len(escanos)} legislaturas\n")
    else:
        print("  ⚠  No se encontraron archivos en diputados/ — omitiendo escanos.json\n")

    # 2. Votaciones por legislatura
    legs = sys.argv[1:] or [
        p.name for p in sorted(VOTACIONES_DIR.iterdir()) if p.is_dir()
    ]
    total = 0
    for leg in legs:
        if not (VOTACIONES_DIR / leg).exists():
            print(f"  ⚠ No existe votaciones/{leg}/")
            continue
        total += build_legislatura(leg)

    # 3. index.json — lista todos los chunks (sin escanos ni index)
    available = sorted(
        p.stem for p in DATOS_DIR.glob("*.json")
        if p.stem not in ('index', 'escanos')
    )
    (DATOS_DIR / 'index.json').write_text(
        json.dumps(available, ensure_ascii=False),
        encoding='utf-8',
    )
    print(f"\nTotal nuevas votaciones: {total}")
    print(f"docs/index.json → {len(available)} chunks")


if __name__ == '__main__':
    main()
