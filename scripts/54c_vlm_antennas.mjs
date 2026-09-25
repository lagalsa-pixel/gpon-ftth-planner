// Task 54: VLM-проверка кандидатов в пропущенные многоэтажки (Алтайский).
// НОВЫЙ КРИТЕРИЙ ЗАКАЗЧИКА: телевизионные антенны на крыше = жилой
// многоквартирный дом. Проверяем 10 кропов из кадра заказчика (0.19 м/px).
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const BASE = '/home/z/my-project';
const FIGS = `${BASE}/work/altay_remarks`;
const OUT = `${FIGS}/t54_vlm.json`;

const IDS = [637127278, 637127296, 496463484, 637127295, 637127289,
  637127286, 637127291, 637127290, 637127277, 637127301];

const PROMPT = `Спутниковый снимок села (Восточный Казахстан, ~0.19 м/пиксель, вид сверху). Фиолетовый контур — здание.
КРИТЕРИЙ ЗАКАЗЧИКА: телевизионные антенны на крыше (вертикальные мачты с перекладинами, точка-тень рядом) — признак ЖИЛОГО МНОГОКВАРТИРНОГО дома (2 этажа, барак/общежитие с несколькими квартирами).
Другие признаки: плоская или двускатная длинная крыша, ряд крылец/подъездов вдоль длинной стороны, вытянутая форма (как у барака), несколько отдельных входов.
Хозпостройка/склад/гараж: нет антенн, нет крылец, ворота, низкое.
Посмотри ВНИМАТЕЛЬНО на крышу внутри контура: есть ли ТВ-антенны (мачты), сколько; есть ли ряд крылец; тип крыши; оценка этажности по тени и структуре.
Отвечай ТОЛЬКО JSON без markdown:
{"tv_antennas": <true|false>, "n_antennas": <int 0 если нет>, "antenna_where": "<до 8 слов где именно>", "porches_row": <true|false ряд крылец/подъездов вдоль фасада>, "levels": <int оценка этажности>, "roof": "<flat|gable|shed|other>", "residential": <true|false>, "apartment_block": <true|false многоэтажный жилой с квартирами>, "comment": "<до 15 слов>"}`;

function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{');
  const j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

let lastStart = 0;
let pauseUntil = 0;
const MIN_INTERVAL_MS = 3500;

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function checkOne(zai, id) {
  const p = `${FIGS}/t54_crop_${id}.png`;
  const b64 = fs.readFileSync(p).toString('base64');
  for (let attempt = 1; attempt <= 6; attempt++) {
    const wait = Math.max(lastStart + MIN_INTERVAL_MS, pauseUntil) - Date.now();
    if (wait > 0) await sleep(wait);
    lastStart = Date.now();
    try {
      const resp = await zai.chat.completions.createVision({
        messages: [{
          role: 'user',
          content: [
            { type: 'text', text: PROMPT },
            { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
          ]
        }],
        thinking: { type: 'disabled' }
      });
      const txt = resp.choices?.[0]?.message?.content || '';
      const js = extractJson(txt);
      if (js && 'tv_antennas' in js) return { ok: true, v: js, raw: txt.slice(0, 250) };
      if (attempt === 6) return { ok: false, parse_error: true, raw: txt.slice(0, 250) };
    } catch (e) {
      const is429 = String(e).includes('429');
      if (is429) {
        pauseUntil = Math.max(pauseUntil, Date.now() + 90000);
        console.log(`[429] пауза 90 c (${id})`);
      }
      if (attempt === 6) return { ok: false, error: String(e).slice(0, 180) };
      await sleep((is429 ? 20000 : 4000) * attempt);
    }
  }
  return { ok: false, error: 'unreachable' };
}

const zai = await ZAI.create();
const results = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT)) : {};
for (const id of IDS) {
  if (results[id]?.ok) { console.log(`${id}: уже есть`); continue; }
  const r = await checkOne(zai, id);
  results[id] = r;
  fs.writeFileSync(OUT + '.tmp', JSON.stringify(results, null, 1));
  fs.renameSync(OUT + '.tmp', OUT);
  const v = r.v || {};
  console.log(`${id}: antennas=${v.tv_antennas ?? '?'}(${v.n_antennas ?? '?'}) `
    + `porches=${v.porches_row ?? '?'} lv=${v.levels ?? '?'} roof=${v.roof ?? '?'} `
    + `apt=${v.apartment_block ?? '?'} | ${v.comment ?? (r.error || r.parse_error ? 'FAIL ' + (r.raw || '') : '')}`);
}
console.log('->', OUT);
