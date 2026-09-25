# -*- coding: utf-8 -*-
"""
Шаг 38. Альбом карт зон ОРШ (схема D) в одном PDF <= 10 МБ.

Состав: титульный лист A3 (векторный текст, DejaVu Sans) + 6 карт full-bleed
(страница повторяет аспект изображения, длинная сторона 420 мм = A3).

Сжатие карт (rate control): даунсемпл LANCZOS длинной стороны до MAX_PX,
затем пер-страничный подбор JPEG quality под байтовый бюджет, выделенный
пропорционально сложности карты (опорный энкод q80). 4:2:0, baseline,
optimize=True; ReportLab встраивает JPEG-поток без перекодирования (DCTDecode).

Выход: download/Альбом_карт_зон_ОРШ_схема_D_ВКО.pdf
Запуск: python3 38_pdf_album.py
"""
import io
import json
import os
import time

from PIL import Image
from reportlab import rl_config
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

rl_config.useA85 = 0             # без ASCII85-обёртки JPEG-потоков (-25% объёма)
Image.MAX_IMAGE_PIXELS = None

BASE = '/home/z/my-project'
SRC = f'{BASE}/download/snp_vko'
TMP = f'{BASE}/work/pdf_album'
OUT = f'{BASE}/download/Альбом_карт_зон_ОРШ_схема_D_ВКО.pdf'

MAX_PX = 3200                 # длинная сторона, ~194 DPI при печати A3
REF_Q = 80                    # опорное качество для оценки сложности
Q_LO, Q_HI = 66, 86           # границы поиска quality
MAPS_BUDGET = 9.45e6          # байтов на 6 карт (запас: титул + структура PDF)
A3_LONG = 1190.55             # pt, 420 мм
A3_SHORT = 841.89             # pt, 297 мм

DBOOK = json.load(open(f'{BASE}/work/boq_decentral_data_v4.json', encoding='utf-8'))
DBY = {v['num']: v for v in DBOOK['villages']}

# ---------------------------------------------------------------- стили ----
FD = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FDB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
pdfmetrics.registerFont(TTFont('DejaVu', FD))
pdfmetrics.registerFont(TTFont('DejaVu-Bold', FDB))

BG = HexColor('#0A121E')
WHITE = HexColor('#F0F5FA')
MUTED = HexColor('#8FA3BC')
BODY = HexColor('#C9D6E6')
YELLOW = HexColor('#FFDC78')
DIV = HexColor('#22334D')
ROW = HexColor('#0F1B2D')
HEAD = HexColor('#12213A')
NUM = HexColor('#DCE6F2')


def fmt(n, nd=0):
    """1234567.8 -> '1 234 567,8' (русский формат)."""
    s = f'{n:,.{nd}f}'.replace(',', ' ').replace('.', ',')
    return s


# ================================================== A. RATE-CONTROL ENCODE ==
def downscale(path):
    """draft-декод + LANCZOS до MAX_PX по длинной стороне."""
    im = Image.open(path)
    w, h = im.size
    k = MAX_PX / max(w, h)
    if k >= 1.0:
        return im.convert('RGB')
    tw, th = max(1, round(w * k)), max(1, round(h * k))
    im.draft('RGB', (tw, th))            # DCT-доменное сокращение (2^k)
    return im.resize((tw, th), Image.LANCZOS, reducing_gap=3.0)


def enc(im, q):
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=q, subsampling=2, optimize=True)
    return buf.tell(), buf


def phase_a():
    os.makedirs(TMP, exist_ok=True)
    files = sorted(f for f in os.listdir(SRC) if f.endswith('.jpg'))
    print('A. Эталонный энкод q80 (оценка сложности)...', flush=True)
    refs, ims = [], []
    for f in files:
        im = downscale(os.path.join(SRC, f))
        n, _ = enc(im, REF_Q)
        refs.append(n)
        ims.append(im)
        print(f'   {f[:2]}: {im.size[0]}x{im.size[1]}  q{REF_Q} -> {n / 1e6:.2f} МБ',
              flush=True)
    total_ref = sum(refs)

    print('B. Распределение бюджета и подбор quality...', flush=True)
    params, used = [], 0
    for f, im, ref in zip(files, ims, refs):
        budget = MAPS_BUDGET * ref / total_ref
        lo, hi = Q_LO, Q_HI
        while lo < hi:                     # максимальный q, влезающий в бюджет
            mid = (lo + hi + 1) // 2
            n, _ = enc(im, mid)
            if n <= budget:
                lo = mid
            else:
                hi = mid - 1
        n, buf = enc(im, lo)
        out = os.path.join(TMP, f'{f[:2]}.jpg')
        with open(out, 'wb') as fh:
            fh.write(buf.getbuffer())
        used += n
        params.append({'file': f, 'out': out, 'q': lo, 'bytes': n,
                       'size': im.size})
        print(f'   {f[:2]}: бюджет {budget / 1e6:.2f} МБ -> q{lo}, {n / 1e6:.2f} МБ',
              flush=True)
    print(f'   Итого карты: {used / 1e6:.2f} МБ', flush=True)
    return params, used


def fit(text, font, size, max_w):
    """Размер шрифта с авто-уменьшением, чтобы строка влезала в max_w."""
    w = pdfmetrics.stringWidth(text, font, size)
    if w <= max_w:
        return size
    return max(8.5, size * max_w / w)


# ================================================== B. ТИТУЛЬНЫЙ ЛИСТ A3 ===
def title_page(c):
    W, H = A3_SHORT, A3_LONG
    c.setFillColor(BG)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    M = 70.0
    AW = W - 2 * M                   # доступная ширина 701.9 pt
    y = H - 96

    # верхняя надпись
    f = fit('ПРОЕКТ FTTH  ·  ВОСТОЧНО-КАЗАХСТАНСКАЯ ОБЛАСТЬ  ·  '
            'ГЛУБОКОВСКИЙ Р-Н И Г. РИДДЕР', 'DejaVu', 12.5, AW)
    c.setFont('DejaVu', f)
    c.setFillColor(MUTED)
    c.drawString(M, y, 'ПРОЕКТ FTTH  ·  ВОСТОЧНО-КАЗАХСТАНСКАЯ ОБЛАСТЬ  ·  '
                       'ГЛУБОКОВСКИЙ Р-Н И Г. РИДДЕР')

    # акцентная плашка
    y -= 44
    c.setFillColor(YELLOW)
    c.rect(M, y, 72, 7, stroke=0, fill=1)

    # заголовок
    y -= 62
    c.setFont('DejaVu-Bold', 58)
    c.setFillColor(WHITE)
    c.drawString(M, y, 'КАРТЫ ЗОН ОРШ')
    y -= 72
    c.setFillColor(YELLOW)
    c.drawString(M, y, 'СХЕМА D')

    # подзаголовок (3 строки, авто-подгонка)
    y -= 46
    subs = ('Децентрализованная структура: зонные ОРШ (сплиттеры 1:64)',
            'при едином узле OLT · шесть сельских населённых пунктов ВКО',
            '3 072 обслуживаемых домохозяйств · 36 зонных ОРШ + 6 ЦУ · ОРШ в центрах секторов, фидеры в границе НП')
    for s in subs:
        f = fit(s, 'DejaVu', 18.5, AW)
        c.setFont('DejaVu', f)
        c.setFillColor(BODY)
        c.drawString(M, y, s)
        y -= 27

    # разделитель
    y -= 16
    c.setStrokeColor(DIV)
    c.setLineWidth(1)
    c.line(M, y, W - M, y)

    # KPI-полоса: ширины ячеек пропорциональны содержимому
    kpis = [('6', 'сельских населённых пунктов'),
            ('3 072', 'домохозяйств (ДХ)'),
            ('36 + 6', 'зонных ОРШ + ЦУ (OLT)'),
            ('1 495,7 км', 'суммарного волокна')]
    nat = [max(pdfmetrics.stringWidth(n, 'DejaVu-Bold', 33),
               pdfmetrics.stringWidth(l, 'DejaVu', 12.5)) + 44
           for n, l in kpis]
    scale = AW / sum(nat)
    x = M
    for i, ((num, lab), nw) in enumerate(zip(kpis, nat)):
        c.setFont('DejaVu-Bold', 33)
        c.setFillColor(YELLOW)
        c.drawString(x, y - 78, num)
        c.setFont('DejaVu', 12.5)
        c.setFillColor(MUTED)
        c.drawString(x, y - 102, lab)
        if i:
            c.setStrokeColor(DIV)
            c.setLineWidth(1)
            c.line(x - 22, y - 66, x - 22, y - 112)
        x += nw * scale

    # содержание
    y -= 150
    c.setFont('DejaVu', 13.5)
    c.setFillColor(MUTED)
    c.drawString(M, y, 'С О Д Е Р Ж А Н И Е')
    y -= 34

    heads = ['№', 'Село', 'ДХ', 'Зон ОРШ\n+ ЦУ', 'Волокно,\nкм',
             'Магистраль,\nкм', 'Дроп,\nкм', 'Стр.']
    cols = [30, 168, 60, 96, 88, 104, 76, 40]      # = 662
    xs, x = [], M
    for cw in cols:
        xs.append(x)
        x += cw
    tw = sum(cols)

    # шапка таблицы
    c.setFillColor(HEAD)
    c.rect(M, y - 10, tw, 34, stroke=0, fill=1)
    c.setFont('DejaVu', 11)
    c.setFillColor(MUTED)
    for i, htxt in enumerate(heads):
        col_r = xs[i] + cols[i] - 7
        if i == 0:
            c.drawString(xs[i] + 7, y + 1, htxt)
        elif i == 1:
            c.drawString(xs[i] + 7, y + 1, htxt)
        else:
            for j, ln in enumerate(htxt.split('\n')):
                c.drawRightString(col_r, y + 4 - j * 12, ln)
    y -= 44

    # строки
    vs = DBOOK['villages']
    for r, v in enumerate(vs):
        if r % 2 == 0:
            c.setFillColor(ROW)
            c.rect(M, y - 9, tw, 36, stroke=0, fill=1)
        c.setFont('DejaVu-Bold', 15)
        c.setFillColor(WHITE)
        c.drawString(xs[0] + 7, y, v['num'])
        c.drawString(xs[1] + 7, y, v['name'])
        c.setFont('DejaVu', 14)
        c.setFillColor(NUM)
        vals = [fmt(v['dhx_served']), f"{v['n_zones']} + 1",
                fmt(v['fiber_km'], 1), fmt(v['cable_km_raw'], 1),
                fmt(v['drop_cable_km'], 1), str(r + 2)]
        for i, val in enumerate(vals, start=2):
            c.drawRightString(xs[i] + cols[i] - 7, y, val)
        y -= 36

    # итоговая строка
    t = DBOOK['totals']
    c.setStrokeColor(HexColor('#2C4160'))
    c.setLineWidth(1.2)
    c.line(M, y + 18, M + tw, y + 18)
    c.setFont('DejaVu-Bold', 14)
    c.setFillColor(YELLOW)
    c.drawString(xs[1] + 7, y, 'Итого по схеме D')
    totals = [fmt(t['dhx_served']), f"{t['n_zones']} + 6",
              fmt(t['fiber_km'], 1), fmt(t['cable_km_raw'], 1),
              fmt(t['drop_cable_km'], 1)]
    for i, val in enumerate(totals, start=2):
        c.drawRightString(xs[i] + cols[i] - 7, y, val)
    y -= 52

    # примечания (авто-подгонка ширины)
    c.setFillColor(HexColor('#7E93AC'))
    notes = (
        'Топология сетей, муфты и дропы соответствуют схемам A/B/C без '
        'изменений; меняется только размещение сплиттеров 1:64 (зонные ОРШ).',
        'Подложка карт — спутниковые снимки Google z18: Верхнеберезовка — '
        'мозаика, остальные сёла — обрезанные кадры пользователя.',
        'Полная ведомость материалов схемы D — в сводной таблице '
        '«Сводная_таблица_материалов_FTTH_ВКО_каскад.xlsx», лист «Схема D».',
        'Печать: длинная сторона страниц соответствует A3 (420 мм); '
        'растр ~194 DPI.')
    for line in notes:
        f = fit(line, 'DejaVu', 10.5, AW)
        c.setFont('DejaVu', f)
        c.drawString(M, y, line)
        y -= 17

    # колонтитул
    c.setFont('DejaVu', 11)
    c.setFillColor(MUTED)
    c.drawString(M, 52, 'сентябрь 2026 г.')
    c.drawRightString(W - M, 52, 'ВКО · 6 СНП · 3072 ДХ')


# ================================================== C. СБОРКА PDF ===========
def build(params):
    c = rl_canvas.Canvas(OUT, pagesize=(A3_SHORT, A3_LONG), pageCompression=1)
    c.setTitle('Альбом карт зон ОРШ — схема D (FTTH, ВКО)')
    c.setAuthor('Z.ai')
    c.setCreator('Z.ai')
    c.setSubject('Зоны ОРШ шести СНП ВКО — децентрализованная схема D '
                 'с единым узлом OLT (сплиттеры 1:64)')

    c.bookmarkPage('cover')
    c.addOutlineEntry('Титульный лист', 'cover', level=0)
    title_page(c)
    c.showPage()

    for p in params:
        v = DBY[p['file'][:2]]
        w, h = p['size']
        if w >= h:
            pw, ph = A3_LONG, A3_LONG * h / w
        else:
            pw, ph = A3_LONG * w / h, A3_LONG
        c.setPageSize((pw, ph))
        c.drawImage(p['out'], 0, 0, pw, ph)
        key = f"map{v['num']}"
        c.bookmarkPage(key)
        c.addOutlineEntry(f"{v['num']} · {v['name']}", key, level=0)
        c.showPage()
        dpi = max(w, h) / (A3_LONG / 72)
        print(f"   стр. {v['num']} {v['name']:<18} {w}x{h}px -> "
              f"{pw:.0f}x{ph:.0f} pt, ~{dpi:.0f} DPI", flush=True)

    c.save()
    return os.path.getsize(OUT)


def main():
    t0 = time.time()
    params, used = phase_a()
    sz = build(params)
    print(f'\nГотово: {OUT}')
    print(f'Размер: {sz / 1e6:.2f} МБ (карты {used / 1e6:.2f} МБ), '
          f'7 стр., [{time.time() - t0:.0f} с]')
    assert sz <= 10e6, 'PDF превысил 10 МБ!'


if __name__ == '__main__':
    main()
