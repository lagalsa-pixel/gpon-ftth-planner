import fs from 'fs';
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
const b64 = fs.readFileSync('/home/z/my-project/work/altay2/south_check_3x.jpg').toString('base64');
const zai = await ZAI.create();
const P = `Спутниковый снимок села (3x). Перечисли ВСЕ постройки: для каждой — тип (жилой дом / сарай / гараж / баня / руины), примерный размер, признаки жилья (крыльцо, тропинки, огород, машина, антенна). 
Только JSON: {"buildings": [{"type": "...", "size_m": "...", "signs": "..."}], "any_residential": <true|false>}`;
for (let a = 1; a <= 5; a++) {
  try {
    const r = await zai.chat.completions.createVision({
      messages: [{ role: 'user', content: [
        { type: 'text', text: P },
        { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }]}],
      thinking: { type: 'disabled' }});
    const t = r.choices?.[0]?.message?.content || '';
    const i = t.indexOf('{'), j = t.lastIndexOf('}');
    if (i >= 0) { console.log(t.slice(i, j+1)); break; }
  } catch (e) { console.error('err', String(e).slice(0, 90)); await new Promise(r => setTimeout(r, 8000)); }
}
