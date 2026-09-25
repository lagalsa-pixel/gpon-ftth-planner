// Task 60n: VLM-описание большого спутникового кропа вокруг hh324
// (квадрат зоны-P0, муфта M4 севернее, дроп 17м) — есть ли там
// вытянутое многоквартирное здание.
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const BASE = '/home/z/my-project';
const PROMPT = `Спутниковый снимок сельской местности (Восточный Казахстан, ~0.19 м/px после 3x увеличения; реальный охват кадра ~76x61 м). Центр кадра — место, где на проектной карте стоит тёмно-синий квадрат домохозяйства, от муфты к нему идёт жёлтый дроп сверху (с севера).
Опиши ВСЕ здания в кадре:
1. Здания вытянутой формы (длинные, баракоподобные): размеры в метрах (примерно), ориентация (горизонтально/вертикально), крыша (секции, цвета торцов/середины), крыльца/подъезды вдоль фасада, антенны.
2. Малые постройки (сараи, гаражи).
3. Дороги, тропы, деревья.
4. Особое внимание: здание, у которого юго-восточный угол находится в ЦЕНТРЕ кадра (там стоит квадрат).
Отвечай ТОЛЬКО JSON:
{"elongated_blds": [{"where": "<позиция в кадре>", "size_m": "<ДxШ>", "orient": "<H|V>", "roof": "<секции и цвета>", "porches": "<есть/нет, где>", "antennas": "<есть/нет>"}], "small_blds": "<сколько и где>", "roads": "<описание>", "trees": "<где>", "center_corner_bld": "<какое здание у центра кадра, форма>", "comment": "<до 20 слов>"}`;

function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{');
  const j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

const zai = await ZAI.create();
const b64 = fs.readFileSync(`${BASE}/work/altay3/t60_hh324_big.png`).toString('base64');
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
