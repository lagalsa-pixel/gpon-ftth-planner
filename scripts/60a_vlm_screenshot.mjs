// Task 60a: свежий VLM-разбор скриншота altay3 (img_9_p1.png, 459x339).
// Заказчик уточнил: здание находится в селе Алтайский. Извлекаем признаки
// без оглядки на вывод Task 59 (ложная идентификация Пригородного).
import fs from 'fs';

let ZAI;
try {
  ZAI = (await import('/home/z/.bun/install/global/node_modules/z-ai-web-dev-sdk/dist/index.js')).default;
} catch {
  ZAI = (await import('z-ai-web-dev-sdk')).default;
}

const BASE = '/home/z/my-project';
const SRC = `${BASE}/work/altay3/img_9_p1.png`;
const SRC2X = `${BASE}/work/altay3/img_9_p1_2x.png`;

const PROMPT = `Кадр из спутниковой карты FTTH-проекта села (Восточный Казахстан). Это скриншот с карты заказчика. На нём видно здание и элементы проекта: синий кабель, бирюзовая муфта, жёлтая линия (дроп), цветной квадрат (домохозяйство), белый пунктир (граница села).
Опиши МАКСИМАЛЬНО ТОЧНО и подробно:
1. ЗДАНИЕ: ориентация (вытянуто горизонтально/вертикально), примерные пропорции, сколько секций крыши и их цвета (рыжие торцы? светлая середина?), ряд крылец/подъездов (сколько, с какой стороны), антенны на крыше, тень (в какую сторону, длина по сравнению с шириной здания), что рядом (двор, постройки, деревья, поле, дорога).
2. СИМВОЛИКА: где проходит синий кабель (сверху/снизу/слева/справа от здания), где муфта (бирюзовый ромб/квадратик) относительно здания, как идёт жёлтый дроп (откуда куда), где цветной квадрат домохозяйства относительно здания (над/под/слева/справа, насколько далеко в пикселях), есть ли на квадрате цифровой бейдж, точный цвет квадрата (тёмно-синий/зелёный/оранжевый/фиолетовый...).
3. ГРАНИЦА СЕЛА: где белый пунктик относительно здания (сверху/снизу, близко/далеко).
4. СОСЕДИ: другие здания в кадре, их положение и тип.
Отвечай ТОЛЬКО JSON без markdown:
{"bld_orient": "<horizontal|vertical>", "bld_ratio": "<например 3:1>", "roof_sections": "<описание секций и цветов>", "porches": "<сколько и где>", "antennas": "<есть/нет, где>", "shadow": "<направление и сравнение>", "surround": "<двор/постройки/деревья/поле/дорога>", "cable_where": "<где кабель>", "coupler_where": "<где муфта>", "drop_path": "<откуда куда идёт жёлтая линия>", "square_where": "<позиция квадрата>", "square_badge": "<есть/нет цифра>", "square_color": "<цвет>", "border_where": "<граница села>", "neighbors": "<соседние здания>", "extra": "<что ещё примечательного>"}`;

function extractJson(text) {
  if (!text) return null;
  let t = text.replace(/```json/gi, '```').replace(/```/g, '').trim();
  const i = t.indexOf('{');
  const j = t.lastIndexOf('}');
  if (i < 0 || j <= i) return null;
  try { return JSON.parse(t.slice(i, j + 1)); } catch { return null; }
}

async function ask(zai, path, prompt) {
  const b64 = fs.readFileSync(path).toString('base64');
  for (let attempt = 1; attempt <= 6; attempt++) {
    try {
      const resp = await zai.chat.completions.createVision({
        messages: [{
          role: 'user',
          content: [
            { type: 'text', text: prompt },
            { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } }
          ]
        }],
        thinking: { type: 'disabled' }
      });
      const txt = resp.choices[0].message.content;
      return extractJson(txt) || { raw: txt };
    } catch (e) {
      console.error(`  attempt ${attempt}: ${e.message}`);
      await new Promise(r => setTimeout(r, 4000 * attempt));
    }
  }
  return null;
}

const zai = await ZAI.create();
// 2x апскейл для деталей
const { execSync } = await import('child_process');
try { execSync(`python3 -c "
from PIL import Image
im = Image.open('${SRC}')
im.resize((im.width*2, im.height*2), Image.LANCZOS).save('${SRC2X}')
print('saved 2x')
"`); } catch (e) { console.error('upscale fail', e.message); }

const r1 = await ask(zai, SRC2X, PROMPT);
console.log('=== 2x analysis ===');
console.log(JSON.stringify(r1, null, 1));
fs.writeFileSync(`${BASE}/work/altay3/t60_screenshot_vlm.json`, JSON.stringify(r1, null, 1));
