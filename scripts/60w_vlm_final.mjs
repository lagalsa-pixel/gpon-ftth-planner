import fs from 'fs';
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{'), j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}
const zai = await ZAI.create();
const b64 = fs.readFileSync('/home/z/my-project/work/altay3/t60_bld_5x_wide.png').toString('base64');
for (let a = 1; a <= 5; a++) {
  try {
    const r = await zai.chat.completions.createVision({
      messages: [{ role: 'user', content: [
        { type: 'text', text: `Спутниковый снимок (0.19 м/px, 5x). В центре — длинное здание (~30x14 м) вытянутое запад-восток: северный скат крыши светлее, южный почти чёрный, южный фасад в тени. Слева (запад) — вертикальное длинное здание (известный 2-этажный барак). Вокруг — дворы, сараи.
Ответь максимально точно, без предположений:
1. Сколько РЯДОВ окон различимо вдоль южной стены центрального здания? (2-этажный барак показал бы два ряда тёмных точек на южной стене; 1-этажный — один ряд или ничего различимого)
2. Есть ли на южной стене различимая горизонтальная линия межэтажного перекрытия?
3. Крыльца/входы: сколько отдельных выступов вдоль южной стены?
4. Сравни ВЫСОТУ центрального здания и 2-эт барака слева по длине тени и структуре крыши.
5. Итог: этажность центрального здания.
ТОЛЬКО JSON: {"window_rows": <int 0-2>, "floor_line": "<есть/нет>", "n_entrances": <int>, "vs_2fl_barrack": "<выше/такая же/ниже/неясно>", "levels": <int>, "confidence": <0-100>, "why": "<до 20 слов>"}` },
        { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
      ]}],
      thinking: { type: 'disabled' }
    });
    console.log(JSON.stringify(extractJson(r.choices[0].message.content), null, 1));
    break;
  } catch (e) { console.error(`attempt ${a}: ${e.message}`); await new Promise(r2 => setTimeout(r2, 4000 * a)); }
}
