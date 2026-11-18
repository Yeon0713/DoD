// 가입 흐름이 부르는 곳 (이전 앱 mobile/src/lib/api.ts, naverDemo.ts, ownerCheck.ts 에서 옮김).
// 음성 백엔드(8100)가 메인 서버의 /api/auth, /api/naver, /api/stores, /api/owner_check 를 그대로 붙여 두었다 (server/voice/api/account.py).
import { Linking, Platform } from 'react-native';

import { BASE, request } from './api';

/** 진행 막대: 가게 찾기, 가게 확인, 사장님 확인, 가게 정보, 리뷰 불러오기, 브리핑 알림 (그다음 마이크) */
export const STEPS = 6;

/** 가게 찾기: 네이버 지역 검색 결과 하나 */
export type SearchedPlace = { name: string; category: string; address: string; jibun_address: string; lat: number; lng: number };
/** 이 가게가 맞나요? 네이버 지도에서 읽은 가게 */
export type StorePlace = {
  place_id: string; name: string; category: string; road_address: string; address: string; lat: number; lng: number;
  weekly_hours: Record<string, { open: string; close: string } | null>;
  break_time: { start: string; end: string } | null;
  menus: { name: string; price: number | null; photo: string | null }[];
  review_total: number;
  closed_note: string | null;
};
/** 가게 정보 확인: 등록한 가게의 네이버 플레이스 정보 */
export type NaverPlace = {
  place_id: string; name: string; address: string; category: string;
  weekly_hours: Record<string, { open: string; close: string } | null>;
  break_time: { start: string; end: string } | null;
  menus: { name: string; photo: string | null }[];
  photo_count: number; review_count: number; rating: number;
  logo: string | null;
};
export type ReviewSource = 'BAEMIN' | 'NAVER' | 'COUPANG';
export type OwnerCheckInput = { business_no: string; owner_name: string; opened_on: string; document: string | null };
export type OwnerCheckResult = {
  check_id: string; store_id: string; status: 'reviewing' | 'approved' | 'held';
  reason_code: string | null; reason_title: string | null; reason_sub: string | null; seconds_left: number;
};
/** 네이버 로그인으로 받은 것 (GET /api/auth/naver/result/{ticket}) */
export type NaverResult = {
  received: Record<string, string>;
  test: boolean;
  store_id: string | null;
  store_name: string | null;
  test_account: { login_id: string; on_logout: 'reset' | 'keep'; scene_at: string | null } | null;
};

export const WEEKDAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'] as const;
export const WEEKDAY_KO: Record<string, string> = { MON: '월', TUE: '화', WED: '수', THU: '목', FRI: '금', SAT: '토', SUN: '일' };

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

export const join = {
  config: () => request<{ naver_real: boolean; demo_store_id: string }>('/v1/account/config'),
  /** 가입·로그인을 마친 가게로 들어간다 (음성 백엔드에 그 가게가 없으면 메인 데이터로 만든다) */
  enter: (storeId: string) => request<{ store_id: string; name: string; logo_url: string | null }>('/v1/account/enter', json({ store_id: storeId }), 30000),
  ownerStore: (ownerKey: string) => request<{ store_id: string | null; store_name: string | null }>(`/v1/account/owner-store?owner_key=${encodeURIComponent(ownerKey)}`),
  naverResult: (ticket: string) => request<NaverResult>(`/api/auth/naver/result/${encodeURIComponent(ticket)}`),
  testLogout: (loginId: string) => request<{ on_logout: string }>('/api/auth/test/logout', json({ login_id: loginId })),
  testWithdraw: (loginId: string) => request<{ unlinked_store_id: string | null }>('/api/auth/test/withdraw', json({ login_id: loginId })),
  search: (query: string) => request<{ items: SearchedPlace[] }>(`/api/naver/search?query=${encodeURIComponent(query)}`, undefined, 10000),
  /** 네이버 지도에서 가게를 읽는다 (저장 안 함). 10 ~ 20초 걸릴 수 있다 */
  preview: (p: SearchedPlace) =>
    request<{ place: StorePlace; registered_store_id: string | null }>('/api/stores/preview', json({ name: p.name, address: p.address, lat: p.lat, lng: p.lng }), 45000),
  register: (placeId: string, ownerKey: string | null) =>
    request<{ store_id: string; place: StorePlace }>('/api/stores/register', json({ place_id: placeId, owner_key: ownerKey }), 45000),
  place: (storeId: string) => request<{ place: NaverPlace }>(`/api/naver/place?store_id=${storeId}`, undefined, 15000),
  ownerSubmit: (body: OwnerCheckInput & { store_id: string; owner_key: string }) => request<OwnerCheckResult>('/api/owner_check', json(body)),
  ownerResult: (checkId: string) => request<OwnerCheckResult>(`/api/owner_check/${checkId}`),
  ownerSample: (storeId: string) => request<OwnerCheckInput & { trade_name: string }>(`/api/owner_check/sample?store_id=${storeId}`),
  importedReviews: (storeId: string) => request<{ imported: Record<ReviewSource, number> }>(`/api/stores/${storeId}/reviews`),
  importReviews: (storeId: string, platform: ReviewSource) =>
    request<{ platform: ReviewSource; imported: number; already: boolean }>(`/api/stores/${storeId}/reviews/import`, json({ platform }), 20000),
};

/** 지도 그림 (서버가 네이버 지도 Static Map 을 대신 받아 준다). numbered: 핀에 번호, selected: 갈색 핀(0부터) */
export function storeMapUrl(o: { lat: number; lng: number; level?: number; markers?: { lat: number; lng: number }[]; w?: number; h?: number; numbered?: boolean; selected?: number }): string {
  const q = new URLSearchParams({ lat: String(o.lat), lng: String(o.lng), level: String(o.level ?? 15), w: String(o.w ?? 640), h: String(o.h ?? 360) });
  if (o.markers?.length) q.set('markers', o.markers.map((m) => `${m.lat},${m.lng}`).join(';'));
  if (o.numbered) q.set('numbered', 'true');
  if (o.selected !== undefined) q.set('selected', String(o.selected));
  return `${BASE}/api/stores/map?${q}`;
}

/** 네이버 플레이스 사진(pstatic.net)은 서버를 거쳐 받는다. 서버 안 주소(/api/...)는 서버 주소를 붙인다 */
export function placeImage(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  if (url.startsWith('/')) return `${BASE}${url}`;
  if (/^https:\/\/([a-z0-9-]+\.)*pstatic\.net\//.test(url)) return `${BASE}/api/stores/image?url=${encodeURIComponent(url)}`;
  return url;
}

/** 이 탭을 네이버 로그인 창으로 옮긴다 (웹). 마치면 back(이 앱 주소)으로 ?ticket= 또는 ?error= 를 달고 돌아온다. */
export function goToNaverLogin(backPath: string) {
  const back = `${window.location.origin}${backPath}`;
  window.location.assign(`${BASE}/api/auth/naver/start?back=${encodeURIComponent(back)}`);
}

/** 서버가 살아 있는지 (시작 화면 메뉴, 네이버 로그인 전) */
export async function serverUp(ms = 3000): Promise<boolean> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try {
    return (await fetch(`${BASE}/health`, { signal: ctrl.signal })).ok;
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}

const SMARTPLACE_URL = 'https://new.smartplace.naver.com/';
/** 메뉴와 사진은 네이버 플레이스(스마트플레이스)에서 고친다. 도나는 바꾸지 않는다 */
export function openSmartPlace() {
  if (Platform.OS === 'web') window.open(SMARTPLACE_URL, '_blank', 'noopener');
  else void Linking.openURL(SMARTPLACE_URL);
}

/** 이 계정의 열쇠. 같은 계정으로 다시 로그인하면 확인까지 마친 가게로 들어온다 (서버 등록 기록 owners) */
export function ownerKey(s: { naver: { id: string | null } | null; phone: string | null }): string | null {
  if (s.naver?.id) return `naver:${s.naver.id}`;
  return s.phone ? `phone:${s.phone}` : null;
}

/** 가게 찾기 → 확인 → 사장님 확인을 화면끼리 넘기는 것 (새로 고치면 가게 찾기부터) */
export const joinState: { picked: SearchedPlace | null; check: { checkId: string | null; storeId: string | null; storeName: string | null } } = {
  picked: null,
  check: { checkId: null, storeId: null, storeName: null },
};

/** "01012345678" → "010-1234-5678" */
export function formatPhone(digits: string): string {
  const d = digits.replace(/\D/g, '').slice(0, 11);
  if (d.length < 4) return d;
  if (d.length < 8) return `${d.slice(0, 3)}-${d.slice(3)}`;
  const mid = d.length === 10 ? 3 : 4;
  return `${d.slice(0, 3)}-${d.slice(3, 3 + mid)}-${d.slice(3 + mid)}`;
}
export const isPhone = (digits: string) => /^01\d{8,9}$/.test(digits.replace(/\D/g, ''));

const WEIGHTS = [1, 3, 7, 1, 3, 7, 1, 3, 5];
/** 사업자등록번호 10자리 + 마지막 검증 숫자 (국세청 규칙) */
export function isBusinessNo(digits: string): boolean {
  if (!/^\d{10}$/.test(digits)) return false;
  const d = [...digits].map(Number);
  const total = WEIGHTS.reduce((sum, w, i) => sum + d[i] * w, 0) + Math.floor((d[8] * 5) / 10);
  return (10 - (total % 10)) % 10 === d[9];
}
export function formatBusinessNo(digits: string): string {
  if (digits.length <= 3) return digits;
  if (digits.length <= 5) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
}
/** 20210401 → 2021.04.01 */
export function formatDate(digits: string): string {
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}.${digits.slice(4)}`;
  return `${digits.slice(0, 4)}.${digits.slice(4, 6)}.${digits.slice(6)}`;
}
/** 20210401 → 2021-04-01. 없는 날짜면 null */
export function isoDate(digits: string): string | null {
  if (!/^\d{8}$/.test(digits)) return null;
  const iso = `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`;
  const d = new Date(`${iso}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === iso ? iso : null;
}

/** 서버가 돌려보낸 네이버 로그인 오류 → 사장님이 읽을 말 */
export function naverErrorText(code: string): { title: string; sub: string } {
  if (code === 'access_denied') return { title: '네이버 동의를 취소했어요', sub: '다시 하기를 누르면 네이버 화면이 다시 열려요' };
  if (code === 'TICKET_EXPIRED' || code === 'TICKET_NOT_FOUND') return { title: '시간이 지나서 다시 해야 해요', sub: '다시 하기를 눌러 주세요' };
  if (code === 'SERVER_UNREACHABLE') return { title: '도나 서버에 닿지 않아요', sub: '서버가 켜져 있는지 확인하고 다시 하기를 눌러 주세요' };
  if (code === 'NOT_DEMO') return { title: '데모 테스트 모드를 켜 주세요', sub: '네이버 앱 키가 아직 없어서 시작 화면 메뉴에서 데모 테스트 모드를 켜야 네이버로 시작할 수 있어요' };
  return { title: '네이버 로그인을 마치지 못했어요', sub: '잠시 뒤 다시 해 주세요' };
}
