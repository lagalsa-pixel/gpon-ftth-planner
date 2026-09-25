// Task 54o: решающие 4x-пары «эталон | подозреваемый» без контуров
// (контур перекрывал антенны). Финальный вердикт по 289/290/291/283/295.
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const FIGS = '/home/z/my-project/work/altay_remarks';
const OUT = `${FIGS}/t54_vlm_x4.json`;

const PAIRS = [637127289, 637127290, 637127291, 637127283];
const SOLO = 637127295;

const PROMPT_PAIR = `Сверхкрупный вид сверху (4x, ~0.05 м/пикс) на ДВА здания села. Панель A (слева) — жилой барак с квартирами (эталон). Панель B (справа) — проверяемое.
На 4x ТВ-антенны видны как чёткие тонкие линии/крестики/точки с маленькой тенью на крыше. Крыльца/подъезды — прямоугольные выступы или навесы у края + тропинки/протоптанности.
Сравни B с A МЕТОДИЧНО: 1) антенны (число на A и на B), 2) крыльца/входы (число на A и на B), 3) структура крыши (конёк, плоская, световые фонари), 4) состояние (жилое/заброшено).
Отвечай ТОЛЬКО JSON без markdown:
{"A_antennas": <int>, "B_antennas": <int>, "A_porches": <int>, "B_porches": <int>, "B_roof": "<flat|gable|other>", "B_same_type": <true|false B такой же жилой барак>, "B_levels": <int>, "B_verdict": "<barracks|private|nonres|ruins>", "why": "<до 15 слов>"}`;

const PROMPT_SOLO = `Сверхкрупный вид сверху (4x, ~0.05 м/пикс) на здание села. Опиши его МЕТОДИЧНО: 1) ТВ-антенны на крыше (тонкие мачты-линии/крестики с тенью) — сколько и где, 2) крыльца/входы — сколько, с какой стороны, 3) крыша (плоская/двускатная/сложная), 4) этажность (по структуре, люкам, окнам), 5) двор (протоптанные тропинки? машины? склад? техника?), 6) назначение.
Отвечай ТОЛЬКО JSON без markdown:
{"antennas": <int>, "porches": <int>, "roof": "<flat|gable|complex>", "levels": <int>, "yard": "<жилой с тропинками|складской|пустой|другое>", "verdict": "<barracks|private|nonres|ruins|admin>", "why": "<до 15 слов>"}`;

function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{');
  const j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

let lastStart = 0, pauseUntil = 0;
const MIN_INTERVAL_MS = 3500;
async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function ask(zai, prompt, imgPath, key) {
  const b64 = fs.readFileSync(imgPath).toString('base64');
  for (let attempt = 1; attempt <= 6; attempt++) {
    const wait = Math.max(lastStart + MIN_INTERVAL_MS, pauseUntil) - Date.now();
    if (wait > 0) await sleep(wait);
    lastStart = Date.now();
    try {
      const resp = await zai.chat.completions.createVision({
        messages: [{ role: 'user', content: [
          { type: 'text', text: prompt },
          { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
        ]}],
        thinking: { type: 'disabled' }
      });
      const txt = resp.choices?.[0]?.message?.content || '';
      const js = extractJson(txt);
      if (js && key in js) return { ok: true, v: js };
      if (attempt === 6) return { ok: false, parse_error: true, raw: txt.slice(0, 200) };
    } catch (e) {
      const is429 = String(e).includes('429');
      if (is429) { pauseUntil = Math.max(pauseUntil, Date.now() + 90000); console.log(`[429] пауза`); }
      if (attempt === 6) return { ok: false, error: String(e).slice(0, 160) };
      await sleep((is429 ? 20000 : 4000) * attempt);
    }
  }
  return { ok: false, error: 'unreachable' };
}

const zai = await ZAI.create();
const results = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT)) : {};

for (const id of PAIRS) {
  if (results['pair_' + id]?.ok) { console.log(`${id}: есть`); continue; }
  const r = await ask(zai, PROMPT_PAIR, `${FIGS}/t54_x4_pair_${id}.png`, 'B_verdict');
  results['pair_' + id] = r;
  fs.writeFileSync(OUT + '.tmp', JSON.stringify(results, null, 1));
  fs.renameSync(OUT + '.tmp', OUT);
  const v = r.v || {};
  console.log(`${id}: A_ant=${v.A_antennas ?? '?'} B_ant=${v.B_antennas ?? '?'} `
    + `A_porch=${v.A_porches ?? '?'} B_porch=${v.B_porches ?? '?'} `
    + `same=${v.B_same_type ?? '?'} lv=${v.B_levels ?? '?'} -> ${v.B_verdict ?? '?'} | ${v.why ?? 'FAIL'}`);
}

if (!results['solo_' + SOLO]?.ok) {
  const r = await ask(zai, PROMPT_SOLO, `${FIGS}/t54_x4_solo_${SOLO}.png`, 'verdict');
  results['solo_' + SOLO] = r;
  fs.writeFileSync(OUT + '.tmp', JSON.stringify(results, null, 1));
  fs.renameSync(OUT + '.tmp', OUT);
  const v = r.v || {};
  console.log(`${SOLO}: ant=${v.antennas ?? '?'} porch=${v.porches ?? '?'} ${v.roof ?? '?'} `
    + `lv=${v.levels ?? '?'} yard=${v.yard ?? '?'} -> ${v.verdict ?? '?'} | ${v.why ?? 'FAIL'}`);
}
console.log('->', OUT);
