// Task 54s: VLM-контроль отрисовки карты — район трёх бараков 289/290/291.
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const FIGS = '/home/z/my-project/work/altay_remarks';
const OUT = `${FIGS}/t54_vlm_render.json`;

const PROMPT = `Фрагмент карты зон ОРШ сети FTTH (спутниковый фон, село Алтайский). В центре — три длинных здания-барака (вертикальные прямоугольники), между ними другие корпуса.
Проверь для КАЖДОГО из трёх бараков:
1) Подведён ли кабель/дропы (жёлтые/оранжевые линии-пучки) к зданию?
2) Сколько отдельных линий-дропов подходит к каждому бараку (примерно)?
3) Идут ли трассы вдоль улиц/дорог, без обрывов?
4) Руины справа (светлое пятно без крыши) — есть ли к нему дропы? (их быть не должно)
Отвечай ТОЛЬКО JSON без markdown:
{"barracks_top": {"connected": <true|false>, "n_drops": <int>},
 "barracks_middle": {"connected": <true|false>, "n_drops": <int>},
 "barracks_bottom_left": {"connected": <true|false>, "n_drops": <int>},
 "routes_along_roads": <true|false>, "broken_routes": <true|false видимые обрывы>,
 "ruins_drops": <int число дропов к руинам, 0 если нет>,
 "comment": "<до 15 слов>"}`;

function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{');
  const j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

const zai = await ZAI.create();
const b64 = fs.readFileSync(`${FIGS}/t54_map_render_check.png`).toString('base64');
let result = null;
for (let attempt = 1; attempt <= 5; attempt++) {
  try {
    const resp = await zai.chat.completions.createVision({
      messages: [{ role: 'user', content: [
        { type: 'text', text: PROMPT },
        { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
      ]}],
      thinking: { type: 'disabled' }
    });
    const txt = resp.choices?.[0]?.message?.content || '';
    const js = extractJson(txt);
    if (js && 'ruins_drops' in js) { result = js; break; }
  } catch (e) {
    if (String(e).includes('429')) { console.log('[429] пауза 90 c'); await new Promise(r => setTimeout(r, 90000)); }
    else await new Promise(r => setTimeout(r, 5000 * attempt));
  }
}
if (result) {
  fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
  console.log(JSON.stringify(result, null, 1));
} else {
  console.log('FAIL');
}
