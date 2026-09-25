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
const p1 = await ask(zai, `${BASE}/work/altay3/t60_lv_pair.png`,
`Два здания сельской местности (спутник, 0.19 м/px, 4x). Здание A — длинное горизонтальное с тёмной крышей (~29x13 м). Здание B — длинное вертикальное (~13x40 м), это ИЗВЕСТНЫЙ 2-этажный жилой барак (общежитие) с квартирами.
ВОПРОС: здание A — того же типа и этажности, что B (2-этажный барак), или это 1-этажный дом?
Сравни: высоту крыши (контраст скатов, гребень), длину теней, пропорции, серию крылец/труб.
Отвечай ТОЛЬКО JSON: {"A_type": "<2-эт барак как B | 1-эт дом | иное>", "A_levels": <int>, "confidence": <0-100>, "evidence": "<до 20 слов>"}`);
console.log('PAIR:', JSON.stringify(p1));
const p2 = await ask(zai, `${BASE}/work/altay3/t60_bld_4x.png`,
`Спутник 0.19 м/px, 4x. В центре — длинное здание с почти чёрной крышей на южном скате и светлым северным скатом (двускатная крыша, конёк вдоль длинной оси). Длина ~29 м, ширина ~13 м.
Оцени ТОЧНО: (1) сколько рядов крылец/подъездов вдоль южного фасада (тёмные прямоугольнички/ступеньки у стены), (2) видны ли дымовые трубы на коньке, (3) ширина тёмного ската vs светлого ската (в метрах), (4) этажность.
Отвечай ТОЛЬКО JSON: {"porches": <int>, "porches_where": "<до 8 слов>", "chimneys": <int>, "slope_dark_m": <float>, "slope_light_m": <float>, "levels": <int>, "comment": "<до 12 слов>"}`);
console.log('DETAIL:', JSON.stringify(p2));
