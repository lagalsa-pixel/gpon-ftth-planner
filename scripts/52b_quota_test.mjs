let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
import fs from 'fs';
const zai = await ZAI.create();
const img = '/home/z/my-project/work/hh2/vinnoe/cand_A_hh10.jpg';
const b64 = fs.readFileSync(img).toString('base64');
const t0 = Date.now();
try {
  const resp = await zai.chat.completions.createVision({
    messages: [{ role: 'user', content: [
      { type: 'text', text: 'Спутниковый снимок. Есть ли красный контур строения? Ответь JSON: {"seen": true|false}' },
      { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } } ] }],
    thinking: { type: 'disabled' } });
  console.log('OK', ((Date.now()-t0)/1000).toFixed(1)+'с', (resp.choices?.[0]?.message?.content||'').slice(0,120));
} catch (e) { console.log('ERR', String(e).slice(0,300)); }
