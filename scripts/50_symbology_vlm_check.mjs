import ZAI from 'z-ai-web-dev-sdk';
import fs from 'fs';
const BASE = '/home/z/my-project';
const zai = await ZAI.create();
const b64 = fs.readFileSync(BASE + '/work/symbology_preview.png').toString('base64');
const resp = await zai.chat.completions.createVision({
  messages: [{ role: 'user', content: [
    { type: 'text', text: 'Это тест картографических условных знаков. На изображении два типа значков: (1) узел связи ЦУ/OLT — тёмный бейдж с красной рамкой, внутри здание с крышей, антенной-мачтой с сигнальными дугами и красная табличка "OLT"; (2) зонный шкаф ОРШ — вертикальный корпус цвета зоны с белой рамкой, вентиляционными щелями сверху, крупной белой цифрой номера, линией дверец с ручками внизу и тёмным цоколем. Ответь строго JSON: {"olt_building_visible": true/false, "olt_antenna_arcs_visible": true/false, "olt_plate_text": "что написано на красной табличке", "orsh_numbers_visible": [какие цифры различимы], "orsh_doors_handles_visible": true/false, "icons_readable_on_photo": true/false, "problems": "кратко, что не так, либо пустая строка"}' },
    { type: 'image_url', image_url: { url: `data:image/png;base64,${b64}` } } ] }],
  thinking: { type: 'disabled' } });
console.log(resp.choices?.[0]?.message?.content || '');
