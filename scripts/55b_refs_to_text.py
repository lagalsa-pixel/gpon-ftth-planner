# -*- coding: utf-8 -*-
# Task 48: конвертация скачанных статей в чистый текст для изучения
import json, re, os, html

SRC = '/home/z/my-project/work/ref_materials'
FILES = ['01_foxes_xpon.json', '02_netsol.json', '03_donntu.json',
         '05_prorostelecom.json', '06_begemot.json']

def clean(h):
    h = re.sub(r'<script[^>]*>.*?</script>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<style[^>]*>.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<!--.*?-->', ' ', h, flags=re.S)
    # сохраняем структуру заголовков/абзацев/списков
    h = re.sub(r'<(h[1-6])[^>]*>', '\n\n## ', h, flags=re.I)
    h = re.sub(r'</h[1-6]>', '\n', h, flags=re.I)
    h = re.sub(r'<(p|div|li|tr|br)[^>]*>', '\n', h, flags=re.I)
    h = re.sub(r'<td[^>]*>', ' | ', h, flags=re.I)
    h = re.sub(r'<[^>]+>', '', h)
    h = html.unescape(h)
    h = re.sub(r'[ \t]+', ' ', h)
    h = re.sub(r'\n[ \t]+', '\n', h)
    h = re.sub(r'\n{3,}', '\n\n', h)
    return h.strip()

for f in FILES:
    p = os.path.join(SRC, f)
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    data = d.get('data', d)
    title = data.get('title', '')
    h = data.get('html') or ''
    t = clean(h)
    # отбрасываем хвосты unrelated (навигация/футер): обрезаем по последнему содержательному блоку
    out = os.path.join(SRC, f.replace('.json', '.txt'))
    with open(out, 'w') as fh:
        fh.write(f'TITLE: {title}\nURL: {data.get("url","")}\n{"="*70}\n{t}\n')
    print(f'{f}: {len(t)} символов -> {os.path.basename(out)}')
