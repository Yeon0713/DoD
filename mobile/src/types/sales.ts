// 매출 대시보드(Figma 05-70 ~ 05-75) 응답 모양. 서버에 아직 없다. 제안 API는 docs/frontend_mock_and_api_needs.md 3장 R.
// 고정 샘플 모드에서는 /mock-api/sales-board/[part]가 server/db/mock/out의 주문 목업(orders.csv, order_items.csv, menu.csv)을 "지금" 시각까지만 모아서 돌려준다.

export type SalesPeriod = "today" | "week" | "4w" | "month";

/** 05-70 위: 오늘 실시간 */
export interface SalesLive {
  now: string;
  date: string;
  amount: number;
  orders: number;
  /** 주문 1번 평균 */
  avg: number;
  /** 어제 같은 시각까지 */
  yesterdaySame: number;
  /** 지난 4주 같은 요일의 하루 평균 */
  usualDay: number;
  /** 지난 4주 같은 요일, 같은 시각까지 평균 */
  usualSame: number;
  hourly: { hour: number; amount: number; usual: number; state: "past" | "now" | "future" }[];
}

/** 05-70 아래, 05-71: 이번 주와 지난주 */
export interface SalesWeeks {
  weekStart: string;
  days: { date: string; amount: number; last: number; state: "actual" | "now" | "forecast"; reasons: string[]; usual?: number }[];
  /** 이번 주 지금까지 */
  toDate: number;
  /** 지난주 같은 때까지 */
  lastSamePeriod: number;
  lastTotal: number;
  /** 이번 주 지금까지 + 남은 날 예상 */
  forecastTotal: number;
}

/** 05-72 메뉴별 */
export interface SalesMenus {
  period: SalesPeriod;
  from: string;
  to: string;
  items: { name: string; qty: number; amount: number; prevQty: number; prevAmount: number }[];
}

/** 05-73 시간대와 요일 */
export interface SalesTimes {
  period: SalesPeriod;
  from: string;
  to: string;
  dayparts: { key: "LUNCH" | "DINNER" | "NIGHT"; label: string; range: string; amount: number }[];
  /** 요일(0=월 ~ 6=일) × 시간대 하루 평균 */
  grid: { weekday: number; daypart: "LUNCH" | "DINNER" | "NIGHT"; avg: number }[];
}

/** 05-74 어디서, 누가 */
export interface SalesChannels {
  period: SalesPeriod;
  from: string;
  to: string;
  channels: { key: string; label: string; amount: number; orders: number }[];
  /** 배달앱 나눔은 주문 목업에 없어서 주문 번호로 나눈 예시다 */
  platformsSimulated: boolean;
  customers: { regular: { people: number; amount: number }; fresh: { people: number; amount: number }; other: { people: number; amount: number }; unknownOrders: number; unknownAmount: number };
}

/** 05-75 달별 */
export interface SalesMonths {
  months: { month: string; amount: number; orders: number; days: number; partial: boolean; forecast?: number }[];
  avgDaily: number;
  avgOrder: number;
}
