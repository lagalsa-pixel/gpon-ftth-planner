// Task 55s: финальные сфокусированные проходы по 283 и зданию img_12
// (два разных кропа каждое, прямые вопросы о этажности/входах/антеннах)
import fs from 'fs';
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
const DIR = '/home/z/my-project/work/altay2';
const OUT = `${DIR}/vlm_final.json`;
function extractJson(t) {
  if (!t) return null;
  t = t.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{'), j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}
let lastStart = 0, pauseUntil = 0;
async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
async function ask(zai, prompt, imgPath, key) {
  const b64 = fs.readFileSync(imgPath).toString('base64');
  for (let attempt = 1; attempt <= 6; attempt++) {
    const wait = Math.max(lastStart + 3500, pauseUntil) - Date.now();
    if (wait > 0) await sleep(wait);
    lastStart = Date.now();
    try {
      const r = await zai.chat.completions.createVision({
        messages: [{ role: 'user', content: [
          { type: 'text', text: prompt },
          { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }]}],
        thinking: { type: 'disabled' }});
      const js = extractJson(r.choices?.[0]?.message?.content || '');
      if (js && key in js) return js;
      if (attempt === 6) return { parse_error: true };
    } catch (e) {
      pauseUntil = Date.now() + (String(e).includes('429') ? 30000 : 8000);
      if (attempt === 6) return { error: String(e).slice(0, 150) };
    }
  }
}
const zai = await ZAI.create();
const res = {};

// --- 283: два кропа (2x малый контекст, и широкий с соседним бараком 284) ---
const P283 = `Спутниковый снимок села (масштаб укажу: 1 пиксель = 0.19 м). Здание в центре — вытянутое (примерно 29 x 9 м), ориентировано север-юг. Заказчик утверждает, что оно ЖИЛОЕ (в списке с жилыми бараками района).
Ответь строго по изображению:
1) levels: сколько этажей? Признаки 2 этажей: тень высокой стены, два ряда структур на фасаде. Признаки 1: низкая тень, один ряд.
2) porches: сколько отдельных входов (крыльца/навесы/тропинки) вдоль фасада?
3) antennas: сколько ТВ-антенн (тонкие вертикальные мачты с маленькой тенью) на крыше?
4) state: целое/частично разрушено/руины? (провалы крыши, обрушения)
5) roof: плоская/двускатная?
Только JSON: {"levels": <int>, "porches": <int>, "antennas": <int>, "state": "<ok|partial|ruins>", "roof": "<flat|gable>", "conf": <0..1>}`;
res.b283_a = await ask(zai, P283, `${DIR}/base_283_2x.jpg`, 'levels');
console.log('283 a:', JSON.stringify(res.b283_a));
res.b283_b = await ask(zai, P283 + ' (второй ракурс, более широкий кроп)', `${DIR}/shadow_compare.jpg`, 'A');
console.log('283 b:', JSON.stringify(res.b283_b?.A || res.b283_b));

// --- img_12 building: сеточный кроп и широкий ---
const P12 = `Спутниковый снимок села (1 пиксель = 0.19 м в первом случае). Здание между двумя длинными вертикальными бараками — горизонтальное, примерно 30 x 10 м. Заказчик утверждает, что оно ЖИЛОЕ.
Ответь строго по изображению:
1) levels: этажей? (тень стены: у 2-этажного заметно длиннее)
2) porches: отдельных входов вдоль фасада? (крыльца, тропинки, приступки)
3) antennas: ТВ-антенн на крыше? (тонкие мачты с тенью)
4) state: целое/разрушено?
5) type: частный дом (1 семья) / двухквартирный / барак-многоквартирный (4+)?
Только JSON: {"levels": <int>, "porches": <int>, "antennas": <int>, "state": "<ok|partial|ruins>", "type": "<private|duplex|barracks>", "conf": <0..1>}`;
res.b12_a = await ask(zai, P12, `${DIR}/new_bld_grid_4x.jpg`, 'levels');
console.log('12 a:', JSON.stringify(res.b12_a));
res.b12_b = await ask(zai, P12 + ' (широкий кроп с соседними бараками для сравнения теней)', `${DIR}/shadow_compare.jpg`, 'C');
console.log('12 b:', JSON.stringify(res.b12_b?.C || res.b12_b));
res.b12_c = await ask(zai, P12, `${DIR}/base_img12_3x.jpg`, 'levels');
console.log('12 c:', JSON.stringify(res.b12_c));

fs.writeFileSync(OUT, JSON.stringify(res, null, 2));
console.log('saved', OUT);
