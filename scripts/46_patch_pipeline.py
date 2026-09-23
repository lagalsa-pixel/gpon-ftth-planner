# -*- coding: utf-8 -*-
"""Патч пайплайна ftth_pipeline.py: стадия refine_households v2 -> v3 (Task 46).

1) Заголовочный комментарий стадии 2b + константы HH2_*.
2) Функция roof_split_info -> двухканальная (цвет вспомогателен, центр фасада,
   сопоставимость частей, шов/стык).
3) Промпт _hh2_vlm_nproperties -> критерии пользователя (забор перпендикулярно
   фасаду у центра; пристройка = меньший прямоугольник — не владение) + гейт.
"""
import re
import io

P = '/home/z/my-project/download/ftth_pipeline/ftth_pipeline.py'
src = io.open(P, encoding='utf-8').read()

# ---------- 1) заголовок стадии + константы ----------
i = src.index('# СТАДИЯ 2b')
line_start = src.rfind('\n', 0, i) + 1          # начало строки '# СТАДИЯ 2b'
sep_start = src.rfind('\n', 0, line_start - 1) + 1  # начало строки '# ====' перед ней
head_start = sep_start
const_end = src.index('HH2_SANE_FPF = (40.0, 3500.0)') + len('HH2_SANE_FPF = (40.0, 3500.0)')
old_block = src[head_start:const_end]

new_block = '''# ============================================================================
# СТАДИЯ 2b: уточнение детекции ДХ (v3) — сблокированные дома и многоэтажки
# ============================================================================
# Кейс (ВКО, Пригородное): OSM-полигон покрывает ДВА сблокированных дома
# с разными крышами, разделённых межевым забором; кластеризация усадеб
# eps=16 м дополнительно склеивает соседние дома в одно ДХ.
#
# Критерии пользователя (Task 46, скорректированное «условие поиска по крышам»):
# различие ЦВЕТА крыш НЕ достаточно — пристройка тоже другого цвета, но
# прямоугольник МЕНЬШЕГО размера, отличной формы в плане. Признаки двух
# владений: (1) увеличенные размеры; (2) ограждение, примыкающее к фасаду
# ПЕРПЕНДИКУЛЯРНО ближе к его ЦЕНТРУ; (3) общая кровля одинаковой формы,
# иногда двух цветов.
#
# A) два канала сплита полигона (линия раздела — только у центра фасада,
#    t=0.38..0.62, обе оси; «увеличенные размеры»: bbox >= 165 м²,
#    длинная сторона >= 12.5 м, части >= 36 м²):
#    A1 «двухцветная пара»: хроматический сплит (dE_ab >= 8.5 И (dE >= 18
#       ИЛИ нейтральная+окрашенная ИЛИ оттенки >= 25°)) при СОПОСТАВИМЫХ
#       частях (ratio >= 0.35 — анти-пристройка);
#    A2 «одноцветная пара»: геометрический центр-сплит — только при
#       найденном ШВЕ/СТЫКЕ кровель (градиент яркости на линии раздела
#       покрывает >= 45% среза) — CV-заместитель признака ограждения;
# B) кластер с 2+ дом-размерными (>= 60 м²) зданиями;
# C) многоэтажки: building=apartments ИЛИ levels>=3 (площадь/этаж 40..3500 м²);
#    N квартир = min(эт x S / 55, эт x подъезды x 4), подъезды = long/28.
#
# Верификация: VLM по кропам (признаки пользователя). Сплит применяется при
# n_properties >= 2 И НЕ пристройка И есть признак раздела (забор у центра
# фасада / стык). Если VLM недоступен — только детерминированные C-кандидаты
# (tier 1), A/B записываются в hh2_pending.json.
HH2_MIN_BBOX_M2 = 165.0     # «увеличенные размеры» (больше типового дома)
HH2_MIN_LONG_M = 12.5       # длинная сторона (фасад)
HH2_CENTER_T0, HH2_CENTER_T1 = 0.38, 0.62
HH2_MIN_PART_M2 = 36.0      # обе части — дом-размера
HH2_MIN_RATIO = 0.35        # «одинаковая форма»: сопоставимость частей
HH2_GEOM_RATIO = 0.30       # одноцветный канал: чуть мягче
HH2_SEAM_GRAD_T = 40.0      # порог градиента для шва/стыка кровель
HH2_SEAM_FRAC_MIN = 0.45
HH2_MIN_D_EAB = 8.5
HH2_STRONG_D_EAB = 18.0
HH2_NEUTRAL_TOL = 6.0
HH2_COLORED_TOL = 10.0
HH2_MAX_HUE_SHIFT = 25.0
HH2_CLUSTER_BLD_M2 = 60.0
HH2_B_MIN_SEP_M = 10.0
HH2_SANE_FPF = (40.0, 3500.0)'''

src = src.replace(old_block, new_block, 1)

# ---------- 2) roof_split_info ----------
f_start = src.index('def roof_split_info(mos, poly, mpp):')
f_end = src.index('def _hh2_vlm_available():')
old_fn = src[f_start:f_end]

new_fn = '''def roof_split_info(mos, poly, mpp):
    """Двухканальный тест «в здании два домохозяйства» (v3, Task 46).

    Канал A1 «двухцветная пара»: хроматический сплит у центра фасада при
    сопоставимых частях; канал A2 «одноцветная пара»: центр-сплит с швом/
    стыком кровель на линии раздела. Цвет — вспомогательный признак;
    решают размер + форма частей + шов (ограждение) + VLM-верификация.
    """
    import cv2
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0i, y0i = int(max(0, math.floor(min(xs)))), int(max(0, math.floor(min(ys))))
    x1i = int(min(mos.shape[1], math.ceil(max(xs))))
    y1i = int(min(mos.shape[0], math.ceil(max(ys))))
    W_, H_ = x1i - x0i, y1i - y0i
    if W_ < 14 or H_ < 14:
        return None
    # 1) «увеличенные размеры»
    if W_ * H_ * mpp * mpp < HH2_MIN_BBOX_M2:
        return None
    if max(W_, H_) * mpp < HH2_MIN_LONG_M:
        return None
    crop = mos[y0i:y1i, x0i:x1i]
    pts = np.array([[p[0] - x0i, p[1] - y0i] for p in poly], dtype=np.int32)
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    mask = cv2.erode(mask, np.ones((3, 3), np.uint8))
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    valid = (mask > 0) & (hsv[..., 2] >= 35) & (hsv[..., 2] <= 250)
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB)
    a_ch, b_ch = lab[..., 1].astype(np.float32), lab[..., 2].astype(np.float32)
    hue, sat = hsv[..., 0].astype(np.float32), hsv[..., 1].astype(np.float32)
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    Xg, Yg = np.meshgrid(np.arange(W_, dtype=np.float32),
                         np.arange(H_, dtype=np.float32))

    best_chroma = None   # A1: двухцветная пара
    best_geom = None     # A2: одноцветная пара со швом
    for axis in (0, 1):
        coord = Xg if axis == 0 else Yg
        span = W_ if axis == 0 else H_
        grad = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1 if axis == 0 else 0,
                                0 if axis == 0 else 1, ksize=3)) / 4.0
        for t in np.arange(HH2_CENTER_T0, HH2_CENTER_T1 + 1e-9, 0.02):
            cut = t * span
            m0 = valid & (coord < cut)
            m1 = valid & (coord >= cut)
            a0_m2 = float(m0.sum()) * mpp * mpp
            a1_m2 = float(m1.sum()) * mpp * mpp
            if a0_m2 < HH2_MIN_PART_M2 or a1_m2 < HH2_MIN_PART_M2:
                continue
            ratio = min(a0_m2, a1_m2) / max(a0_m2, a1_m2)
            if ratio < HH2_GEOM_RATIO:
                continue
            r = {}
            for lb, m in ((0, m0), (1, m1)):
                sm = sat[m]
                r[lb] = dict(n=int(m.sum()),
                             a=float(a_ch[m].mean()), b=float(b_ch[m].mean()),
                             cx=float(Xg[m].mean()), cy=float(Yg[m].mean()),
                             hue=float(hue[m][sm > 30].mean()) * 2.0
                             if (sm > 30).sum() > 30 else None)
            dE = math.hypot(r[0]['a'] - r[1]['a'], r[0]['b'] - r[1]['b'])
            n0 = abs(r[0]['a'] - 128) + abs(r[0]['b'] - 128)
            n1 = abs(r[1]['a'] - 128) + abs(r[1]['b'] - 128)
            nc = (n0 < HH2_NEUTRAL_TOL and n1 >= HH2_COLORED_TOL) or \\
                 (n1 < HH2_NEUTRAL_TOL and n0 >= HH2_COLORED_TOL)
            hd = None
            if r[0]['hue'] is not None and r[1]['hue'] is not None:
                dh = abs(r[0]['hue'] - r[1]['hue'])
                hd = min(dh, 360.0 - dh)
            two_color = (dE >= HH2_MIN_D_EAB and
                         (dE >= HH2_STRONG_D_EAB or nc or
                          (hd is not None and hd >= HH2_MAX_HUE_SHIFT)))
            band = valid & (np.abs(coord - cut) <= 1.5)
            nb = int(band.sum())
            seam_frac = float((grad[band] > HH2_SEAM_GRAD_T).sum()) / max(nb, 1) \\
                if nb > 0 else 0.0
            rec = dict(axis=axis, t=round(float(t), 2), ratio=round(ratio, 2),
                       dE=dE, two_color=two_color, seam_frac=seam_frac, r=r)
            if two_color and ratio >= HH2_MIN_RATIO:
                score = (2.0 * min(seam_frac / HH2_SEAM_FRAC_MIN, 1.0) +
                         min(dE / 15.0, 1.5) + 1.0 - abs(t - 0.5) / 0.13)
                if best_chroma is None or score > best_chroma[0]:
                    best_chroma = (score, rec)
            if seam_frac >= HH2_SEAM_FRAC_MIN:
                score = seam_frac + 1.0 - abs(t - 0.5) / 0.13
                if best_geom is None or score > best_geom[0]:
                    best_geom = (score, rec)

    if best_chroma is not None:
        pick = best_chroma[1]
    elif best_geom is not None:
        pick = best_geom[1]
    else:
        return None
    r0, r1 = pick['r'][0], pick['r'][1]
    return dict(dE_ab=round(pick['dE'], 1), axis=pick['axis'], t=pick['t'],
                ratio=pick['ratio'], two_color=bool(pick['two_color']),
                seam_frac=round(pick['seam_frac'], 2),
                part0=dict(cx=round(r0['cx'] + x0i, 1), cy=round(r0['cy'] + y0i, 1),
                           area_m2=round(r0['n'] * mpp * mpp, 1)),
                part1=dict(cx=round(r1['cx'] + x0i, 1), cy=round(r1['cy'] + y0i, 1),
                           area_m2=round(r1['n'] * mpp * mpp, 1)))


'''
src = src[:f_start] + new_fn + src[f_end:]

# ---------- 3) VLM-промпт + гейт ----------
i = src.index("            prompt = ('Спутниковый снимок села")
_END = '\'"fence_between": <bool>}\')'
pe = src.index(_END, i) + len(_END)
old_prompt = src[i:pe]

new_prompt = '''            prompt = ('Спутниковый снимок села (Восточный Казахстан, ~0.4 м/px). '
                      'Красный контур — строение по геоданным; вокруг — дворы, '
                      'заборы, соседние участки. Признаки ДВУХ и более владений: '
                      '(1) увеличенные размеры — строение крупнее соседних домов; '
                      '(2) забор примыкает к фасаду ПЕРПЕНДИКУЛЯРНО, ближе к '
                      'ЦЕНТРУ фасада, продолжаясь вглубь двора; (3) общая кровля '
                      'одинаковой формы, иногда двух цветов. НЕ признак: пристройка '
                      '— прямоугольник меньшего размера, отличной формы, часто '
                      'другого цвета, без забора. Ответь ТОЛЬКО JSON: '
                      '{"n_properties": <int>, "fence_between": <bool>, '
                      '"annex": <bool>}')'''
src = src.replace(old_prompt, new_prompt, 1)

# разбор ответа: учитываем annex/fence_between
old_ret = ("            return int(js['n_properties']) if js and 'n_properties' in js else None")
new_ret = ("            if not (js and 'n_properties' in js):\n"
           "                return None\n"
           "            # гейт Task 46: пристройка без забора — не владение\n"
           "            if js.get('annex') and not js.get('fence_between'):\n"
           "                return 1\n"
           "            return int(js['n_properties'])")
assert old_ret in src
src = src.replace(old_ret, new_ret, 1)

io.open(P, 'w', encoding='utf-8').write(src)
print('OK: пайплайн пропатчен (v3-критерии, промпт, гейт)')
import ast
ast.parse(src)
print('OK: синтаксис python валиден')
