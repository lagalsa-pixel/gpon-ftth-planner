import fs from 'fs';
let ZAI;
try { ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default; }
catch { ZAI = (await import('z-ai-web-dev-sdk')).default; }
function extractJson(t) {
  if (!t) return null;
  t = (t||'').replace(/```json/gi,'```').replace(/```/g,'').trim();
  const i = t.indexOf('{'), j = t.lastIndexOf('}');
  if (i<0||j<=i) return null;
  try { return JSON.parse(t.slice(i,j+1)); } catch { return null; }
}
const zai = await ZAI.create();
const b64 = fs.readFileSync('/home/z/my-project/work/altay3/t60_map_context.png').toString('base64');
for (let a=1;a<=5;a++) {
  try {
    const r = await zai.chat.completions.createVision({
      messages: [{ role: 'user', content: [
        { type: 'text', text: `Фрагмент карты FTTH (спутник + символика). Здесь должно быть: длинное тёмное здание запад-восток; на нём — ЗНАЧОК МЖД: скруглённый квадрат цвета зоны с 3 белыми горизонтальными полосами и тёмным бейджем с ЧИСЛОМ квартир; дропы и отдельные квадраты ДХ под значком СКРЫТЫ; рядом муфта (бирюзовый квадрат) и кабель.
Проверь и ответь ТОЛЬКО JSON:
{"icon_present": <true|false>, "icon_badge_number": <число или null>, "stripes": <сколько белых полос>, "hidden_drops_visible": <true|false видно ли пачку жёлтых дропов/квадратов прямо под значком>, "coupler_nearby": <true|false>, "anomalies": "<до 15 слов>"}` },
        { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
      ]}],
      thinking: { type: 'disabled' }
    });
    console.log(JSON.stringify(extractJson(r.choices[0].message.content), null, 1));
    break;
  } catch (e) { console.error(`attempt ${a}: ${e.message}`); await new Promise(r2=>setTimeout(r2,4000*a)); }
}
