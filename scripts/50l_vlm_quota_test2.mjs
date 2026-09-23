let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}
const zai = await ZAI.create();
// 1) чисто текстовый чат (без картинки)
try {
  const r = await zai.chat.completions.create({
    messages: [{ role: 'user', content: 'Ответь одним словом: OK' }]
  });
  console.log('TEXT-OK:', (r.choices[0].message.content || '').slice(0, 30));
} catch (e) {
  console.log('TEXT-FAIL:', String(e.message || e).slice(0, 120));
}
// 2) vision
try {
  const r = await zai.chat.completions.create({
    messages: [{ role: 'user', content: [
      { type: 'text', text: 'Что на картинке? До 5 слов.' },
      { type: 'image_url', image_url: { url: 'https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/300px-PNG_transparency_demonstration_1.png' } }
    ]}],
    model: 'glm-4.5v'
  });
  console.log('VISION-OK:', (r.choices[0].message.content || '').slice(0, 60));
} catch (e) {
  console.log('VISION-FAIL:', String(e.message || e).slice(0, 120));
}
