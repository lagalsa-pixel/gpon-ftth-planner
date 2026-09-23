// Быстрый тест квоты VLM (1 минимальный запрос)
let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}
const zai = await ZAI.create();
const t0 = Date.now();
try {
  const r = await zai.chat.completions.create({
    messages: [
      { role: 'user', content: [
        { type: 'text', text: 'Ответь одним словом: OK' }
      ]}
    ],
    model: 'glm-4.5v'
  });
  console.log('SUCCESS', Date.now()-t0, 'ms:', r.choices[0].message.content.slice(0,50));
} catch (e) {
  console.log('FAIL', Date.now()-t0, 'ms:', e.status || '', String(e.message || e).slice(0,200));
}
