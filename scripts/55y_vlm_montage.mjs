import fs from 'fs';
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
const b64 = fs.readFileSync('/home/z/my-project/download/snp_vko/altay2_task55_result.jpg').toString('base64');
const zai = await ZAI.create();
const P = `Монтаж-отчёт проекта FTTH: верхний ряд — 4 фрагмента от заказчика, нижний ряд — те же места на обновлённой карте со схемой сети. Проверь: 1) колонки соответствуют друг другу (одни и те же здания сверху и снизу)? 2) на нижних кропах видны линии подключений и точки ДХ у зданий? 3) читабельны подписи? 4) артефакты/пустые ячейки?
Только JSON: {"columns_match": <true|false>, "drops_visible": <true|false>, "labels_ok": <true|false>, "artifacts": "<до 15 слов>", "verdict": "<ok|fix>"}`;
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
