// Шаг 52h-run (Task 47). Прогон контрольных стеков ВБ (валидация парного режима).
// Один вызов на стек; результат -> work/hh2/verhneberezovka/val_verdicts.json
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
import fs from 'fs';
import path from 'path';

const D = '/home/z/my-project/work/hh2/verhneberezovka';
const MIN_INTERVAL_MS = parseInt(process.env.VLM_INT || '4000');
let lastStart = 0;

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
  const i = t.indexOf('{'), j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

const zai = await ZAI.create();
const stacks = JSON.parse(fs.readFileSync(path.join(D, 'val_stacks.json'), 'utf8'));
const out = fs.existsSync(path.join(D, 'val_verdicts.json'))
  ? JSON.parse(fs.readFileSync(path.join(D, 'val_verdicts.json'), 'utf8')) : {};

for (const [sf, s] of Object.entries(stacks)) {
  if (out[sf] && out[sf].ok) continue;
  const img = path.join(D, sf);
  const b64 = fs.readFileSync(img).toString('base64');
  let res = { ok: false };
  for (let a = 1; a <= 6; a++) {
    const w = Math.max(lastStart + MIN_INTERVAL_MS) - Date.now();
    if (w > 0) await sleep(w);
    lastStart = Date.now();
    try {
      const resp = await zai.chat.completions.createVision({
        messages: [{ role: 'user', content: [
          { type: 'text', text: PROMPT_AB_STACK },
          { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } } ] }],
        thinking: { type: 'disabled' } });
      const js = extractJson(resp.choices?.[0]?.message?.content || '');
      if (js && js.f1 && 'n_properties' in js.f1 && js.f2 && 'n_properties' in js.f2) {
        res = { ok: true, v1: js.f1, v2: js.f2 }; break;
      }
    } catch (e) {
      if (String(e).includes('429')) { console.log('429, пауза 120 с'); await sleep(120000); }
      else await sleep(8000);
    }
  }
  out[sf] = res;
  fs.writeFileSync(path.join(D, 'val_verdicts.json'), JSON.stringify(out, null, 1));
  console.log(sf, res.ok ? 'OK' : 'FAIL');
}
console.log('VALIDATION RUN DONE');
