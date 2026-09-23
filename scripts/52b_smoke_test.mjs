import ZAI from 'z-ai-web-dev-sdk';
import fs from 'fs';
const BASE = '/home/z/my-project';
function extractJson(text) {
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{'), j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}
const PROMPT_AB = fs.readFileSync(BASE + '/work/hh2/_prompt_ab.txt', 'utf8');
const zai = await ZAI.create();
for (const cid of ['A_hh215', 'A_hh107', 'C_b358']) {
  const key = 'prigorodnoe';
  const img = `${BASE}/work/hh2/${key}/cand_${cid}.jpg`;
  if (!fs.existsSync(img)) { console.log(cid, 'нет картинки'); continue; }
  const b64 = fs.readFileSync(img).toString('base64');
  const t0 = Date.now();
  const resp = await zai.chat.completions.createVision({
    messages: [{ role: 'user', content: [
      { type: 'text', text: PROMPT_AB },
      { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } } ] }],
    thinking: { type: 'disabled' } });
  const txt = resp.choices?.[0]?.message?.content || '';
  console.log(`--- ${cid} (${((Date.now()-t0)/1000).toFixed(1)} с):`);
  console.log(txt.slice(0, 300));
  console.log('parsed:', JSON.stringify(extractJson(txt)).slice(0, 250));
}
