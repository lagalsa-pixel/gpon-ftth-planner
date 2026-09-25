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
let lastStart = 0;
async function ask(zai, prompt, imgPath) {
  const b64 = fs.readFileSync(imgPath).toString('base64');
  for (let a = 1; a <= 6; a++) {
    const wait = Math.max(lastStart + 3500, 0) - Date.now();
    if (wait > 0) await new Promise(r => setTimeout(r, wait));
    lastStart = Date.now();
    try {
      const r = await zai.chat.completions.createVision({
        messages: [{ role: 'user', content: [
          { type: 'text', text: prompt },
          { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }]}],
        thinking: { type: 'disabled' }});
      const js = extractJson(r.choices?.[0]?.message?.content || '');
      if (js) return js;
    } catch (e) { console.error('err', String(e).slice(0, 90)); await new Promise(r => setTimeout(r, 8000)); }
  }
  return null;
}
const zai = await ZAI.create();
const P = `Фрагмент итоговой карты проекта FTTH (спутник + схема сети: линии=дропы, квадратики=ДХ, крупные квадраты=муфты). Проверь качество подключения зданий:
1) Подключены ли ВСЕ здания на фрагменте? (у каждого есть линии/квадратики ДХ)
2) Есть ли обрывы линий, линии в никуда, висячие концы?
3) Линии идут вдоль дорог/двором без пересечения зданий?
Только JSON: {"all_connected": <true|false>, "breaks": <int>, "issues": "<до 15 слов>", "quality": "<ok|problems>"}`;
const r1 = await ask(zai, P, `${DIR}/verify_map_283.jpg`);
console.log('283:', JSON.stringify(r1));
const r2 = await ask(zai, P, `${DIR}/verify_map_duplex.jpg`);
console.log('duplex:', JSON.stringify(r2));
fs.writeFileSync(`${DIR}/vlm_verify.json`, JSON.stringify({r1, r2}, null, 1));
