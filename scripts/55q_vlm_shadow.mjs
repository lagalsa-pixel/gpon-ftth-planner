import fs from 'fs';
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
const DIR = '/home/z/my-project/work/altay2';
function extractJson(t) {
  if (!t) return null;
  t = t.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{'), j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}
const b64 = fs.readFileSync(`${DIR}/shadow_compare.jpg`).toString('base64');
const zai = await ZAI.create();
const PROMPT = `Четыре фрагмента спутникового снимка села (один масштаб, 3x). B — эталон: 2-этажный жилой барак. D — эталон: 1-этажный частный дом. A и C — проверяемые здания.
Сравни ВЫСОТУ зданий A и C с эталонами по длине тени (тень от солнца одного момента, чем выше здание — тем длиннее тень), по высоте стены на краю крыши, структуре крыши.
Также для A и C: число отдельных входов (крылец с тропинками) вдоль фасада, ТВ-антенн (тонкие мачты с тенью), состояние.
Отвечай ТОЛЬКО JSON:
{"A": {"levels": <1|2>, "shadow_vs_B": "<короче|такая же|длиннее>", "porches": <int>, "antennas": <int>, "state": "<ok|ruins>"},
 "C": {"levels": <1|2>, "shadow_vs_B": "<короче|такая же|длиннее>", "porches": <int>, "antennas": <int>, "state": "<ok|ruins>"},
 "C_is": "<private_house|duplex|barracks>",
 "confidence": <0..1>, "why": "<до 20 слов>"}`;
let v = null;
for (let a = 1; a <= 6 && !v; a++) {
  try {
    const r = await zai.chat.completions.createVision({
      messages: [{ role: 'user', content: [
        { type: 'text', text: PROMPT },
        { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }]}],
      thinking: { type: 'disabled' }});
    v = extractJson(r.choices?.[0]?.message?.content || '');
    if (!v) console.log('attempt', a, 'parse fail');
  } catch (e) { console.error('err', String(e).slice(0, 100)); await new Promise(r => setTimeout(r, 8000)); }
}
console.log(JSON.stringify(v, null, 1));
fs.writeFileSync(`${DIR}/shadow_verdict.json`, JSON.stringify(v, null, 1));
