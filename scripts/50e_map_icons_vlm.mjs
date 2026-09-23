import ZAI from 'z-ai-web-dev-sdk';
import fs from 'fs';
const BASE = '/home/z/my-project';
const Q = BASE + '/work/qa/symbology_t50';
const zai = await ZAI.create();
const imgs = ['01_cu_olt.jpg', '02_orsh_1.jpg'];
const content = [{
  type: 'text',
  text: 'Проверка новых условных знаков на карте зон FTTH (снимок со спутника). Изображение 1 — окрестность центрального узла ЦУ/OLT: значок должен представлять собой тёмный бейдж с красной рамкой, внутри здание с крышей, антенна-мачта с сигнальными дугами, красная табличка с текстом OLT. Изображение 2 — окрестность зонного шкафа ОРШ: значок — уличный шкаф (вертикальный корпус с цветной заливкой, белая рамка, вентиляционные щели, белая цифра номера, линия дверец с ручками, тёмный цоколь). Ответь СТРОГО JSON: {"cu_badge_visible": bool, "cu_building_antenna_visible": bool, "cu_olt_text": "текст на табличке или пусто", "cu_label_text": "подпись рядом с ЦУ", "orsh_cabinet_visible": bool, "orsh_number": "какая цифра на шкафе", "orsh_doors_handles_visible": bool, "orsh_label_text": "подпись рядом с ОРШ", "readable_on_satellite": bool, "issues": "кратко проблемы или пусто"}'
}];
for (const f of imgs) {
  const b64 = fs.readFileSync(`${Q}/${f}`).toString('base64');
  content.push({ type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } });
}
const resp = await zai.chat.completions.createVision({
  messages: [{ role: 'user', content }], thinking: { type: 'disabled' } });
console.log(resp.choices?.[0]?.message?.content || '');
