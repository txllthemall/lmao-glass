import json,sys
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
EXPECTED=['telegram','discord','github','google_play','pinterest','kaspi','2gis','revanced','gamehub']
errors=[]
meta=json.loads((ROOT/'android-pack/launcher-mappings/icons.json').read_text())
prov_path=ROOT/'artwork/official/provenance.json'
if not prov_path.exists():
    errors.append('missing artwork/official/provenance.json; run scripts/sync_official_assets.py')
    provenance={}
else:
    provenance=json.loads(prov_path.read_text())

for s in EXPECTED:
    p=ROOT/f'generated/icons/{s}_1024.png'
    if not p.exists(): errors.append(f'missing {p}')
    else:
        im=Image.open(p).convert('RGBA')
        if im.size!=(1024,1024): errors.append(f'{s}: wrong size {im.size}')
        if im.getchannel('A').getbbox() is None: errors.append(f'{s}: empty alpha')
    for q in [ROOT/f'android-pack/src/main/res/mipmap-anydpi-v26/ic_{s}.xml',ROOT/f'android-pack/src/main/res/mipmap-anydpi-v33/ic_{s}.xml',ROOT/f'android-pack/src/main/res/drawable/ic_{s}_monochrome.png']:
        if not q.exists(): errors.append(f'missing {q}')
    if s not in meta or not meta[s].get('packages'): errors.append(f'{s}: missing package mapping')
    if s not in provenance:
        errors.append(f'{s}: missing official-source provenance')
    else:
        rec=provenance[s]
        local=ROOT/rec.get('local_master','')
        if not local.exists(): errors.append(f'{s}: provenance master missing: {local}')
        if rec.get('geometry_modifications')!='NONE': errors.append(f'{s}: source geometry was modified')
        if not rec.get('source_url'): errors.append(f'{s}: missing source URL')
    source=(meta.get(s,{}).get('source') or '').lower()
    if 'simple icons' in source or 'reconstruction' in source:
        errors.append(f'{s}: launcher metadata still references rejected surrogate artwork')

for q in [ROOT/'generated/contact-sheets/qa-grid.png',ROOT/'generated/contact-sheets/source-geometry.png']:
    if not q.exists(): errors.append(f'missing {q}')

if errors:
    print('\n'.join(errors)); sys.exit(1)
print('QA PASS:',len(EXPECTED),'icons; official-source provenance, renders, adaptive XML and geometry sheet present')
