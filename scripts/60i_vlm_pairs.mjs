// Task 60i: VLM сайд-бай-сайд — скриншот заказчика vs кропы карты вокруг
// всех 8 зона-P0 (синих) дропов Алтайского. Ранкровать совпадение.
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const BASE = '/home/z/my-project';
const FIG = `${BASE}/work/altay3/img_9_p1.png`;

const PROMPT = `Два изображения сельской местности со спутника.
СЛЕВА (рис. 1): скриншот заказчика с карты FTTH: синий горизонтальный кабель вверху, бирюзовая муфта, жёлтый вертикальный дроп вниз к тёмно-синему квадрату; вытянутое здание с многосекционной крышей.
СПРАВА (рис. 2): фрагмент другой карты в том же масштабе.
ЗАДАЧА: определить, ОДНО И ТО ЖЕ ЛИ МЕСТО на двух изображениях.
Сравнивай: (1) форму и секции крыши здания (цвета торцов/середины), (2) взаимное расположение кабеля/муфты/дропа/квадрата, (3) соседние объекты (постройки, деревья, дороги, тропы), (4) ориентацию здания.
Важно: мелкие различия цвета из-за JPEG допустимы; смотри на ГЕОМЕТРИЮ и структуру.
Отвечай ТОЛЬКО JSON:
{"same_place": <true|false|uncertain>, "confidence": <0-100>, "roof_match": "<совпадает/нет по секциям крыши>", "symbology_match": "<совпадает/нет расположение кабель-муфта-дроп-квадрат>", "neighbors_match": "<совпадают/нет соседи>", "differences": "<главные различия, до 20 слов>", "comment": "<до 15 слов>"}`;

function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{');
  const j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

async function ask(zai, imgPath, prompt) {
  const b64 = fs.readFileSync(imgPath).toString('base64');
  for (let attempt = 1; attempt <= 6; attempt++) {
    try {
      const resp = await zai.chat.completions.createVision({
        messages: [{
          role: 'user',
          content: [
            { type: 'text', text: prompt },
            { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
          ]
        }],
        thinking: { type: 'disabled' }
      });
      return extractJson(resp.choices[0].message.content);
    } catch (e) {
      console.error(`  attempt ${attempt}: ${e.message}`);
      await new Promise(r => setTimeout(r, 4000 * attempt));
    }
  }
  return null;
}

const zai = await ZAI.create();
const ids = [324, 51, 105, 120, 201, 204, 256, 297];
const results = {};
for (const id of ids) {
  const pair = `${BASE}/work/altay3/t60_pair_hh${id}.png`;
  if (!fs.existsSync(pair)) {
    console.error(`нет пары ${pair}`);
    continue;
  }
  const r = await ask(zai, pair, PROMPT);
  results[id] = r;
  console.log(`hh${id}: same=${r?.same_place} conf=${r?.confidence} ` +
    `roof=${r?.roof_match} symb=${r?.symbology_match} nb=${r?.neighbors_match}`);
  console.log(`   diff: ${r?.differences}`);
  await new Promise(r2 => setTimeout(r2, 3500));
}
fs.writeFileSync(`${BASE}/work/altay3/t60_vlm_pairs.json`,
  JSON.stringify(results, null, 1));
console.log('saved t60_vlm_pairs.json');
