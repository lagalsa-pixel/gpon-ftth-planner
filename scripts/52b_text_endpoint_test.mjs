// Тест: принимает ли ТЕКСТОВЫЙ эндпоинт (/chat/completions) image_url-контент,
// и не заблокирован ли он 429 (у vision-эндпоинта отдельный лимит?).
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
import fs from 'fs';
const zai = await ZAI.create();
const b64 = fs.readFileSync('/home/z/my-project/work/hh2/vinnoe/cand_A_hh10.jpg').toString('base64');
const msg = [{ role: 'user', content: [
  { type: 'text', text: 'Есть ли на спутниковом снимке строение в красном контуре? Ответь JSON: {"seen": true|false}' },
  { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } } ] }];
// 1) текстовый эндпоинт с картинкой
try {
  const r1 = await zai.chat.completions.create({ messages: msg, thinking: { type: 'disabled' } });
  console.log('TEXT+IMG OK:', JSON.stringify(r1.choices?.[0]?.message?.content || r1).slice(0, 200));
} catch (e) { console.log('TEXT+IMG ERR:', String(e).slice(0, 200)); }
// 2) чистый текст (контроль канала)
try {
  const r2 = await zai.chat.completions.create({ messages: [{ role: 'user', content: 'ответь одним словом OK' }], thinking: { type: 'disabled' } });
  console.log('TEXT OK:', JSON.stringify(r2.choices?.[0]?.message?.content || r2).slice(0, 120));
} catch (e) { console.log('TEXT ERR:', String(e).slice(0, 200)); }
