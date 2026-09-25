import fs from 'fs';
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
const BASE = '/home/z/my-project';
function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{'), j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}
async function ask(zai, path, prompt) {
  const b64 = fs.readFileSync(path).toString('base64');
  for (let a = 1; a <= 5; a++) {
    try {
      const r = await zai.chat.completions.createVision({
        messages: [{ role: 'user', content: [
          { type: 'text', text: prompt },
          { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
        ]}],
        thinking: { type: 'disabled' }
      });
      return extractJson(r.choices[0].message.content);
    } catch (e) { console.error(`  attempt ${a}: ${e.message}`); await new Promise(r2 => setTimeout(r2, 4000 * a)); }
  }
  return null;
}
const zai = await ZAI.create();
const r1 = await ask(zai, `${BASE}/work/altay3/t60_facade_6x.png`,
`Спутник 0.19 м/px, 6x. Полоса вдоль южного фасада длинного здания с тёмной крышей (крыша сверху кадра, тень снизу). Длина здания ~30 м.
КРИТЕРИЙ: отдельные входы/крыльца многоквартирного дома выглядят как маленькие светлые/серые прямоугольники или ступеньки, равномерно выступающие из тёмной стены (нижняя кромка крыши) в светлую зону двора, часто с тропинкой.
Посчитай ВНИМАТЕЛЬНО: сколько отдельных выступов-крылец/входов вдоль стены? Есть ли тропинки от них? Есть ли ряд окон (тёмные точки вдоль стены)?
Отвечай ТОЛЬКО JSON: {"n_entrances": <int>, "entrance_x_positions_pct": [<проценты 0-100 вдоль длины>], "paths": "<есть/нет тропинки>", "windows_row": "<есть/нет тёмные точки-окна>", "comment": "<до 15 слов>"}`);
console.log('FACADE:', JSON.stringify(r1));
const r2 = await ask(zai, `${BASE}/work/altay3/t60_facadeN_6x.png`,
`Спутник 0.19 м/px, 6x. Полоса вдоль СЕВЕРНОГО фасада того же здания (светлая сторона). Длина ~30 м.
Сколько отдельных входов/крылец (выступы, ступеньки, серые прямоугольники у стены)? Есть ли строения, пристроенные с севера (веранды, сараи)?
Отвечай ТОЛЬКО JSON: {"n_entrances": <int>, "attached_structures": "<что пристроено>", "comment": "<до 15 слов>"}`);
console.log('NORTH:', JSON.stringify(r2));
