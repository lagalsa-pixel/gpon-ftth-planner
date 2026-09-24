#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 50 (директива 23.09.2026): интуитивно понятные обозначения на картах зон.

Иконки для 48b_zone_maps_v4.py (и последующих рендеров):

  draw_olt_node(dr, x, y, R, ...)  — узел ЦУ / OLT: здание со шпилем-антенной,
      сигнальные дуги по бокам (читается как «станция/узел связи»),
      табличка-бейдж «OLT» на фасаде. Красный акцент сохранён (цвет корня).

  draw_orsh(dr, x, y, R, color, number) — зонный ОРШ: уличный шкаф — корпус
      цвета зоны с белой окантовкой, две дверцы с ручками, вентиляционные
      щели, цоколь-опора, крупный НОМЕР зоны на корпусе.

Обе функции рисуют в PIL ImageDraw; (x, y) — центр значка, R — масштаб
(половина габарита). Шрифты — DejaVu (есть в системе).
"""
import os
from PIL import ImageDraw

_FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
_FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

_font_cache = {}


def _font(sz):
    """DejaVu Bold кэшированный; sz<=0 -> None (нет текста)."""
    sz = int(round(sz))
    if sz <= 0:
        return None
    if sz not in _font_cache:
        from PIL import ImageFont
        _font_cache[sz] = ImageFont.truetype(_FB, sz)
    return _font_cache[sz]


# ----------------------------------------------------------------- ЦУ/OLT ---
def draw_olt_node(dr, x, y, R, *, plate_h=0.52, show_text=True):
    """Узел ЦУ/OLT. R — полу-габарит значка (~высота/2.6).

    Слои: гало -> тёмный бейдж со скруглением и двойной рамкой (красная
    внешняя + белая внутренняя) -> здание (крыша+корпус, белое) -> мачта
    с огоньком -> сигнальные дуги слева/справа -> красная табличка «OLT».
    """
    x, y, R = float(x), float(y), float(R)
    W2, H2 = 1.15 * R, 1.30 * R          # полуширина/полувысота бейджа
    # 0) гало (читаемость на любом снимке)
    dr.ellipse([x - 1.45 * R, y - 1.45 * R, x + 1.45 * R, y + 1.45 * R],
               fill=(0, 0, 0, 105))
    # 1) бейдж: красная внешняя рамка -> тёмный корпус -> белая внутренняя
    dr.rounded_rectangle([x - W2, y - H2, x + W2, y + H2], radius=0.28 * R,
                         fill=(224, 49, 49, 255))
    pad = max(1.0, 0.09 * R)
    dr.rounded_rectangle([x - W2 + pad, y - H2 + pad, x + W2 - pad, y + H2 - pad],
                         radius=0.22 * R, fill=(16, 24, 40, 252))
    pad2 = max(1.0, 0.16 * R)
    # 2) сигнальные дуги + мачта (верхняя зона бейджа)
    mast_top = y - 0.92 * R
    roof_apex = y - 0.28 * R
    arc_c = (x, mast_top)
    for rr_ in (0.34 * R, 0.58 * R):
        w = max(1, int(round(0.10 * R)))
        dr.arc([arc_c[0] - rr_, arc_c[1] - rr_, arc_c[0] + rr_, arc_c[1] + rr_],
               118, 242, fill=(255, 255, 255, 255), width=w)      # левая
        dr.arc([arc_c[0] - rr_, arc_c[1] - rr_, arc_c[0] + rr_, arc_c[1] + rr_],
               -62, 62, fill=(255, 255, 255, 255), width=w)       # правая
    mw = max(1, int(round(0.09 * R)))                              # мачта
    dr.line([(x, mast_top), (x, roof_apex)], fill=(255, 255, 255, 255), width=mw)
    dr.ellipse([x - 0.14 * R, mast_top - 0.14 * R, x + 0.14 * R, mast_top + 0.14 * R],
               fill=(255, 120, 90, 255))                           # огонёк
    # 3) здание: крыша + корпус (белые, тёмная дверь)
    hw, roof_base = 0.52 * R, y + 0.10 * R
    dr.polygon([(x, roof_apex), (x - hw, roof_base), (x + hw, roof_base)],
               fill=(245, 248, 252, 255))
    body_top, body_bot = roof_base, y + (0.90 - plate_h) * R + 0.06 * R
    dr.rectangle([x - 0.46 * R, body_top, x + 0.46 * R, body_bot],
                 fill=(245, 248, 252, 255))
    dr.rectangle([x - 0.11 * R, body_bot - 0.34 * R, x + 0.11 * R, body_bot],
                 fill=(16, 24, 40, 255))                           # дверь
    # 4) табличка «OLT»
    if show_text:
        ph = plate_h * R
        pl_top, pl_bot = y + 0.90 * R - ph, y + 0.90 * R
        dr.rounded_rectangle([x - 0.82 * R, pl_top, x + 0.82 * R, pl_bot],
                             radius=0.10 * R, fill=(224, 49, 49, 255),
                             outline=(255, 255, 255, 255), width=max(1, int(0.05 * R)))
        f = _font(0.40 * R)
        if f is not None:
            tb = dr.textbbox((0, 0), 'OLT', font=f)
            dr.text((x - (tb[2] - tb[0]) / 2 - tb[0], pl_top + (ph - (tb[3] - tb[1])) / 2 - tb[1]),
                    'OLT', font=f, fill=(255, 255, 255, 255))


# -------------------------------------------------------------------- ОРШ ---
def draw_orsh(dr, x, y, R, color, number):
    """Зонный ОРШ — уличный шкаф. R — полу-габарит по ширине (~w/1.5).

    Слои: тень -> цоколь -> корпус (цвет зоны, белая окантовка) ->
    вентиляционные щели -> линия дверец + ручки -> крупный НОМЕР зоны.
    """
    x, y, R = float(x), float(y), float(R)
    col = tuple(color[:3]) + (255,)
    w2, h2 = 0.75 * R, 1.08 * R                 # полуширина/полувысота корпуса
    # 0) тень (лёгкое смещение вправо-вниз)
    dr.rounded_rectangle([x - w2 + 0.10 * R, y - h2 + 0.12 * R, x + w2 + 0.10 * R,
                          y + h2 + 0.12 * R], radius=0.12 * R, fill=(0, 0, 0, 95))
    # 1) цоколь-опора
    dr.rectangle([x - 0.55 * R, y + h2 - 0.02 * R, x + 0.55 * R, y + h2 + 0.20 * R],
                 fill=(28, 30, 36, 255))
    # 2) корпус: тёмная внешняя окантовка -> цвет зоны -> белая рамка
    dr.rounded_rectangle([x - w2, y - h2, x + w2, y + h2], radius=0.10 * R,
                         fill=(20, 22, 28, 255))
    p1 = max(1.0, 0.085 * R)
    dr.rounded_rectangle([x - w2 + p1, y - h2 + p1, x + w2 - p1, y + h2 - p1],
                         radius=0.08 * R, fill=col,
                         outline=(255, 255, 255, 255), width=max(1, int(0.075 * R)))
    # 3) вентиляционные щели (верх)
    sw = max(1, int(round(0.055 * R)))
    for k in range(3):
        yy = y - h2 + (0.24 + 0.13 * k) * R
        dr.line([(x - 0.44 * R, yy), (x + 0.44 * R, yy)], fill=(255, 255, 255, 235),
                width=sw)
    # 4) номер зоны — крупно, по центру верхней половины
    f = _font(0.62 * R)
    if f is not None and number is not None:
        txt = str(number)
        tb = dr.textbbox((0, 0), txt, font=f)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        cy = y - 0.30 * R
        dr.text((x - tw / 2 - tb[0], cy - th / 2 - tb[1]), txt, font=f,
                fill=(255, 255, 255, 255),
                stroke_width=max(1, int(0.055 * R)), stroke_fill=(15, 15, 15, 255))
    # 5) дверцы: линия раздела (нижняя половина) + ручки
    dl = max(1, int(round(0.05 * R)))
    dr.line([(x, y + 0.10 * R), (x, y + h2 - p1 - 0.04 * R)],
            fill=(255, 255, 255, 235), width=dl)
    hr = max(1.0, 0.055 * R)
    for hx in (x - 0.14 * R, x + 0.14 * R):
        dr.ellipse([hx - hr, y + 0.48 * R - hr, hx + hr, y + 0.48 * R + hr],
                   fill=(255, 255, 255, 255))


# ================================================================== Task 51 =
# Параллельные кабели на общих трассах + пучки дропов одной муфты к одному дому.
#
# Проблема: фидеры нескольких зон и магистраль идут по одним улицам и сейчас
# рисуются друг на друге (до 9 кабелей на общем стволе у ЦУ); дропы из одной
# муфты к соседним точкам дома тоже перекрываются.
#
# Решение: посегментная группировка кабелей по совпадению концов сегмента
# (квантование координат до 0.1 px) -> каждому кабелю своя «полоса» (lane)
# с межосевым промежутком width+gap; линии рисуются со сдвигом по нормали.
# На стыках сегментов с разным составом пучка — короткие «мостики».
# ----------------------------------------------------------------------------
import math
from collections import defaultdict


def _seg_key(a, b):
    """Ключ сегмента: нечувствителен к направлению, квантование 0.1 px."""
    p = (round(float(a[0]), 1), round(float(a[1]), 1))
    q = (round(float(b[0]), 1), round(float(b[1]), 1))
    return (p, q) if p <= q else (q, p)


def _shift_seg(a, b, off):
    """Сдвиг отрезка (a,b) на off px по нормали (право по ходу, y-вниз)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < 1e-9 or abs(off) < 1e-9:
        return (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))
    nx, ny = -dy / L * off, dx / L * off
    return (a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny)


def offset_polyline(pts, off):
    """Полилиния, смещённая на off px перпендикулярно ходу.

    Стыки сегментов — miter (пересечение смещённых прямых соседних
    сегментов) с ограничением 2.5*|off|; при почти параллельном стыке —
    усреднённая нормаль. Возвращает список (x, y).
    """
    if len(pts) < 2 or abs(off) < 1e-9:
        return [(float(p[0]), float(p[1])) for p in pts]
    P = [(float(p[0]), float(p[1])) for p in pts]
    out = [P[0]]
    for i in range(len(P) - 2):
        a, v, b = P[i], P[i + 1], P[i + 2]
        d1 = (v[0] - a[0], v[1] - a[1])
        d2 = (b[0] - v[0], b[1] - v[1])
        L1 = math.hypot(*d1)
        L2 = math.hypot(*d2)
        if L1 < 1e-9 or L2 < 1e-9:
            out.append(v)
            continue
        n1 = (-d1[1] / L1, d1[0] / L1)
        n2 = (-d2[1] / L2, d2[0] / L2)
        # пересечение прямых (a+n1*off)+t*d1 и (v+n2*off)+s*d2
        det = d1[0] * (-d2[1]) - d1[1] * (-d2[0])
        if abs(det) < 1e-9:
            out.append((v[0] + (n1[0] + n2[0]) / 2 * off,
                        v[1] + (n1[1] + n2[1]) / 2 * off))
            continue
        rx, ry = (v[0] + n2[0] * off) - (a[0] + n1[0] * off), \
                 (v[1] + n2[1] * off) - (a[1] + n1[1] * off)
        t = (rx * (-d2[1]) - ry * (-d2[0])) / det
        m = (a[0] + n1[0] * off + t * d1[0], a[1] + n1[1] * off + t * d1[1])
        base = (v[0] + (n1[0] + n2[0]) / 2 * off, v[1] + (n1[1] + n2[1]) / 2 * off)
        if math.hypot(m[0] - base[0], m[1] - base[1]) > 2.5 * abs(off):
            m = base
        out.append(m)
    out.append(P[-1])
    # сдвиг концов (первая/последняя точки тоже уходят по нормали крайних сегментов)
    p0, q0 = _shift_seg(P[0], P[1], off)
    out[0] = p0
    pe, qe = _shift_seg(P[-2], P[-1], off)
    out[-1] = qe
    return out


def _dashed_polyline(dr, pts, fill, width, phase, dash, gap):
    """Пунктир по полилинии с начальной фазой phase (px)."""
    if len(pts) < 2:
        return
    seg = float(dash + gap)
    g = float(phase) % seg if seg > 0 else 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1e-9:
            continue
        t0 = 0.0
        pos = 0.0
        while pos < L:
            if g >= dash:                      # в пробеле
                rem = seg - g
                step = min(rem, L - pos)
                g += step
                pos += step
                if g >= seg - 1e-9:
                    g -= seg
                continue
            run = min(dash - g, L - pos)       # штрих
            t1 = t0 + run / L
            dr.line([(x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0),
                     (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1)],
                    fill=fill, width=width)
            t0 = t1
            g += run
            pos += run
            if g >= dash - 1e-9:
                # сразу пробел (для простоты — до конца пробела на месте)
                rem = min(gap, L - pos)
                pos += rem
                t0 = pos / L
                g = (g + rem)
                if g >= seg - 1e-9:
                    g -= seg


def edge_chains(segs):
    """Разбиение отрезков в максимальные цепочки (пути без ветвлений).

    segs: [(p, q), ...]; совпадение узлов — по квантованию _seg_key (0.1 px).
    Возвращает [[(x, y), ...], ...] — полилинии для отрисовки со сдвигом:
    внутри цепочки стыки сегментов сглаживаются «мостиками»/miter.
    """
    if not segs:
        return []
    key = lambda p: (round(float(p[0]), 1), round(float(p[1]), 1))
    adj = defaultdict(set)          # node -> set(ребро id)
    epts = []                       # (kp, kq, p_src, q_src): узел — квант,
    used_pts = []                   # но координаты в цепочке — ИСХОДНЫЕ
    for i, (p, q) in enumerate(segs):
        kp, kq = key(p), key(q)
        if kp == kq:
            continue
        epts.append((kp, kq, (float(p[0]), float(p[1])), (float(q[0]), float(q[1]))))
        ei = len(epts) - 1
        adj[kp].add(ei)
        adj[kq].add(ei)
    used = [False] * len(epts)
    chains = []
    # стартуем с рёбер, у которых конец имеет степень 1 (листья), затем прочие
    def start_order():
        leaf_first, other = [], []
        for i, (kp, kq, _, _) in enumerate(epts):
            if len(adj[kp]) == 1 or len(adj[kq]) == 1:
                leaf_first.append(i)
            else:
                other.append(i)
        return leaf_first + other

    def src_of(kp, kq, p_src, q_src, want):
        """исходные координаты узла want (по кванту)."""
        return p_src if want == kp else q_src

    for e0 in start_order():
        if used[e0]:
            continue
        used[e0] = True
        kp, kq, p_src, q_src = epts[e0]
        chain = [kp, kq]
        src = {kp: p_src, kq: q_src}
        # тянем влево
        while True:
            end = chain[0]
            nxt = next((e for e in adj[end] if not used[e]), None)
            if nxt is None or len(adj[end]) > 2:
                break
            used[nxt] = True
            a, b, pa, pb = epts[nxt]
            other = b if a == end else a
            chain.insert(0, other)
            src[other] = pb if a == end else pa
            if len(adj[chain[0]]) > 2:
                break
        # тянем вправо
        while True:
            end = chain[-1]
            nxt = next((e for e in adj[end] if not used[e]), None)
            if nxt is None or len(adj[end]) > 2:
                break
            used[nxt] = True
            a, b, pa, pb = epts[nxt]
            other = b if a == end else a
            chain.append(other)
            src[other] = pb if a == end else pa
            if len(adj[chain[-1]]) > 2:
                break
        if len(chain) >= 2:
            chains.append([src[c] for c in chain])
    return chains


def draw_cables_bundled(dr, cables, *, gap=4.5, dash=30.0, gap_d=22.0,
                         dump_path=None):
    """Кабели, разводимые параллельными линиями на общих сегментах трассы.

    cables: список dict с ключами:
      pts    — [(x, y), ...] полилиния в px базовой карты;
      color  — RGBA, width — толщина линии, px;
      dashed — пунктир (default False), phase — сдвиг фазы пунктира, px;
      sort_key — стабильный порядок «полос» в пучке (меньше — левее).

    Совпадающие сегменты (концы совпали с точностью 0.1 px) образуют пучок:
    полосы центрируются, межосевой промежуток = max(width)+gap. Стыки
    сегментов одного кабеля с разными смещениями соединяются «мостиками».
    """
    if not cables:
        return
    segs = defaultdict(list)
    for ci, c in enumerate(cables):
        pts = c['pts']
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) + abs(a[1] - b[1]) < 1e-9:
                continue
            segs[_seg_key(a, b)].append(ci)
    order = sorted(range(len(cables)),
                   key=lambda i: cables[i].get('sort_key', i))
    rank = {ci: r for r, ci in enumerate(order)}
    lane_off = {}
    for k, cis in segs.items():
        cis = sorted(set(cis), key=lambda ci: rank[ci])
        n = len(cis)
        pitch = max(cables[ci]['width'] for ci in cis) + float(gap)
        for lane, ci in enumerate(cis):
            lane_off[(k, ci)] = (lane - (n - 1) / 2.0) * pitch
    if dump_path:
        try:
            import json
            dump = dict(
                gap=float(gap),
                cables=[dict(pts=[list(map(float, p)) for p in c['pts']],
                             color=list(c['color']), width=int(c['width']),
                             dashed=bool(c.get('dashed')),
                             phase=float(c.get('phase', 0.0)),
                             sort_key=c.get('sort_key')) for c in cables],
                segs={f'{k[0][0]},{k[0][1]};{k[1][0]},{k[1][1]}':
                      [int(ci) for ci in cis] for k, cis in segs.items()},
                lane_off={f'{k[0][0]},{k[0][1]};{k[1][0]},{k[1][1]}|{ci}': off
                          for (k, ci), off in lane_off.items()})
            tmp = dump_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(dump, f)
            os.replace(tmp, dump_path)
        except Exception:
            pass
    for ci, c in enumerate(cables):
        pts = c['pts']
        col, wd = c['color'], int(c['width'])
        prev_q = None
        acc = 0.0
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) + abs(a[1] - b[1]) < 1e-9:
                continue
            k = _seg_key(a, b)
            off = lane_off.get((k, ci), 0.0)
            p, q = _shift_seg(a, b, off)
            if prev_q is not None and math.hypot(p[0] - prev_q[0],
                                                 p[1] - prev_q[1]) > 0.5:
                dr.line([prev_q, p], fill=col, width=wd)   # мостик
            if c.get('dashed'):
                _dashed_polyline(dr, [p, q], col, wd,
                                 acc + float(c.get('phase', 0.0)),
                                 c.get('dash', dash), c.get('gap_d', gap_d))
            else:
                dr.line([p, q], fill=col, width=wd)
            acc += math.hypot(b[0] - a[0], b[1] - a[1])
            prev_q = q


def draw_drops_bundled(dr, drops, *, gap=3.2, width=2, color=None,
                       home_r_px=30.0):
    """Дропы с разводкой пучков «одна муфта -> один дом».

    drops: список dict(pts=[(x, y), ...], coupler=<id муфты>, color, width).
    Конечная точка pts[-1] — точка ДХ. Дропы одной муфты с близкими
    конечными точками (<= home_r_px, транзитивно) считаются уходящими
    к одному дому и рисуются параллельными линиями со сдвигом по нормали
    (начало — точно у муфты, заход — точно в точку ДХ).
    """
    if not drops:
        return
    by_c = defaultdict(list)
    for d in drops:
        by_c[d.get('coupler')].append(d)
    for _, ds in by_c.items():
        # кластеры конечных точек (транзитивная близость)
        ends = [d['pts'][-1] for d in ds]
        parent = list(range(len(ds)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(ds)):
            for j in range(i + 1, len(ds)):
                if math.hypot(ends[i][0] - ends[j][0],
                              ends[i][1] - ends[j][1]) <= home_r_px:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[ri] = rj
        clusters = defaultdict(list)
        for i in range(len(ds)):
            clusters[find(i)].append(ds[i])
        for cl in clusters.values():
            n = len(cl)
            if n <= 1:
                d = cl[0]
                col = d.get('color') or color
                wd = int(d.get('width', width))
                if len(d['pts']) >= 2:
                    dr.line(d['pts'], fill=col, width=wd)
                continue
            pitch = width + float(gap)
            for i, d in enumerate(sorted(cl, key=lambda d: (d['pts'][-1][0],
                                                            d['pts'][-1][1]))):
                off = (i - (n - 1) / 2.0) * pitch
                pts = d['pts']
                col = d.get('color') or color
                wd = int(d.get('width', width))
                if len(pts) >= 3:
                    body = offset_polyline(pts[:-1], off)
                    path = [pts[0]] + body[1:] + [pts[-1]]
                elif len(pts) == 2:
                    mid = ((pts[0][0] + pts[1][0]) / 2.0,
                           (pts[0][1] + pts[1][1]) / 2.0)
                    p, _ = _shift_seg(pts[0], pts[1], off)
                    path = [pts[0], (mid[0] + (p[0] - pts[0][0]),
                                     mid[1] + (p[1] - pts[0][1])), pts[1]]
                else:
                    continue
                dr.line(path, fill=col, width=wd, joint='curve')


# --------------------------------------------------------------- самопроверка
if __name__ == '__main__':
    """Отрисовка образцов иконок: work/symbology_preview.png."""
    from PIL import Image, ImageFont
    import math
    S = 3.2                                    # как на карте ~S(1)
    W, H = int(560 * S / 3.2), int(420 * S / 3.2)
    im = Image.new('RGB', (W, H), (92, 104, 88))          # «снимок»-имитация
    dr = ImageDraw.Draw(im, 'RGBA')
    # сетка «улиц» для контекста
    for gx in range(0, W, 90):
        dr.line([(gx, 0), (gx, H)], fill=(120, 120, 110), width=6)
    for gy in range(0, H, 90):
        dr.line([(0, gy), (W, gy)], fill=(120, 120, 110), width=6)
    demo = [(255, 255, 255, 255), (30, 120, 60, 255), (60, 60, 70, 255)]
    dr.rectangle([0, 0, W, H], fill=(96, 108, 88, 60))
    # ЦУ/OLT крупно + ОРШ разного размера/цвета
    draw_olt_node(dr, W * 0.30, H * 0.32, 17 * S / 3.2)
    draw_orsh(dr, W * 0.62, H * 0.30, 15 * S / 3.2, (25, 113, 194), 1)
    draw_orsh(dr, W * 0.80, H * 0.30, 15 * S / 3.2, (47, 158, 68), 2)
    draw_orsh(dr, W * 0.30, H * 0.72, 15 * S / 3.2, (240, 140, 0), 3)
    draw_orsh(dr, W * 0.52, H * 0.72, 15 * S / 3.2, (156, 54, 181), 12)
    draw_olt_node(dr, W * 0.76, H * 0.74, 12 * S / 3.2)
    fr = ImageFont.truetype(_FR, 16)
    dr.text((12, H - 40), 'образцы: ЦУ·OLT (здание+антенна+бейдж OLT), ОРШ (шкаф с номером зоны)',
            font=fr, fill=(255, 255, 255))
    out = os.path.join(os.path.dirname(__file__), '..', 'work', 'symbology_preview.png')
    im.save(out)
    print('образцы ->', os.path.abspath(out))
