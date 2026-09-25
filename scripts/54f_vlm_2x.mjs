// Task 54f: VLM антенны — перепроверка 10 кандидатов на 2x-апскейлах
// (калибровка показала: на 2x антенны заметно читаемее).
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const FIGS = '/home/z/my-project/work/altay_remarks';
const OUT = `${FIGS}/t54_vlm_2x.json`;

const IDS = [637127278, 637127296, 496463484, 637127295, 637127289,
  637127286, 637127291, 637127290, 637127277, 637127301];

const PROMPT = `Спутниковый снимок села (Восточный Казахстан), увеличенный 2x, исходно ~0.19 м/пиксель, вид строго сверху. Фиолетовый контур — здание.
ЗАДАЧА: посчитать ТЕЛЕВИЗИОННЫЕ АНТЕННЫ на крыше здания внутри контура.
ТВ-антенна сверху: маленькая яркая/тёмная ТОЧКА или короткая чёрточка (мачта), иногда Т-образная/крестовая перекладина, рядом маленькая тень. Несколько антенн = несколько точек вдоль конька/края крыши.
НЕ антенны: дымоходные трубы (крупнее, круглые), венткороба, деревья, машины.
КРИТЕРИЙ ЗАКАЗЧИКА: антенны на крыше = ЖИЛОЙ МНОГОЭТАЖНЫЙ дом (2 этажа, барак с квартирами). Плоская длинная крыша + антенны = общежитие/барак.
Также оцени: ряд крылец/подъездов вдоль длинного фасада, этажность (по тени, структуре), тип крыши, есть ли ворота (склад/гараж).
Отвечай ТОЛЬКО JSON без markdown:
{"tv_antennas": <true|false>, "n_antennas": <int>, "antenna_desc": "<до 10 слов>", "porches_row": <true|false>, "n_entrances": <int>, "levels": <int>, "roof": "<flat|gable|shed|other>", "gates": <true|false ворота склада/гаража>, "apartment_block": <true|false>, "comment": "<до 12 слов>"}`;

function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{');
  const j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

let lastStart = 0, pauseUntil = 0;
const MIN_INTERVAL_MS = 3500;
async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function checkOne(zai, id) {
  const b64 = fs.readFileSync(`${FIGS}/t54_crop_${id}_2x.png`).toString('base64');
  for (let attempt = 1; attempt <= 6; attempt++) {
    const wait = Math.max(lastStart + MIN_INTERVAL_MS, pauseUntil) - Date.now();
    if (wait > 0) await sleep(wait);
    lastStart = Date.now();
    try {
      const resp = await zai.chat.completions.createVision({
        messages: [{ role: 'user', content: [
          { type: 'text', text: PROMPT },
          { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
        ]}],
        thinking: { type: 'disabled' }
      });
      const txt = resp.choices?.[0]?.message?.content || '';
      const js = extractJson(txt);
      if (js && 'tv_antennas' in js) return { ok: true, v: js };
      if (attempt === 6) return { ok: false, parse_error: true, raw: txt.slice(0, 200) };
    } catch (e) {
      const is429 = String(e).includes('429');
      if (is429) { pauseUntil = Math.max(pauseUntil, Date.now() + 90000); console.log(`[429] пауза (${id})`); }
      if (attempt === 6) return { ok: false, error: String(e).slice(0, 160) };
      await sleep((is429 ? 20000 : 4000) * attempt);
    }
  }
  return { ok: false, error: 'unreachable' };
}

const zai = await ZAI.create();
const results = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT)) : {};
for (const id of IDS) {
  if (results[id]?.ok) { console.log(`${id}: есть`); continue; }
  const r = await checkOne(zai, id);
  results[id] = r;
  fs.writeFileSync(OUT + '.tmp', JSON.stringify(results, null, 1));
  fs.renameSync(OUT + '.tmp', OUT);
  const v = r.v || {};
  console.log(`${id}: ANT=${v.tv_antennas ?? '?'}×${v.n_antennas ?? '?'} `
    + `porch=${v.porches_row ?? '?'} ent=${v.n_entrances ?? '?'} lv=${v.levels ?? '?'} `
    + `${v.roof ?? '?'} gates=${v.gates ?? '?'} apt=${v.apartment_block ?? '?'} `
    + `| ${v.comment ?? 'FAIL'} (${v.antenna_desc ?? ''})`);
}
console.log('->', OUT);
