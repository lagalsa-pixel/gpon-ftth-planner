// Task 55h: финальная VLM-сверка пар «фрагмент заказчика | карта с ID»
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const DIR = '/home/z/my-project/work/altay2';
const OUT = `${DIR}/vlm_pairs.json`;

const PROMPT = `Пара изображений села Алтайское. Слева (A) — фрагмент от заказчика: одно или два здания, которые заказчик назвал ЖИЛЫМИ (возможна синяя обводка — его аннотация). Справа (B) — та же местность на карте проекта: пурпурные контуры = известные здания, рядом с контурами пурпурные цифры ID (последние 3 цифры, напр. 290). Зелёная рамка — границы фрагмента A на карте.

Задача: сопоставь здания с фрагмента A зданиям на карте B по форме, размеру, ориентации, крыше, окружению (дороги, деревья, соседние здания).

Отвечай ТОЛЬКО JSON без markdown:
{"matches": [{"fig_building": "<описание здания на A, до 10 слов>", "map_id": "<ID с карты B или 'НЕТ_ID' если здание без пурпурного контура>", "confidence": <0..1>}], "unlabeled_on_map": <true|false есть ли на A здание, которого НЕТ на B ни с одним контуром>, "notes": "<до 20 слов>"}`;

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

async function ask(zai, prompt, imgPath, key) {
  const b64 = fs.readFileSync(imgPath).toString('base64');
  for (let attempt = 1; attempt <= 6; attempt++) {
    const wait = Math.max(lastStart + MIN_INTERVAL_MS, pauseUntil) - Date.now();
    if (wait > 0) await sleep(wait);
    lastStart = Date.now();
    try {
      const resp = await zai.chat.completions.createVision({
        messages: [{ role: 'user', content: [
          { type: 'text', text: prompt },
          { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
        ]}],
        thinking: { type: 'disabled' }
      });
      const txt = resp.choices?.[0]?.message?.content || '';
      const js = extractJson(txt);
      if (js && key in js) return { ok: true, v: js };
      if (attempt === 6) return { ok: false, parse_error: true, raw: txt.slice(0, 300) };
    } catch (e) {
      const is429 = String(e).includes('429');
      const wait2 = is429 ? 30000 : 8000;
      pauseUntil = Date.now() + wait2;
      console.error(`  attempt ${attempt} err: ${String(e).slice(0, 100)}`);
      if (attempt === 6) return { ok: false, error: String(e).slice(0, 200) };
    }
  }
}

const zai = await ZAI.create();
const results = {};
for (const name of ['img_9', 'img_10', 'img_11', 'img_12']) {
  process.stdout.write(`${name} pair... `);
  const r = await ask(zai, PROMPT, `${DIR}/pair_${name}.jpg`, 'matches');
  results[name] = r.ok ? r.v : { error: r };
  console.log(JSON.stringify(results[name]));
}
fs.writeFileSync(OUT, JSON.stringify(results, null, 2));
console.log('saved', OUT);
