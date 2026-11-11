// 모든 데이터 조회는 이 파일 한 곳에서만 한다 (docs/frontend_plan_v4.md 2장).
// NEXT_PUBLIC_USE_MOCK=true(기본)이면 서버와 같은 예시 파일을, false이면 실제 서버를 부른다.
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

export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false";
const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiFailure extends Error {
  constructor(
    public code: string,
    message: string,
    public offline = false,
  ) {
    super(message);
  }
}

/** 고정 샘플 모드에서 불러오기 화면을 확인하려고 일부러 늦춘다. 주소에 ?delay=4000 처럼 줄 수 있다. */
function mockDelay(): number {
  if (typeof window === "undefined") return 0;
  const q = new URLSearchParams(window.location.search).get("delay");
  if (q !== null) return Number(q) || 0;
  const saved = localStorage.getItem("dona.delay");
  if (saved !== null) return Number(saved) || 0;
  return Number(process.env.NEXT_PUBLIC_MOCK_DELAY_MS ?? 600);
}

async function request<T>(method: "GET" | "PATCH", module: string, query: Record<string, string | undefined> = {}, body?: unknown, mockModule?: string): Promise<T> {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    throw new ApiFailure("OFFLINE", "인터넷이 잠시 끊겼어요.", true);
  }
  // 고정 샘플 모드에서 ?offline=1 이면 인터넷이 끊긴 화면(04-9, 04-7E)을 본다.
  if (USE_MOCK && typeof window !== "undefined" && new URLSearchParams(window.location.search).get("offline") === "1") {
    await new Promise((r) => setTimeout(r, 300));
    throw new ApiFailure("OFFLINE", "인터넷이 잠시 끊겼어요.", true);
  }
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined) params.set(k, v);
  const qs = params.size ? `?${params}` : "";
  // 고정 샘플 길은 대부분 조건을 무시하지만, 매출 대시보드(mockModule)는 now와 기간을 쓴다.
  const url = USE_MOCK ? `/mock-api/${mockModule ?? module}${mockModule ? qs : ""}` : `${BASE_URL}/api/${module}${qs}`;

  let res: Response;
  try {
    if (USE_MOCK) await new Promise((r) => setTimeout(r, mockDelay()));
    res = await fetch(url, {
      method,
      headers: { accept: "application/json", ...(body ? { "content-type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiFailure("OFFLINE", "인터넷이 잠시 끊겼어요.", true);
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
const salesGet = <T,>(part: string, now: Date, period?: SalesPeriod) =>
  request<T>("GET", `sales/${part}`, { now: now.toISOString(), period }, undefined, `sales-board/${part}`);
export const salesApi = {
  live: (now: Date) => salesGet<SalesLive>("live", now),
  weeks: (now: Date) => salesGet<SalesWeeks>("weeks", now),
  menus: (now: Date, period: SalesPeriod) => salesGet<SalesMenus>("menus", now, period),
  times: (now: Date, period: SalesPeriod) => salesGet<SalesTimes>("times", now, period),
  channels: (now: Date, period: SalesPeriod) => salesGet<SalesChannels>("channels", now, period),
  months: (now: Date) => salesGet<SalesMonths>("months", now),
};

export type SettingsUpdate = Partial<Pick<StoreSettings, "slots" | "dayparts" | "busy_dayparts" | "open_time" | "close_time" | "closed_weekdays" | "break_time">>;

export const api = {
  today: () => get<TodayResponse>("today"),
  plan: (from?: string, to?: string) => get<PlanResponse>("plan", { from, to }),
  calendar: (from?: string, to?: string) => get<CalendarResponse>("calendar", { from, to }),
  reviews: (from?: string, to?: string) => get<ReviewsResponse>("reviews", { from, to }),
  settings: () => get<SettingsResponse>("settings"),
  updateSettings: (update: SettingsUpdate) => request<SettingsResponse>("PATCH", "settings", {}, update),
};
