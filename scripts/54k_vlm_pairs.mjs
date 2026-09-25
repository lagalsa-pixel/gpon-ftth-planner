// Task 54k: финальная VLM-сверка типов — пары «эталонный жилой барак A |
// подозреваемый B». Решаем: B — жилой многоквартирный (барак) или нет.
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const FIGS = '/home/z/my-project/work/altay_remarks';
const OUT = `${FIGS}/t54_vlm_pairs.json`;

const IDS = [637127276, 637127283, 759801027, 496463521, 637127279,
  637127288, 637127289, 637127295, 496463519, 759801042, 759801043];

const PROMPT = `Сравнение двух зданий со спутника (село в Восточном Казахстане, ~0.19 м/пикс, 2x увеличение).
Панель A (слева) — ЭТАЛОН: жилой барак на несколько квартир (подтверждён заказчиком): длинное здание, двускатная крыша, вдоль конька видны ТВ-антенны (мачты-точки), есть крыльца.
Панель B (справа, фиолетовый контур) — проверяемое здание.
Задача: определить, здание B — ТОГО ЖЕ ТИПА (жилой дом/барак с несколькими квартирами, где живут люди) или ДРУГОГО типа (склад/гараж/сарай/руины/одинокий частный дом с одним входом).
Признаки жилья: ТВ-антенны на крыше, ряд крылец/входов, тропинки ко входам, огород/посадки рядом, хозяйственная активность. Признаки нежилья: ворота для транспорта, глухие стены, складские площадки, отсутствие входов.
Отвечай ТОЛЬКО JSON без markdown:
{"same_type_as_A": <true|false B того же жилого типа>, "residential_b": <true|false в B живут люди>, "apartments_b": <true|false несколько отдельных квартир в B>, "n_entrances_b": <int>, "antennas_b": <int>, "evidence": "<до 15 слов>"}`;

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
  const b64 = fs.readFileSync(`${FIGS}/t54_pair_${id}.png`).toString('base64');
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
      if (js && 'same_type_as_A' in js) return { ok: true, v: js };
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
  console.log(`${id}: same=${v.same_type_as_A ?? '?'} res=${v.residential_b ?? '?'} `
    + `apt=${v.apartments_b ?? '?'} ent=${v.n_entrances_b ?? '?'} ant=${v.antennas_b ?? '?'} `
    + `| ${v.evidence ?? 'FAIL'}`);
}
console.log('->', OUT);
