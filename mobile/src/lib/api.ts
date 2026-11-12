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
import { account } from "./account";
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

async function request<T>(method: "GET" | "PATCH" | "POST", module: string, query: Record<string, string | undefined> = {}, body?: unknown): Promise<T> {
  if (USE_MOCK) {
    if (method === "POST") throw new ApiFailure("UNKNOWN", "목업에는 없는 요청이에요.");
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
  // 로그인한 계정의 가게 (테스트 계정마다 다른 가게). 없으면 서버가 기본 가게를 보여 준다
  const storeId = account.read().storeId;
  if (storeId && !params.has("store_id")) params.set("store_id", storeId);
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

export type SettingsUpdate = Partial<Pick<StoreSettings, "slots" | "dayparts" | "busy_dayparts" | "open_time" | "close_time" | "closed_weekdays" | "break_time" | "weekly_hours" | "name" | "category" | "work_hours" | "extra_slots">>;

/** 06-2c 네이버 플레이스에서 불러온 가게 정보. 제안 API: GET /api/naver/place */
export interface NaverPlace {
  place_id: string;
  name: string;
  /** 도로명 주소 */
  address: string;
  /** 업종. 예: "돈가스" */
  category: string;
  weekly_hours: NonNullable<StoreSettings["weekly_hours"]>;
  break_time: { start: string; end: string } | null;
  dayparts: StoreSettings["dayparts"];
  busy_dayparts: StoreSettings["busy_dayparts"];
  menus: { name: string; photo: string | null }[];
  photo_count: number;
  review_count: number;
  rating: number;
}

/** 우리 가게 찾기: 네이버 지역 검색 결과 하나. 상호, 업종, 주소, 좌표만 온다 (메뉴, 영업시간, 리뷰는 오지 않는다). GET /api/naver/search */
export interface SearchedPlace {
  name: string;
  category: string;
  address: string;
  jibun_address: string;
  lat: number;
  lng: number;
}

/** 매장 등록 때 네이버 지도에서 읽은 가게 정보 (서버 app/core/naver_place.py PlaceInfo) */
export interface StorePlace {
  place_id: string;
  name: string;
  category: string;
  road_address: string;
  address: string;
  lat: number;
  lng: number;
  weekly_hours: Record<string, { open: string; close: string } | null>;
  break_time: { start: string; end: string } | null;
  menus: { name: string; price: number | null; photo: string | null }[];
  review_total: number;
  closed_note: string | null;
}

/** 리뷰를 불러오는 곳 */
export type ReviewSource = "BAEMIN" | "NAVER" | "COUPANG";

/** 지도 그림 주소 (서버가 네이버 지도 Static Map 을 대신 받아 준다).
 * numbered: 핀에 1, 2, 3 번호 (검색 목록과 같은 번호). selected: 갈색으로 칠할 핀(0부터), -1 이면 모두 */
export function storeMapUrl(o: { lat: number; lng: number; level?: number; markers?: { lat: number; lng: number }[]; w?: number; h?: number; numbered?: boolean; selected?: number }): string {
  const q = new URLSearchParams({ lat: String(o.lat), lng: String(o.lng), level: String(o.level ?? 15), w: String(o.w ?? 640), h: String(o.h ?? 360) });
  if (o.markers?.length) q.set("markers", o.markers.map((m) => `${m.lat},${m.lng}`).join(";"));
  if (o.numbered) q.set("numbered", "true");
  if (o.selected !== undefined) q.set("selected", String(o.selected));
  return `${BASE_URL}/api/stores/map?${q}`;
}

export const api = {
  today: () => get<TodayResponse>("today"),
  plan: (from?: string, to?: string) => get<PlanResponse>("plan", { from, to }),
  calendar: (from?: string, to?: string) => get<CalendarResponse>("calendar", { from, to }),
  reviews: (from?: string, to?: string) => get<ReviewsResponse>("reviews", { from, to }),
  settings: () => get<SettingsResponse>("settings"),
  updateSettings: (update: SettingsUpdate) => request<SettingsResponse>("PATCH", "settings", {}, update),
  naverPlace: () => request<{ is_example: boolean; place: NaverPlace }>("GET", "naver/place"),
  /** 가게 이름으로 네이버 지역 검색 (많아야 5곳) */
  naverSearch: (query: string) => request<{ items: SearchedPlace[] }>("GET", "naver/search", { query }),
  /** 매장 등록: 검색에서 고른 가게를 네이버 지도에서 읽어 보여 준다 (저장 안 함). POST /api/stores/preview */
  storePreview: (p: SearchedPlace) => request<{ place: StorePlace; registered_store_id: string | null }>("POST", "stores/preview", {}, { name: p.name, address: p.address, lat: p.lat, lng: p.lng }),
  /** 매장 등록: 그 가게를 등록한다 (DB 에 저장). 다음 로그인부터 이 계정은 이 가게로 들어온다. POST /api/stores/register */
  storeRegister: (placeId: string, ownerKey?: string) => request<{ store_id: string; place: StorePlace }>("POST", "stores/register", {}, { place_id: placeId, owner_key: ownerKey ?? null }),
  /** 플랫폼별로 불러온 리뷰 수. GET /api/stores/{id}/reviews */
  importedReviews: (storeId: string) => request<{ imported: Record<ReviewSource, number> }>("GET", `stores/${storeId}/reviews`),
  /** 한 플랫폼 리뷰 불러오기 (지금은 목업). POST /api/stores/{id}/reviews/import */
  importReviews: (storeId: string, platform: ReviewSource) =>
    request<{ platform: ReviewSource; imported: number; already: boolean }>("POST", `stores/${storeId}/reviews/import`, {}, { platform }),
  /** 답글 다시 쓰기 (더 짧게 / 더 정중하게). 서버가 CLOVA X로 다시 쓴다. POST /api/replies/rewrite */
  rewriteReply: (text: string, style: "short" | "polite", planId?: string) =>
    request<{ text: string }>("POST", "replies/rewrite", {}, { text, style, plan_id: planId }),
};
