// 목업 데이터를 앱 안으로 옮긴다. 앱(Metro)은 mobile/ 밖 파일을 읽지 못해서 복사해 둔다.
// - contracts/sample_responses/*.example.json  → src/mocks/data/samples/*.json (서버 예시 응답 그대로)
// - server/db/mock/out/{orders,order_items,menu}.csv → src/mocks/data/orders.json (매출 대시보드용, 작게 줄여서)
// 서버 예시나 주문 목업이 바뀌면 `npm run sync-mocks`를 다시 돌린다.
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..', '..');
const out = path.resolve(import.meta.dirname, '..', 'src', 'mocks', 'data');
mkdirSync(path.join(out, 'samples'), { recursive: true });

const sampleDir = path.join(root, 'contracts', 'sample_responses');
for (const f of readdirSync(sampleDir).filter((x) => x.endsWith('.example.json'))) {
  writeFileSync(path.join(out, 'samples', f.replace('_response.example', '')), readFileSync(path.join(sampleDir, f)));
}

const csv = (name) => {
  const [head, ...rows] = readFileSync(path.join(root, 'server', 'db', 'mock', 'out', name), 'utf8').trim().split(/\r?\n/);
  const keys = head.split(',');
  return rows.map((r) => Object.fromEntries(keys.map((k, i) => [k, r.split(',')[i] ?? ''])));
};
// 주문: [id, 주문 시각(ms), 채널(0 가게, 1 배달), 손님 키(없으면 ""), 금액]
const orders = csv('orders.csv').map((o) => [Number(o.order_id), new Date(o.ordered_at).getTime(), o.channel === 'delivery' ? 1 : 0, o.customer_key, Number(o.total_amount)]);
// 주문 메뉴: [주문 id, 메뉴 id, 개수, 단가]
const items = csv('order_items.csv').map((i) => [Number(i.order_id), Number(i.menu_id), Number(i.quantity), Number(i.unit_price)]);
const menu = Object.fromEntries(csv('menu.csv').map((m) => [m.menu_id, m.name]));
writeFileSync(path.join(out, 'orders.json'), JSON.stringify({ orders, items, menu }));
console.log(`samples ${readdirSync(path.join(out, 'samples')).length}, orders ${orders.length}, items ${items.length}`);
