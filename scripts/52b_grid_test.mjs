import ZAI from 'z-ai-web-dev-sdk';
import fs from 'fs';
const PROMPT = `Спутниковые снимки села (Восточный Казахстан, ~0.4 м/px). Четыре фрагмента, обозначенные буквами A, B, C, D в углах. На каждом красный контур — здание по геоданным, фактически там могут быть НЕСКОЛЬКО строений с разными крышами.
Правила:
- Сблокированные дома разных владельцев строят вплотную с РАЗНЫМИ крышами и межевым забором между участками; забор продолжает линию стыка вглубь двора.
- Пристройка/веранда/гараж примыкает к дому, обычно меньше, без забора между ней и домом.
- Хозпостройки на участке — не отдельные владения.
Для КАЖДОГО фрагмента определи число отдельных владений.
Отвечай ТОЛЬКО JSON без markdown:
{"A": {"n_properties": <int>, "fence_between": <bool>, "roof_colors": ["..."]},
 "B": {...}, "C": {...}, "D": {...}}`;
const zai = await ZAI.create();
const b64 = fs.readFileSync('/home/z/my-project/work/hh2/_test_grid.jpg').toString('base64');
const t0 = Date.now();
const resp = await zai.chat.completions.createVision({
  messages: [{ role: 'user', content: [
    { type: 'text', text: PROMPT },
    { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } } ] }],
  thinking: { type: 'disabled' } });
console.log(`время: ${((Date.now()-t0)/1000).toFixed(1)} с`);
console.log(resp.choices?.[0]?.message?.content);
