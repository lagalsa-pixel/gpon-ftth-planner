// Task 55j: VLM на базовом кадре (без оверлея): 283 (этажность/антенны/входы)
// и регион img_12 (есть ли здание, его параметры для оцифровки)
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const DIR = '/home/z/my-project/work/altay2';
const OUT = `${DIR}/vlm_pass3.json`;

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
      pauseUntil = Date.now() + (is429 ? 30000 : 8000);
      console.error(`  err: ${String(e).slice(0, 100)}`);
      if (attempt === 6) return { ok: false, error: String(e).slice(0, 200) };
    }
  }
}

const zai = await ZAI.create();
const results = {};

// --- 283 на чистом кадре ---
process.stdout.write('283 base 2x... ');
results.b283 = (await ask(zai, `Чистый спутниковый кадр (2x, ~0.3 м/пикс) села. В центре здание в пурпурной рамке (9.3 x 28.9 м, вытянуто север-юг). Заказчик проекта заявил: это здание ЖИЛОЕ. Определи его параметры для расчёта домохозяйств:
1) Этажность: 1 или 2? (смотри на тень: у 2-этажного тень выше; на структуру крыши; на рядом стоящие бараки-аналоги)
2) ТВ-антенны на крыше: сколько тонких мачт с тенью?
3) Входы/крыльца вдоль фасада: сколько?
4) Состояние: целое / частично разрушено / руины?
5) Тип: барак с квартирами / частный дом / склад?
Отвечай ТОЛЬКО JSON: {"levels": <int>, "antennas": <int>, "porches": <int>, "state": "<ok|partial|ruins>", "type": "<barracks|private|warehouse>", "confidence": <0..1>, "why": "<до 15 слов>"}`, `${DIR}/base_283_2x.jpg`, 'levels')).v;
console.log(JSON.stringify(results.b283));

// --- регион img_12 на чистом кадре ---
process.stdout.write('img12 base 3x... ');
results.img12 = (await ask(zai, `Чистый спутниковый кадр (3x) села Алтайское. Заказчик обвёл синим ЖИЛОЕ здание на этом месте (между длинными бараками слева и справа вдали). Найди его:
1) Есть ли здесь здание? Сколько? Опиши каждое: положение в кадре (в долях ширины/высоты 0..1), ориентация (гориз/верт), примерные размеры в метрах (масштаб: бараки по краям ~40 м длиной).
2) Крыша (двускатная/плоская), этажность, состояние.
3) Признаки жилья: антенны, крыльца, тропинки, огород, забор.
4) Это уже известные бараки по краям (левее/правее края кадра) или отдельное здание между ними?
Отвечай ТОЛЬКО JSON: {"n_buildings": <int>, "buildings": [{"pos": "<x,y в долях>", "orient": "<horiz|vert>", "size_m": "<длинаxширина>", "roof": "<gable|flat>", "levels": <int>, "state": "<ok|ruins>", "housing_signs": "<до 15 слов>"}], "between_barracks": <true|false>, "notes": "<до 20 слов>"}`, `${DIR}/base_img12_3x.jpg`, 'n_buildings')).v;
console.log(JSON.stringify(results.img12));

fs.writeFileSync(OUT, JSON.stringify(results, null, 2));
console.log('saved', OUT);
