import json, csv, sys
from pathlib import Path

dataset = Path('Dataset')
out = []

def pr(*args):
    s = ' '.join(str(a) for a in args)
    out.append(s)
    print(s)

# ── GA4 ──────────────────────────────────────────────────────────────────────
p = dataset / 'ga4_clickstream.json'
with p.open('r', encoding='utf-8') as f:
    obj = json.load(f)
pr('=== GA4 TOP KEYS ===', list(obj.keys()))
for k, v in obj.items():
    if isinstance(v, list):
        pr(f'  LIST KEY={k!r} len={len(v)}')
        if v and isinstance(v[0], dict):
            pr(f'  EVENT KEYS: {list(v[0].keys())}')
            pr(f'  SAMPLE: {dict(list(v[0].items())[:10])}')
        break

# ── HOTJAR ───────────────────────────────────────────────────────────────────
pr('\n=== HOTJAR ===')
p2 = dataset / 'hotjar.json'
with p2.open('r', encoding='utf-8') as f:
    obj2 = json.load(f)
pr('TYPE:', type(obj2).__name__)
if isinstance(obj2, dict):
    pr('TOP KEYS:', list(obj2.keys()))
    for k, v in obj2.items():
        if isinstance(v, list):
            pr(f'  LIST KEY={k!r} len={len(v)}')
            if v and isinstance(v[0], dict):
                pr(f'  KEYS: {list(v[0].keys())}')
                pr(f'  SAMPLE: {dict(list(v[0].items())[:10])}')
            break
elif isinstance(obj2, list):
    pr('LEN:', len(obj2))
    if obj2 and isinstance(obj2[0], dict):
        pr('KEYS:', list(obj2[0].keys()))
        pr('SAMPLE:', dict(list(obj2[0].items())[:10]))

# ── ALL_SOURCES_BUNDLE ───────────────────────────────────────────────────────
pr('\n=== ALL_SOURCES_BUNDLE ===')
p3 = dataset / 'all_sources_bundle.json'
with p3.open('r', encoding='utf-8') as f:
    obj3 = json.load(f)
pr('TYPE:', type(obj3).__name__)
if isinstance(obj3, dict):
    pr('TOP KEYS:', list(obj3.keys()))
    for k, v in obj3.items():
        pr(f'  {k!r}: {type(v).__name__}', f'len={len(v)}' if isinstance(v, list) else str(v)[:80])
        if isinstance(v, list) and v and isinstance(v[0], dict):
            pr(f'    ITEM KEYS: {list(v[0].keys())}')
            pr(f'    SAMPLE: {dict(list(v[0].items())[:10])}')
            break
elif isinstance(obj3, list):
    pr('LEN:', len(obj3))
    if obj3 and isinstance(obj3[0], dict):
        pr('KEYS:', list(obj3[0].keys()))
        pr('SAMPLE:', dict(list(obj3[0].items())[:10]))

# ── CSV ───────────────────────────────────────────────────────────────────────
pr('\n=== combined_signals_5k.csv ===')
p4 = dataset / 'combined_signals_5k.csv'
with p4.open('r', encoding='utf-8', errors='replace') as f:
    r = csv.DictReader(f)
    row = next(r, None)
    row2 = next(r, None)
if row:
    pr('COLUMNS:', list(row.keys()))
    pr('ROW1:', dict(list(row.items())[:15]))
    if row2:
        pr('ROW2:', dict(list(row2.items())[:15]))

# ── SURVEYS ──────────────────────────────────────────────────────────────────
pr('\n=== surveys.json ===')
p5 = dataset / 'surveys.json'
with p5.open('r', encoding='utf-8') as f:
    obj5 = json.load(f)
pr('TYPE:', type(obj5).__name__)
if isinstance(obj5, dict):
    pr('TOP KEYS:', list(obj5.keys()))
    for k, v in obj5.items():
        if isinstance(v, list) and v:
            pr(f'  LIST KEY={k!r} len={len(v)}')
            if isinstance(v[0], dict):
                pr(f'  KEYS: {list(v[0].keys())}')
                pr(f'  SAMPLE: {dict(list(v[0].items())[:10])}')
            break
elif isinstance(obj5, list):
    pr('LEN:', len(obj5))
    if obj5: pr('KEYS:', list(obj5[0].keys()) if isinstance(obj5[0],dict) else obj5[0])

Path('schema_report.txt').write_text('\n'.join(out), encoding='utf-8')
print('\nWrote schema_report.txt')
