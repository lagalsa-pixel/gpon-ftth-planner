import fs from 'fs';
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
const zai = await ZAI.create();
const b64 = fs.readFileSync('/home/z/my-project/download/snp_vko/altay3_task60_result.jpg').toString('base64');
for (let a=1;a<=5;a++) {
  try {
    const r = await zai.chat.completions.createVision({
      messages: [{ role: 'user', content: [
        { type: 'text', text: `Монтаж-отчёт для заказчика (3 фото в ряд 1, 3 карточки текста в ряд 2). Проверь:
1. Ряд 1, панели 1 и 2 — это ОДНО И ТО ЖЕ место (одинаковая раскладка кабель/муфта/дроп/квадрат)?
2. Панель 3 — виден ли значок МЖД (скруглённый квадрат с полосами и числом «4») на длинном тёмном здании?
3. Текст карточек читаем полностью, ничего не обрезано?
ТОЛЬКО JSON: {"panels_1_2_same": <true|false>, "icon4_visible": <true|false>, "text_ok": <true|false>, "issues": "<до 15 слов>"}` },
        { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } }
      ]}],
      thinking: { type: 'disabled' }
    });
    let t = (r.choices[0].message.content||'').replace(/```json/gi,'```').replace(/```/g,'').trim();
    const i = t.indexOf('{'), j = t.lastIndexOf('}');
    console.log(t.slice(i, j+1));
    break;
  } catch (e) { console.error(`attempt ${a}: ${e.message}`); await new Promise(r2=>setTimeout(r2,4000*a)); }
}
