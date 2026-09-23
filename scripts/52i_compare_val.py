# -*- coding: utf-8 -*-
"""
Шаг 52i (Task 47). Сравнение стек-вердиктов с эталоном (одиночные вызовы
Task 46, Верхнеберезовка): согласованность гейта 52c (второе владение да/нет)
и полей. Порог допуска парного режима: согласованность >= 0,90 и отсутствие
систематического смещения (|принято ложно - отклонено ложно| <= 3).
"""
import json

D = '/home/z/my-project/work/hh2/verhneberezovka'


def gate_pass(v):
    # ВНИМАНИЕ: v здесь — подсписок f1/f2 (n_properties, fence_* ...), поля 'ok'
    # в нём НЕТ (оно на родителе); прежняя проверка v.get('ok') превращала гейт
    # в постоянно False (FP=0, FN=20 — ложный провал стекового режима)
    np_ = v.get('n_properties')
    if not isinstance(np_, (int, float)) or np_ < 2:
        return False
    if bool(v.get('annex')) and not v.get('fence_perp_center'):
        return False
    return bool(v.get('fence_perp_center') or v.get('fence_extends')
                or v.get('seam_visible') or v.get('fence_between'))


def main():
    vv = json.load(open(f'{D}/val_verdicts.json', encoding='utf-8'))
    ref = json.load(open(f'{D}/val_gate_ref.json', encoding='utf-8'))['gate']
    n = agree = 0
    fp = fn = 0     # ложные принятия / ложные отклонения
    np_diff = []
    for sf, r in vv.items():
        if not r.get('ok'):
            print('FAIL стек:', sf)
            continue
        for k, cid in zip(('v1', 'v2'), json.load(open(f'{D}/val_stacks.json'))[sf]['cids']):
            if cid not in ref:
                continue
            n += 1
            g_new = gate_pass(r[k])
            g_ref = ref[cid]
            if g_new == g_ref:
                agree += 1
            elif g_new:
                fp += 1
            else:
                fn += 1
            np_new = r[k].get('n_properties')
            np_diff.append((cid, np_new, g_ref))
    print(f'сравнено кандидатов: {n}')
    print(f'согласованность гейта: {agree}/{n} = {agree/max(1,n):.3f}')
    print(f'ложных принятий (стек сказал «2 владения», эталон — нет): {fp}')
    print(f'ложных отклонений (эталон — сплит, стек — нет): {fn}')
    ok = (n >= 30) and (agree / max(1, n) >= 0.90) and (abs(fp - fn) <= 3)
    print('ВЕРДИКТ ПАРНОГО РЕЖИМА:', 'ДОПУСТИМ' if ok else 'НЕ ДОПУСТИМ — только одиночные')
    return ok


if __name__ == '__main__':
    import sys
    sys.exit(0 if main() else 1)
