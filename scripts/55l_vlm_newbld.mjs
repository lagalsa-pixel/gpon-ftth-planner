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
const b64 = fs.readFileSync(`${DIR}/new_bld_grid_4x.jpg`).toString('base64');
const zai = await ZAI.create();
const PROMPT = `Спутниковый кадр 4x с жёлтой сеткой (шаг 20 px, подписи жёлтым — координаты в px исходного кропа 220x220). В центре — жилого назначения здание (заказчик назвал его жилым). Найди его ТОЧНО.
1) Четыре угла здания (по краям крыши, без пристроек): координаты в px кропа (по сетке, точность +-3 px). Здание горизонтальное вытянутое.
2) Длина и ширина в px.
3) Крыльца/входы: сколько отдельных входов вдоль фасада (1-2 = частный дом, 3+ = барак с квартирами)?
4) ТВ-антенны на крыше: сколько?
5) Пристройки: есть ли, где.
6) Тип: частный дом / барак с квартирами / другое.
Отвечай ТОЛЬКО JSON:
{"corners": [[x,y],[x,y],[x,y],[x,y]], "len_px": <int>, "wid_px": <int>, "porches": <int>, "antennas": <int>, "appendages": "<до 10 слов>", "type": "<private|barracks|other>", "confidence": <0..1>}`;
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
fs.writeFileSync(`${DIR}/new_bld_vlm.json`, JSON.stringify(v, null, 1));
