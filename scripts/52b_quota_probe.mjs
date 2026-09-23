// Проба VLM-квоты одним дешёвым вызовом (Task 47).
// exit 0 — квота доступна; exit 1 — 429/ошибка.
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
import fs from 'fs';
const img = '/home/z/my-project/work/hh2/vinnoe/cand_A_hh10.jpg';
if (!fs.existsSync(img)) { console.log('PROBE_OK (нет файла пробы, считаем квоту доступной)'); process.exit(0); }
try {
  const zai = await ZAI.create();
  const b64 = fs.readFileSync(img).toString('base64');
  await zai.chat.completions.createVision({
    messages: [{ role: 'user', content: [
      { type: 'text', text: 'Ответь одним словом: OK' },
      { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } } ] }],
    thinking: { type: 'disabled' } });
  console.log('PROBE_OK', new Date().toISOString());
  process.exit(0);
} catch (e) {
  console.log('PROBE_FAIL', String(e).slice(0, 160), new Date().toISOString());
  process.exit(1);
}
