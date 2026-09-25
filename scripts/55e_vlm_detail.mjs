// Task 55e: детальный VLM-анализ img_10 (не сматчился) и img_12 (нет OSM здания)
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const DIR = '/home/z/my-project/work/altay2';
const OUT = `${DIR}/vlm_pass2.json`;

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
      console.error(`  attempt ${attempt} err (${is429 ? '429' : 'x'}): ${String(e).slice(0, 100)}`);
      if (attempt === 6) return { ok: false, error: String(e).slice(0, 200) };
    }
  }
}

// апскейл x4 для читаемости
import { execSync } from 'child_process';
execSync(`python3 -c "
from PIL import Image
for n in ['img_10','img_11','img_12']:
    im = Image.open('${DIR}/'+n+'.png')
    im.resize((im.width*4, im.height*4), Image.LANCZOS).save('${DIR}/'+n+'_4x.png')
"`);

const zai = await ZAI.create();
const results = {};

// --- img_10: максимум деталей для идентификации ---
process.stdout.write('img_10 detail... ');
results.img_10 = (await ask(zai, `Крупный вид (4x апскейл) фрагмента карты FTTH села (спутниковый фон + схема сети). Рассмотри ВНИМАТЕЛЬНО:
1) Здание, обведённое/выделенное синим контуром (обводка могла сделать заказчица): форма (вытянутое/квадратное), ориентация (вертикально/горизонтально), примерные пропорции (длина:ширина), крыша (двускатная с коньком/плоская), этажность по виду.
2) Есть ли на САМОМ здании маленькие цветные квадратики (точки подключения ДХ)? Сколько?
3) Что рядом: дорога (с какой стороны), деревья, другие здания (сколько, где), линии трассы (цвет), муфты (крупные квадраты) — где стоят относительно здания.
4) Тень здания: с какой стороны, длинная/короткая.
5) Особые приметы: ворота, пристройки, огород, забор.
Отвечай ТОЛЬКО JSON: {"shape":"<прямоуг вытянутый|квадратный|Г-обр>","orient":"<vert|horiz>","ratio":"<длина:ширина, напр 3:1>","roof":"<gable|flat|unknown>","levels":<int>,"hh_squares":<int на здании>,"nearby":"<до 25 слов: дороги, деревья, соседние здания>","trace_color":"<цвет линии трассы>","couplers":"<где муфты, до 15 слов>","shadow":"<сторона и длина>","marks":"<особые приметы до 15 слов>"}`, `${DIR}/img_10_4x.png`, 'shape')).v;
console.log(JSON.stringify(results.img_10));

// --- img_12: подтверждение "здание без OSM" ---
process.stdout.write('img_12 detail... ');
results.img_12 = (await ask(zai, `Крупный вид (4x апскейл) фрагмента карты FTTH села. Заказчик обвёл здание синим контуром и говорит, что оно жилое.
1) Форма здания под синим контуром: вытянутое/квадратное, ориентация, пропорции, крыша (двускатная/плоская), этажность.
2) Есть ли на здании маленькие цветные квадратики ДХ (точки подключения)? Или оно БЕЗ подключений?
3) Где проходит жёлтая/цветная линия (дроп/трасса): мимо здания? к соседнему?
4) Соседние здания: сколько, с какой стороны, есть ли у них ДХ-квадратики?
5) Окружение: дороги, деревья, пустырь.
Отвечай ТОЛЬКО JSON: {"shape":"<...>","orient":"<vert|horiz>","ratio":"<...>","roof":"<gable|flat>","levels":<int>,"hh_squares":<int>,"has_drops":<true|false>,"line_where":"<до 15 слов>","neighbors":"<до 20 слов>","yard":"<до 15 слов>"}`, `${DIR}/img_12_4x.png`, 'shape')).v;
console.log(JSON.stringify(results.img_12));

// --- img_11: что за здание 283 ---
process.stdout.write('img_11 detail... ');
results.img_11 = (await ask(zai, `Крупный вид (4x апскейл) фрагмента карты FTTH села. Одно здание в центре (рядом жёлтая стрелка/линия — элемент схемы или аннотация заказчика).
1) Здание в центре: форма, ориентация, пропорции, крыша (плоская/двускатная), состояние (целая/провалы крыши/руины).
2) ТВ-антенны на крыше (тонкие мачты с тенью): сколько?
3) Входы/крыльца: сколько, с какой стороны?
4) Квадратики ДХ на здании: есть, сколько?
5) Соседние здания и их ДХ.
Отвечай ТОЛЬКО JSON: {"shape":"<...>","orient":"<vert|horiz>","ratio":"<...>","roof":"<flat|gable>","state":"<целое|провалы|руины>","antennas":<int>,"porches":<int>,"hh_squares":<int>,"neighbors":"<до 20 слов>"}`, `${DIR}/img_11_4x.png`, 'shape')).v;
console.log(JSON.stringify(results.img_11));

fs.writeFileSync(OUT, JSON.stringify(results, null, 2));
console.log('saved', OUT);
