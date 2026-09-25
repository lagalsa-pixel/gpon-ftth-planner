// Task 55a: первичный VLM-анализ 4 изображений из altay2.pdf (заказчик: "Эти здания жилые")
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const DIR = '/home/z/my-project/work/altay2';
const OUT = `${DIR}/vlm_pass1.json`;

const IMGS = ['img_9.png', 'img_10.png', 'img_11.png', 'img_12.png'];

const PROMPT = `Это изображение из PDF, присланного заказчиком проекта FTTH (село Алтайское, Восточно-Казахстанская область). Заказчик сказал про здания на этих изображениях: "Эти здания жилые".

Опиши изображение МЕТОДИЧНО:
1) Тип изображения: аэро/спутниковый снимок сверху | наземное фото здания | фрагмент карты со схемой | другое
2) Если здание(я): сколько зданий видно, этажность каждого, тип крыши (плоская/двускатная/сложная)
3) ТВ-антенны на крыше (тонкие мачты/крестики с тенью): сколько на каждом здании
4) Крыльца/подъезды/входы: сколько и где
5) Состояние: жилое / заброшено / руины / стройка
6) Окружение: двор, дороги, деревья, другие постройки
7) Если это карта/снимок с выделением: что выделено (стрелка, контур, обводка), сколько объектов выделено

Отвечай ТОЛЬКО JSON без markdown:
{"img_type": "<satellite|ground_photo|map_fragment|other>", "buildings": <int>, "desc": "<подробное описание до 40 слов>", "antennas": <int всего>, "porches": <int всего>, "levels": <int макс>, "state": "<жилое|заброшено|руины|стройка|н/д>", "highlight": "<что выделено/нет, до 15 слов>"}`;

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
      console.error(`  attempt ${attempt} error (${is429 ? '429' : 'other'}), pause ${wait2 / 1000}s: ${String(e).slice(0, 120)}`);
      if (attempt === 6) return { ok: false, error: String(e).slice(0, 200) };
    }
  }
}

const zai = await ZAI.create();
const results = {};
for (const name of IMGS) {
  process.stdout.write(`Analyzing ${name}... `);
  const r = await ask(zai, PROMPT, `${DIR}/${name}`, 'img_type');
  results[name] = r.ok ? r.v : { error: r };
  console.log(r.ok ? JSON.stringify(r.v) : 'FAILED');
}
fs.writeFileSync(OUT, JSON.stringify(results, null, 2));
console.log('\nSaved:', OUT);
