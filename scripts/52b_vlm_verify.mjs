// Шаг 52b. VLM-верификация кандидатов уточнённой детекции ДХ.
// Параллельная обработка (5 воркеров), докачка (verdicts.json по сёлам),
// структурированные JSON-ответы.
import fs from 'fs';
import path from 'path';

// bun в этом окружении не резолвит глобальные пакеты из scripts/ — импорт
// по абсолютному пути с фолбэком на обычное имя
let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const BASE = '/home/z/my-project';
const KEYS = ['prigorodnoe', 'altaiskiy', 'vinnoe', 'solnechnoe', 'perevalnoe', 'verhneberezovka'];
// сёла уже с превышением Excel: area-only C-кандидаты (без OSM-этажности) не верифицируем
const SKIP_AREA_C = new Set(['solnechnoe', 'perevalnoe', 'vinnoe']);
const CONCURRENCY = parseInt(process.env.VLM_CONC || '2');
const MIN_INTERVAL_MS = parseInt(process.env.VLM_INT || '4000');  // фиксированный темп
const VLM_STACK = parseInt(process.env.VLM_STACK || '1');        // 2 = парные стеки (экономия квоты)
let lastStart = 0;
let pauseUntil = 0;   // адаптивный cooldown при 429: пауза всех воркеров
let four2nine = 0;    // счётчик подряд — растим паузу

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

const PROMPT_AB = `Спутниковый снимок села (Восточный Казахстан, ~0.4 м/px). Красный контур — строение (или группа строений) по геоданным; вокруг — дворы, заборы, соседние участки.
Признаки того, что здесь ДВА и более отдельных домохозяйств (владений):
1) УВЕЛИЧЕННЫЕ РАЗМЕРЫ: строение заметно крупнее соседних индивидуальных домов (сблокированная пара);
2) ОГРАЖДЕНИЕ: забор примыкает к фасаду ПЕРПЕНДИКУЛЯРНО ему, ближе к ЦЕНТРУ фасада, и продолжается вглубь двора, разделяя участки;
3) ОБЩАЯ КРОВЛЯ ОДИНАКОВОЙ ФОРМЫ: два одинаковых по форме блока/ската, иногда разного цвета (двухцветность не обязательна).
НЕ признак двух владений: пристройка/веранда/гараж — прямоугольник МЕНЬШЕГО размера, отличной формы в плане, часто с кровлей другого цвета, БЕЗ забора между ней и домом.
Хозпостройки (сараи, бани) на участке — не отдельные владения.
Задача: определи число отдельных владений внутри контура и признаки раздела.
Отвечай ТОЛЬКО JSON без markdown:
{"n_properties": <int число владений>, "fence_perp_center": <true|false забор примыкает к фасаду перпендикулярно ближе к центру>, "fence_extends": <true|false линия раздела продолжается вглубь двора>, "seam_visible": <true|false виден стык двух крыш/стен по линии раздела>, "annex": <true|false это дом с пристройкой меньшего размера>, "roof_same_shape": <true|false части кровли одинаковой формы>, "comment": "<до 12 слов>"}`;

const PROMPT_C = `Фрагмент спутникового снимка сельского населённого пункта. Красный контур — одно здание.
Определи тип здания. Критерии многоквартирного дома: 2 и более этажей, несколько подъездов, протяжённый фасад, длинная тень. Индивидуальный дом (в т.ч. 2-этажный с одним входом), школа, склад, производство — НЕ многоквартирные.
Отвечай ТОЛЬКО JSON без markdown:
{"apartment_block": <true|false>, "residential": <true|false жилое вообще>, "levels": <int этажность>, "entrances": <int число подъездов, 0 если не видно>, "comment": "<до 12 слов>"}`;

// Парный стек: два фрагмента в одном изображении (верх = f1, низ = f2),
// критерии идентичны PROMPT_AB — экономия квоты вдвое.
const PROMPT_AB_STACK = `Спутниковый снимок (Восточный Казахстан, ~0.4 м/px) содержит ДВА независимых фрагмента: FRAGMENT 1 — верхняя половина, FRAGMENT 2 — нижняя половина (разделены белой полосой). На каждом фрагменте красный контур — строение (или группа строений) по геоданным; вокруг — дворы, заборы, соседние участки.
Признаки того, что здесь ДВА и более отдельных домохозяйств (владений):
1) УВЕЛИЧЕННЫЕ РАЗМЕРЫ: строение заметно крупнее соседних индивидуальных домов (сблокированная пара);
2) ОГРАЖДЕНИЕ: забор примыкает к фасаду ПЕРПЕНДИКУЛЯРНО ему, ближе к ЦЕНТРУ фасада, и продолжается вглубь двора, разделяя участки;
3) ОБЩАЯ КРОВЛЯ ОДИНАКОВОЙ ФОРМЫ: два одинаковых по форме блока/ската, иногда разного цвета (двухцветность не обязательна).
НЕ признак двух владений: пристройка/веранда/гараж — прямоугольник МЕНЬШЕГО размера, отличной формы в плане, часто с кровлей другого цвета, БЕЗ забора между ней и домом.
Хозпостройки (сараи, бани) на участке — не отдельные владения.
Задача: для КАЖДОГО фрагмента ОТДЕЛЬНО определи число отдельных владений внутри контура и признаки раздела.
Отвечай ТОЛЬКО JSON без markdown:
{"f1": {"n_properties": <int>, "fence_perp_center": <true|false>, "fence_extends": <true|false>, "seam_visible": <true|false>, "annex": <true|false>, "roof_same_shape": <true|false>, "comment": "<до 12 слов>"},
 "f2": {"n_properties": <int>, "fence_perp_center": <true|false>, "fence_extends": <true|false>, "seam_visible": <true|false>, "annex": <true|false>, "roof_same_shape": <true|false>, "comment": "<до 12 слов>"}}`;

function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{');
  const j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

// атомарная запись (tmp + rename): обрыв процесса не портит verdicts.json
function saveJsonAtomic(p, obj) {
  const tmp = p + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 1));
  fs.renameSync(tmp, p);
}

// стек: один вызов — два вердикта (f1/f2); при неудаче оба уйдут в одиночную фазу
async function verifyStack(zai, imgPath) {
  const b64 = fs.readFileSync(imgPath).toString('base64');
  for (let attempt = 1; attempt <= 8; attempt++) {
    const waitStart = Math.max(lastStart + MIN_INTERVAL_MS, pauseUntil) - Date.now();
    if (waitStart > 0) await sleep(waitStart);
    lastStart = Date.now();
    try {
      const resp = await zai.chat.completions.createVision({
        messages: [{
          role: 'user',
          content: [
            { type: 'text', text: PROMPT_AB_STACK },
            { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } }
          ]
        }],
        thinking: { type: 'disabled' }
      });
      const txt = resp.choices?.[0]?.message?.content || '';
      const js = extractJson(txt);
      if (js && js.f1 && 'n_properties' in js.f1 && js.f2 && 'n_properties' in js.f2) {
        four2nine = 0;
        return { ok: true, v1: js.f1, v2: js.f2, raw: txt.slice(0, 300) };
      }
      if (attempt === 8) return { ok: false, parse_error: true, raw: txt.slice(0, 300) };
    } catch (e) {
      const is429 = String(e).includes('429');
      if (is429) {
        four2nine++;
        const pauseMs = Math.min(90000 + four2nine * 30000, 300000);
        pauseUntil = Math.max(pauseUntil, Date.now() + pauseMs);
        console.log(`[429] пауза ${Math.round(pauseMs / 1000)} c (серия ${four2nine})`);
      }
      if (attempt === 8) return { ok: false, error: String(e).slice(0, 200) };
      await sleep((is429 ? 20000 : 4000) * attempt);
    }
  }
  return { ok: false, error: 'unreachable' };
}

async function verifyOne(zai, cand, imgPath) {
  const b64 = fs.readFileSync(imgPath).toString('base64');
  const prompt = cand.type === 'C' ? PROMPT_C : PROMPT_AB;
  for (let attempt = 1; attempt <= 8; attempt++) {
    // троттлинг стартов + глобальная пауза при 429
    const waitStart = Math.max(lastStart + MIN_INTERVAL_MS, pauseUntil) - Date.now();
    if (waitStart > 0) await sleep(waitStart);
    lastStart = Date.now();
    try {
      const resp = await zai.chat.completions.createVision({
        messages: [{
          role: 'user',
          content: [
            { type: 'text', text: prompt },
            { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } }
          ]
        }],
        thinking: { type: 'disabled' }
      });
      const txt = resp.choices?.[0]?.message?.content || '';
      const js = extractJson(txt);
      if (js && ('n_properties' in js || 'apartment_block' in js)) {
        four2nine = 0;
        return { ok: true, ...js, raw: txt.slice(0, 300) };
      }
      if (attempt === 8) return { ok: false, parse_error: true, raw: txt.slice(0, 300) };
    } catch (e) {
      const is429 = String(e).includes('429');
      if (is429) {
        four2nine++;
        // пауза всех воркеров: 90 c, при серии 429 — до 5 мин
        const pauseMs = Math.min(90000 + four2nine * 30000, 300000);
        pauseUntil = Math.max(pauseUntil, Date.now() + pauseMs);
        console.log(`[429] пауза ${Math.round(pauseMs / 1000)} c (серия ${four2nine})`);
      }
      if (attempt === 8) return { ok: false, error: String(e).slice(0, 200) };
      await sleep((is429 ? 20000 : 4000) * attempt);
    }
  }
  return { ok: false, error: 'unreachable' };
}

async function main() {
  const onlyKey = process.argv[2] || null;
  const zai = await ZAI.create();
  for (const key of KEYS) {
    if (onlyKey && key !== onlyKey) continue;
    const dir = path.join(BASE, 'work', 'hh2', key);
    const candsPath = path.join(dir, 'candidates.json');
    if (!fs.existsSync(candsPath)) continue;
    const cands = JSON.parse(fs.readFileSync(candsPath, 'utf8'));
    const vPath = path.join(dir, 'verdicts.json');
    const verdicts = fs.existsSync(vPath) ? JSON.parse(fs.readFileSync(vPath, 'utf8')) : {};
    const todo = cands.filter(c => {
      if (verdicts[c.cid] && verdicts[c.cid].ok) return false;
      if (c.type === 'C' && SKIP_AREA_C.has(key) && !(c.lv >= 2 || c.tag === 'apartments')) return false;
      return true;
    });
    // приоритет очереди: B (кластер) -> A с признаками (prio 1/2) -> A одноцветные (3) -> C
    const po = c => c.type === 'B' ? 0 : (c.type === 'A' ? (c.prio || 3) : 4);
    todo.sort((a, b) => po(a) - po(b));
    console.log(`[${key}] кандидатов ${cands.length}, осталось ${todo.length}`);
    if (!todo.length) continue;

    // ФАЗА 1 (VLM_STACK=2): парные стеки — один вызов на два кандидата
    if (VLM_STACK >= 2) {
      const stacksPath = path.join(dir, 'stacks.json');
      if (fs.existsSync(stacksPath)) {
        const stacks = JSON.parse(fs.readFileSync(stacksPath, 'utf8'));
        const units = Object.entries(stacks)
          .filter(([sf, s]) => fs.existsSync(path.join(dir, sf))
            && s.cids.every(cid => todo.some(c => c.cid === cid)))
          .map(([sf, s]) => ({ file: path.join(dir, sf), cids: s.cids }));
        console.log(`[${key}] стеков к проверке: ${units.length}`);
        let sidx = 0, sdone = 0;
        async function sworker() {
          while (sidx < units.length) {
            const u = units[sidx++];
            const r = await verifyStack(zai, u.file);
            if (r.ok) {
              verdicts[u.cids[0]] = { ok: true, ...r.v1, stack: true, raw: r.raw };
              verdicts[u.cids[1]] = { ok: true, ...r.v2, stack: true, raw: r.raw };
            } else {
              // стек не разобрался — оба кандидата останутся в одиночной фазе
              console.log(`[stack] не удался ${path.basename(u.file)}: ${r.error || 'parse'}`);
            }
            sdone++;
            if (sdone % 10 === 0 || sdone === units.length) {
              console.log(`[${key}] стеки ${sdone}/${units.length}`);
              saveJsonAtomic(vPath, verdicts);
            }
          }
        }
        await Promise.all(Array.from({ length: CONCURRENCY }, sworker));
        saveJsonAtomic(vPath, verdicts);
      }
    }

    // ФАЗА 2: одиночные кандидаты (C, хвосты, неудавшиеся стеки)
    const todo2 = todo.filter(c => !(verdicts[c.cid] && verdicts[c.cid].ok));
    console.log(`[${key}] одиночных после стеков: ${todo2.length}`);
    let idx = 0, done = 0;
    async function worker() {
      while (idx < todo2.length) {
        const c = todo2[idx++];
        const img = path.join(dir, `cand_${c.cid}.jpg`);
        if (!fs.existsSync(img)) {
          verdicts[c.cid] = { ok: false, error: 'no image' };
        } else {
          verdicts[c.cid] = await verifyOne(zai, c, img);
        }
        done++;
        if (done % 10 === 0 || done === todo2.length) {
          console.log(`[${key}] ${done}/${todo2.length}`);
          saveJsonAtomic(vPath, verdicts);
        }
      }
    }
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
    saveJsonAtomic(vPath, verdicts);
    const okN = Object.values(verdicts).filter(v => v.ok).length;
    console.log(`[${key}] готово: ${okN}/${cands.length} вердиктов OK`);
  }
  console.log('ALL DONE');
}
main().catch(e => { console.error('FATAL', e); process.exit(1); });
