import ZAI from 'z-ai-web-dev-sdk';
import fs from 'fs';
const PROMPT = `Спутниковые снимки села (Восточный Казахстан, ~0.4 м/px). ДВА фрагмента: FRAGMENT 1 (TOP, верхняя половина) и FRAGMENT 2 (BOTTOM, нижняя половина). На каждом красный контур — здание по геоданным, фактически там могут быть НЕСКОЛЬКО строений с разными крышами.
Правила:
- Сблокированные дома разных владельцев строят вплотную с РАЗНЫМИ крышами (цвет/материал) и межевым забором между участками; забор продолжает линию стыка строений вглубь двора.
- Пристройка/веранда/гараж примыкает к дому, обычно меньше, без забора.
- Хозпостройки (сараи) — не отдельные владения.
Для КАЖДОГО фрагмента отдельно определи число владений.
Отвечай ТОЛЬКО JSON без markdown:
{"fragment1": {"n_properties": <int>, "fence_between": <bool>, "fence_extends": <bool>, "roof_colors": ["..."]},
 "fragment2": {...}}`;
const zai = await ZAI.create();
const b64 = fs.readFileSync('/home/z/my-project/work/hh2/_test_stack2.jpg').toString('base64');
const t0 = Date.now();
const resp = await zai.chat.completions.createVision({
  messages: [{ role: 'user', content: [
    { type: 'text', text: PROMPT },
    { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } } ] }],
  thinking: { type: 'disabled' } });
console.log(`время: ${((Date.now()-t0)/1000).toFixed(1)} с`);
console.log(resp.choices?.[0]?.message?.content);
