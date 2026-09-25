// Task 60t: VLM-анализ этажности здания (4x кроп) + сравнение теней.
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const BASE = '/home/z/my-project';
const PROMPT = `Спутниковый снимок (Восточный Казахстан, 0.19 м/px, увеличение 4x; охват кропа ~68x61 м). В ЦЕНТРЕ — длинное здание с тёмной (тёмно-серой/почти чёрной) крышей, вытянутое запад-восток (~29x13 м). Рядом на западе — похожее длинное здание (вертикальное). Вокруг — частные дома с двускатными крышами.
ЗАДАЧА: оценить ЭТАЖНОСТЬ центрального здания с тёмной крышей.
Признаки 2 этажей (барак/общежитие): длинная тень (заметно длиннее, чем у 1-эт соседей), высокая двускатная крыша (заметный гребень, светлый/тёмный скат), приземистая but массивная, ряд труб/крылец.
Признаки 1 этажа: тень как у соседей, низкая крыша.
Сравни длину тени центрального здания (южная сторона, тень падает на юг) с тенями соседних 1-этажных домов. Посмотри на структуру крыши: виден ли гребень (светлая полоса сверху, тёмный южный скат)?
Отвечай ТОЛЬКО JSON:
{"levels": <int 1|2>, "confidence": <0-100>, "shadow_cmp": "<тень центрального vs соседей: длиннее/такая же/короче, во сколько раз примерно>", "roof_structure": "<описание: гребень, скаты>", "porches_pipes": "<крыльца/трубы вдоль южного фасада: сколько>", "comment": "<до 15 слов>"}`;

function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{');
  const j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

const zai = await ZAI.create();
const b64 = fs.readFileSync(`${BASE}/work/altay3/t60_bld_4x.png`).toString('base64');
for (let a = 1; a <= 5; a++) {
  try {
    const resp = await zai.chat.completions.createVision({
      messages: [{ role: 'user', content: [
        { type: 'text', text: PROMPT },
        { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
      ]}],
      thinking: { type: 'disabled' }
    });
    console.log(JSON.stringify(extractJson(resp.choices[0].message.content), null, 1));
    break;
  } catch (e) {
    console.error(`attempt ${a}: ${e.message}`);
    await new Promise(r => setTimeout(r, 4000 * a));
  }
}
