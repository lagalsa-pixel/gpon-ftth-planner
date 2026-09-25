// Task 54e: VLM антенны — КАЛИБРОВКА на заведомых многоэтажках Task 53
// + перепроверка «частных домов» R3. Использует 2x-апскейлы.
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const FIGS = '/home/z/my-project/work/altay_remarks';
const OUT = `${FIGS}/t54_vlm_calib.json`;

const CALIB = {
  496463512: 'APT_R1', 496463513: 'APT_R1',
  637127272: 'APT_R3_barracks', 637127280: 'APT_R3', 637127294: 'APT_R2',
  496463485: 'APT_R2',
  637127288: 'R3_private?', 637127289: 'R3_private?',
  637127290: 'R3_private?', 637127291: 'R3_private?',
  637127279: 'R3_private?',
};

const PROMPT = `Спутниковый снимок села (Восточный Казахстан), увеличенный 2x, исходно ~0.19 м/пиксель, вид строго сверху. Фиолетовый контур — здание.
ЗАДАЧА: посчитать ТЕЛЕВИЗИОННЫЕ АНТЕННЫ на крыше здания внутри контура.
ТВ-антенна на снимке сверху выглядит как: маленькая яркая/тёмная ТОЧКА или короткая чёрточка (мачта), иногда с Т-образной или крестообразной перекладиной, часто рядом маленькая тень-чёрточка. Несколько антенн = несколько точек вдоль конька/края крыши.
НЕ антенны: трубы дымоходы (крупнее, круглые пятна), вентиляционные короба, конёк крыши, деревья рядом, машины.
Также оцени: ряд крылец (подъездов) вдоль длинного фасада (маленькие прямоугольные выступы/навесы + тропинки), этажность по тени и структуре, тип крыши.
Отвечай ТОЛЬКО JSON без markdown:
{"tv_antennas": <true|false>, "n_antennas": <int>, "antenna_desc": "<до 10 слов как выглядят и где>", "porches_row": <true|false>, "n_entrances": <int>, "levels": <int>, "roof": "<flat|gable|shed|other>", "chimneys": <true|false трубы вдоль крыши>, "comment": "<до 12 слов>"}`;

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
  const b64 = fs.readFileSync(`${FIGS}/t54_calib_${id}_2x.png`).toString('base64');
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
for (const [id, tag] of Object.entries(CALIB)) {
  if (results[id]?.ok) { console.log(`${id}: есть`); continue; }
  const r = await checkOne(zai, id);
  results[id] = { ...r, tag };
  fs.writeFileSync(OUT + '.tmp', JSON.stringify(results, null, 1));
  fs.renameSync(OUT + '.tmp', OUT);
  const v = r.v || {};
  console.log(`${id} [${tag}]: ANT=${v.tv_antennas ?? '?'}×${v.n_antennas ?? '?'} `
    + `porch=${v.porches_row ?? '?'} ent=${v.n_entrances ?? '?'} lv=${v.levels ?? '?'} `
    + `${v.roof ?? '?'} chim=${v.chimneys ?? '?'} | ${v.comment ?? 'FAIL'} `
    + `(${v.antenna_desc ?? ''})`);
}
console.log('->', OUT);
