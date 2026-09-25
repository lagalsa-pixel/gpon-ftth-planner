// Task 54m: арбитраж — VLM-классификация всех 13 зданий района бараков
// на одном обзорном снимке с подписями. Контекст: известные жилые бараки
// (APT53) прямо в кадре для сравнения.
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const FIGS = '/home/z/my-project/work/altay_remarks';
const OUT = `${FIGS}/t54_vlm_overview.json`;

const PROMPT = `Обзорный спутниковый снимок квартала села (Восточный Казахстан, ~0.19 м/пикс). Жёлтые числа — метки зданий (293, 291, 290, 288, 281, 270, 289, 287, 271, 282, 284, 283, 285).
ИЗВЕСТНО (подтверждено заказчиком): 270, 271, 282, 284, 285, 287 — ЖИЛЫЕ бараки с квартирами (длинные корпуса). 293 — руины без крыши.
КРИТЕРИЙ ЖИЛОГО БАРАКА: ТВ-антенны на крыше (мачты-точки/чёрточки), ряд крылец/подъездов вдоль длинного фасада, тропинки к входам.
ПРОВЕРЬ КАЖДОЕ из остальных зданий: 291, 290, 288, 281, 289, 283.
Сравнивай их с известными бараками (270/271/282/284/285/287) В ЭТОМ ЖЕ СНИМКЕ: одинаковая ли форма, ширина, крыша, есть ли антенны/крыльца.
Отвечай ТОЛЬКО JSON без markdown:
{"291": {"type": "<barracks|private|nonres|ruins>", "antennas": <int>, "porches": <int>, "why": "<до 10 слов>"},
 "290": {...}, "288": {...}, "281": {...}, "289": {...}, "283": {...},
 "comment": "<до 15 слов об общем характере квартала>"}`;

function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{');
  const j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

const zai = await ZAI.create();
const b64 = fs.readFileSync(`${FIGS}/t54_overview_barracks.png`).toString('base64');
let result = null;
for (let attempt = 1; attempt <= 6; attempt++) {
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
    if (js && js['291']) { result = js; break; }
    console.log('попытка', attempt, 'не распарсилось:', txt.slice(0, 150));
  } catch (e) {
    const is429 = String(e).includes('429');
    if (is429) { console.log('[429] пауза 90 c'); await new Promise(r => setTimeout(r, 90000)); }
    else await new Promise(r => setTimeout(r, 5000 * attempt));
  }
}
if (result) {
  fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
  for (const k of ['291', '290', '288', '281', '289', '283']) {
    const v = result[k] || {};
    console.log(`${k}: ${v.type ?? '?'} ant=${v.antennas ?? '?'} porch=${v.porches ?? '?'} | ${v.why ?? ''}`);
  }
  console.log('комментарий:', result.comment);
} else {
  console.log('FAIL');
}
