// Пробник квоты z-ai. Коды выхода: 0 = квота есть, 3 = 429, 1 = другая ошибка.
let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}
const zai = await ZAI.create();
try {
  const r = await zai.chat.completions.create({
    messages: [{ role: 'user', content: 'Ответь одним словом: OK' }]
  });
  console.log('QUOTA_OK');
  process.exit(0);
} catch (e) {
  const s = String(e && e.message || e);
  if (s.includes('429')) { console.log('QUOTA_429'); process.exit(3); }
  console.log('QUOTA_ERR', s.slice(0, 120));
  process.exit(1);
}
