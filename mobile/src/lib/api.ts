// 모든 데이터 조회는 이 파일 한 곳에서만 한다 (docs/frontend_plan_v4.md 2장).
// EXPO_PUBLIC_USE_MOCK=true(기본)이면 앱 안 목업 서버가 서버와 같은 예시 파일을 돌려주고, false이면 실제 서버를 부른다.
import type {
  ApiError,
  CalendarResponse,
  PlanResponse,
  ReviewsResponse,
  SettingsResponse,
  StoreSettings,
  TodayResponse,
} from "@/types/contract";
import type { SalesChannels, SalesLive, SalesMenus, SalesMonths, SalesPeriod, SalesTimes, SalesWeeks } from "@/types/sales";

import { handleMock } from "@/mocks/server";
import { devFlags } from "./dev";

/** EXPO_PUBLIC_USE_MOCK=false가 아니면 앱 안의 목업 서버(src/mocks/server)를 쓴다. */
export const USE_MOCK = process.env.EXPO_PUBLIC_USE_MOCK !== "false";
const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiFailure extends Error {
  constructor(
    public code: string,
    message: string,
    public offline = false,
  ) {
    super(message);
  }
}

/** 고정 샘플 모드에서 불러오기 화면을 확인하려고 일부러 늦춘다. 개발 화면(/dev)에서 바꿀 수 있다. */
function mockDelay(): number {
  const d = devFlags.read().delay;
  if (d !== null) return d;
  return Number(process.env.EXPO_PUBLIC_MOCK_DELAY_MS ?? 600);
}

/** 웹에서는 브라우저가 알려 주는 연결 상태를 본다. 앱에서는 요청이 실패할 때 끊긴 것으로 친다. */
export function isOffline(): boolean {
  if (USE_MOCK && devFlags.read().offline) return true;
  return typeof navigator !== "undefined" && (navigator as { onLine?: boolean }).onLine === false;
}

const OFFLINE = () => new ApiFailure("OFFLINE", "인터넷이 잠시 끊겼어요.", true);

async function request<T>(method: "GET" | "PATCH", module: string, query: Record<string, string | undefined> = {}, body?: unknown): Promise<T> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, devFlags.read().offline ? 300 : mockDelay()));
    if (isOffline()) throw OFFLINE();
    const res = handleMock(method, module, query, body);
    const json = res.body as T | ApiError;
    if (res.status >= 400 || (json && typeof json === "object" && "error" in json)) {
      const err = (json as ApiError).error ?? { code: "UNKNOWN", message: "잠시 뒤 다시 해 주세요." };
      throw new ApiFailure(err.code, err.message);
    }
    return json as T;
  }
  if (isOffline()) throw OFFLINE();
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined) params.set(k, v);
  const qs = params.toString() ? `?${params}` : "";
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}/api/${module}${qs}`, {
      method,
      headers: { accept: "application/json", ...(body ? { "content-type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw OFFLINE();
  }
  const json = (await res.json()) as T | ApiError;
  if (!res.ok || (json && typeof json === "object" && "error" in json)) {
    const err = (json as ApiError).error ?? { code: "UNKNOWN", message: "잠시 뒤 다시 해 주세요." };
    throw new ApiFailure(err.code, err.message);
  }
  return json as T;
}

const get = <T,>(module: string, query: Record<string, string | undefined> = {}) => request<T>("GET", module, query);

/** 매출 대시보드 (05-70 ~ 05-75). 제안 API: GET /api/sales/{live|weeks|menus|times|channels|months}?now=&period= */
const salesGet = <T,>(part: string, now: Date, period?: SalesPeriod) => request<T>("GET", `sales/${part}`, { now: now.toISOString(), period });
export const salesApi = {
  live: (now: Date) => salesGet<SalesLive>("live", now),
  weeks: (now: Date) => salesGet<SalesWeeks>("weeks", now),
  menus: (now: Date, period: SalesPeriod) => salesGet<SalesMenus>("menus", now, period),
  times: (now: Date, period: SalesPeriod) => salesGet<SalesTimes>("times", now, period),
  channels: (now: Date, period: SalesPeriod) => salesGet<SalesChannels>("channels", now, period),
  months: (now: Date) => salesGet<SalesMonths>("months", now),
};

export type SettingsUpdate = Partial<Pick<StoreSettings, "slots" | "dayparts" | "busy_dayparts" | "open_time" | "close_time" | "closed_weekdays" | "break_time" | "weekly_hours" | "name" | "category">>;

/** 06-2c 네이버 플레이스에서 불러온 가게 정보. 제안 API: GET /api/naver/place */
export interface NaverPlace {
  place_id: string;
  name: string;
  weekly_hours: NonNullable<StoreSettings["weekly_hours"]>;
  break_time: { start: string; end: string } | null;
  dayparts: StoreSettings["dayparts"];
  busy_dayparts: StoreSettings["busy_dayparts"];
  menus: { name: string; photo: string | null }[];
  photo_count: number;
  review_count: number;
  rating: number;
}

export const api = {
  today: () => get<TodayResponse>("today"),
  plan: (from?: string, to?: string) => get<PlanResponse>("plan", { from, to }),
  calendar: (from?: string, to?: string) => get<CalendarResponse>("calendar", { from, to }),
  reviews: (from?: string, to?: string) => get<ReviewsResponse>("reviews", { from, to }),
  settings: () => get<SettingsResponse>("settings"),
  updateSettings: (update: SettingsUpdate) => request<SettingsResponse>("PATCH", "settings", {}, update),
  naverPlace: () => request<{ is_example: boolean; place: NaverPlace }>("GET", "naver/place"),
};
