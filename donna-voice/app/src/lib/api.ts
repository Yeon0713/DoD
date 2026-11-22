// 서버와 주고받는 곳은 이 파일 하나다. 모양은 docs/v0.2.0-voice-agent-handoff.md 4 ~ 5장, 17장(v0.2.1 화면 포맷).
import { staffSession } from './staffSession';

export const BASE = (process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8100').replace(/\/$/, '');
/** 지금 보고 있는 가게. 로그인한 계정의 가게로 바뀐다 (lib/session.tsx). 로그인 전에는 시연 가게(초옹장). */
export const DEMO_STORE_ID = 's005';
let currentStore = DEMO_STORE_ID;
export const setStoreId = (id: string | null | undefined) => {
  currentStore = id || DEMO_STORE_ID;
};
export const storeId = () => currentStore;
/** 서버가 준 그림 주소 (/static/...)를 쓸 수 있는 주소로. */
export const media = (url: string | null | undefined) => (!url ? null : /^https?:/.test(url) ? url : `${BASE}${url}`);

export type RowKind =
  | 'event' | 'game' | 'reservation' | 'group_reservation' | 'schedule' | 'reviews' | 'scheduled_replies'
  | 'reply' | 'briefing' | 'off' | 'done'
  // v0.2.1
  | 'weather' | 'instagram' | 'staff' | 'person' | 'task' | 'ban' | 'warning' | 'time' | 'date' | 'phone'
  | 'lock' | 'message' | 'invite' | 'image' | 'users' | 'clock';

/** v0.2.1부터 줄에는 이름표(label)가 없다. value 하나로 읽힌다. title 은 '오늘 아침에 한 것' 같은 카드 제목. */
/** sub: 끝 화면 줄 아래 '9:04에 스토리에 올렸어요' (H-12b). note: 카드 아래 '✓ 알바생 할 일에 넣음' (H-12) */
export type RowsCard = { type: 'rows'; id: string; title?: string; note?: string; rows: { id: string; kind: RowKind; label?: string; value: string; sub?: string }[] };
export type CountsCard = { type: 'counts'; id: string; items: { id: string; kind: 'positive' | 'negative'; label: string; count: number; unit: string }[] };
export type ReviewCard = {
  type: 'review'; id: string; variant: 'summary' | 'full'; rating: number; text: string; written_at: string;
  /** removed: 사장님 말대로 빼고 올린 문장 (줄을 그어 뒤에 보인다, Figma J-10b) */
  reply: { text: string; posted_at: string | null; by: 'donna' | 'owner'; scheduled_label?: string | null; removed?: string | null } | null;
};
export type TipCard = { type: 'tip'; id: string; kind: 'improve' | 'keep' | 'prepare'; text: string };
export type BarsCard = { type: 'bars'; id: string; unit: string; title?: string; items: { id: string; label: string; count: number }[] };
/** weekday_to_weekend: 평일 손님 리뷰 → 토요일 오전, weekend_next_peak: 주말 손님 리뷰 → 24~48시간 안 식사 피크 한 시간 전 (2026-11-18) */
export type ReasonKind = 'weather' | 'game' | 'event' | 'weekend' | 'season' | 'reservation' | 'lunch' | 'weekday_to_weekend' | 'weekend_next_peak';
export type ScheduledCard = {
  type: 'scheduled'; id: string;
  items: { id: string; day_label: string; time_label: string; post_at: string; reason: { kind: ReasonKind; label: string }; text: string }[];
};
/** 이번 달 많이 나간 메뉴 (D-03, D-14). editable 이면 '바꾸기'가 붙는다. */
export type MenusCard = { type: 'menus'; id: string; title?: string | null; editable?: boolean; items: { id: string; rank: number; name: string; count_label: string; photo_url: string }[] };
export type QuoteCard = { type: 'quote'; id: string; label: string; text: string };
/** 인스타 게시물 모양 그대로 (D-15). */
export type InstaPostCard = { type: 'insta_post'; id: string; handle: string; logo_url: string; slide: number; slides: number; photo_url: string | null; top_label: string; title: string; caption: string };
/** 그림 여러 장을 나란히 (비 오는 날 이벤트: 포스터, 스토리에 올릴 사진). aspect 는 '가로:세로' (예: '9:16'), 그림이 잘리지 않게 그 비율로 보인다. */
/** checked: 올린 뒤 '✓ 스토리에 올림' (H-07) */
export type ImagesCard = { type: 'images'; id: string; items: { id: string; label: string; photo_url: string; aspect?: string; checked?: boolean }[] };
/** 예약해 둔 좋은 리뷰 답글: 리뷰 한 줄과 답글 (H-09) */
export type ReplyListCard = { type: 'reply_list'; id: string; items: { id: string; quote: string; reply: string }[] };
/** 알바생에게 시킨 것 (D-24, D-33). state: todo / done / canceled */
/** tone urgent: 아쉬운 리뷰에서 나온 알바생 교정 카드 (2026-11-18) */
export type ChecklistCard = { type: 'checklist'; id: string; title: string; items: { id: string; title: string; sub: string; state: 'todo' | 'done' | 'canceled'; tone?: 'urgent' }[] };
export type PeopleCard = { type: 'people'; id: string; title: string; items: { id: string; name: string; sub: string }[] };
export type InviteCard = { type: 'invite'; id: string; message: string; url: string; code: string };
export type ManualCard = { type: 'manual'; id: string; groups: { id: string; kind: 'before_open' | 'open' | 'closing'; label: string; text: string }[] };
/** 말로 할 수 없는 한 번의 일 (D-01 인스타 연결). */
export type ActionCard = { type: 'action'; id: string; label: string; action: 'instagram_connect' };
export type Card =
  | RowsCard | CountsCard | ReviewCard | TipCard | BarsCard | ScheduledCard
  | MenusCard | QuoteCard | InstaPostCard | ImagesCard | ChecklistCard | PeopleCard | InviteCard | ManualCard | ActionCard | ReplyListCard;

export type StoreStatus = { state: 'before_open' | 'open' | 'closed'; label: string; detail: string };

export type Say = { text: string; caption: string | null; focus: string[] };

export type Home = {
  store: { id: string; name: string; logo_url: string | null; open_time: string; close_time: string };
  date: string;
  date_label: string;
  /** 가게 상태 줄 (영업 전, 영업 중, 영업 끝) */
  store_status: StoreStatus;
  now: string;
  briefing_ready: boolean;
  headline: string;
  cards: Card[];
};

/** 도나 알림. opens_turn: 소리를 내고 turn(event: notice)로 열어 도나가 묻는다 (아쉬운 리뷰). say: 소리를 내고 읽는다. */
export type Notice = {
  id: string; kind: 'staff_joined' | 'unconfirmed' | 'story' | 'negative_review' | 'staff_checked' | 'reply_fallback' | 'story_event' | 'instagram' | 'negative_auto' | 'hr_batch' | 'notebook' | 'revise_ready';
  text: string; time_label: string; say?: string[]; opens_turn?: boolean; alert_id?: string | null;
};

// ask_tasks: 알바생 할 일로 넣을지 묶어 묻는다 ("응, 넣어" / "두 번째는 빼" / "안 해", 2026-11-20)
// ask_holiday: "○월 ○일을 쉬는 날로 적을게요. 맞아요?" (2026-11-20)
export type TurnType = 'answer' | 'ask' | 'ask_permission' | 'ask_action' | 'ask_tasks' | 'ask_holiday' | 'show_detail' | 'end' | 'not_understood' | 'ignore' | 'stop' | 'navigate';

export type Turn = {
  turn_id: string;
  type: TurnType;
  intent: string;
  owner_said: string | null;
  briefing: { step: number; total: number; step_key: string } | null;
  headline: string | null;
  say: Say[];
  cards: Card[];
  expects_reply: boolean;
  tab?: 'sales' | 'week' | 'settings' | 'home';
  /** 시연: 끝 화면을 after_ms 보여 준 뒤 이 이벤트로 다음 장면(밤 9시 인사과 보고)을 연다 (server/voice/jobs/hr_night.py) */
  next_scene?: { event: 'night_hr'; after_ms: number };
  /** 서버 시계가 옮겨졌다 (가게 상태 줄을 다시 불러온다) */
  clock_moved?: boolean;
  /** 앱이 열어야 하는 것 (카카오톡 공유, 인스타) */
  open?: 'kakao_share' | 'instagram';
  /** ask_action: 도나가 아쉬운 리뷰 처리를 물었다 ("응, 진행해" / "쿠폰 빼고" / "안 해").
   *  review_fix_task: 바로 답하기를 켠 가게에서 답글은 올렸고 알바생 할 일만 묻는다 */
  action?:
    | { kind: 'review_fix' | 'review_fix_task'; alert_id: string; compensation: boolean; staff_card: string | null; deadline_at: string }
    /** batch: 인사과 직급대로 묻기 (인턴은 한 건씩 mode 'each', 사원은 묶어서 'batch'). 대답: "응" / "두 번째는 빼" / "안 해".
     *  items 는 지금 묻는 것, rest 는 이어서 물을 것 (server/voice/jobs/batch_ask.py) */
    | { kind: 'batch'; items: { job: string; ref: string }[]; rest: { job: string; ref: string }[]; mode: 'each' | 'batch' };
};

export type Actor = 'donna' | 'owner';
export type DoneItem = { id: string; actor: Actor; text: string; time_label?: string; after_briefing?: boolean };
export type RemainingItem = { id: string; kind: RowKind; text: string; time_label: string | null };
/** 그날 잡힌 일 하나: 행사, 경기, 단체 예약, 비. 추측이 아니라 날짜와 시각이 있는 사실이다. */
export type Plan = {
  id: string;
  kind: 'event' | 'game' | 'group_reservation' | 'weather';
  /** 종류 이름 (행사, 경기, 단체 예약, 비) */
  label: string;
  text: string;
  /** 달력 칸에 적을 짧은 이름 (단체 12명) */
  short: string;
  /** 시작 시각. 하루 종일이면 null */
  starts_at: string | null;
  time_label: string | null;
};
/** 달력의 하루. 잡힌 일과 준비할 것, 그날 올릴 답글. 오늘에는 한 것과 남은 것, 지난 날에는 한 일이 더 들어 있다. */
export type WeekDay = {
  date: string; weekday_label: string; day: number; date_label: string;
  in_month: boolean; is_today: boolean; is_past: boolean;
  /** 달력 칸의 표시: plan 일이 잡힌 날, reply 답글 올리는 날 */
  marks: ('plan' | 'reply')[];
  /** 그날의 큰 한마디 (경기가 있어요) */
  title: string;
  weather: { label: string; temp_min: number; temp_max: number } | null;
  plans: Plan[];
  tip: string | null;
  scheduled: ScheduledCard['items'];
  done: DoneItem[];
  remaining: RemainingItem[];
};
export type Week = {
  week_label: string;
  month_label: string;
  today: string;
  /** 이번 주(월 ~ 일)의 날짜 */
  week_dates: string[];
  /** 달력 6주, 42일 */
  days: WeekDay[];
  /** 앞으로 올릴 답글 전부 */
  scheduled: ScheduledCard['items'];
  /** 지난 일 묶음 (어제, 지난주) */
  past: { label: string; date_label: string; items: DoneItem[] }[];
};

/** 지난번과 견주는 한 줄. 화면은 화살표 + diff_label(갈색 굵게) + 많아요/적어요 (Figma G-04). */
type Diff = { direction: 'up' | 'down'; diff_label: string; diff_text: string };

export type Sales = {
  headline: string;
  /** ① 오늘 지금까지 (문 열기 전에는 어제) ↔ 지난주 같은 요일 이맘때 */
  primary: Diff & {
    label: string; amount: number; amount_label: string;
    compare_label: string; compare_amount: number; compare_amount_label: string; compare_text: string; short_text: string;
  };
  /** ② 이번 주 지금까지 ↔ 지난주 이맘때 */
  week: Diff & {
    label: string; amount: number; total_label: string; compare_label: string; compare_text: string;
    bars: { weekday_label: string; date: string; amount: number; amount_label: string | null; last_week_amount: number; last_week_label: string; is_today: boolean; is_future: boolean }[];
    max_amount: number;
  };
  /** ② 이번 달 지금까지 ↔ 지난달 이맘때 */
  month: Diff & { label: string; amount: number; amount_label: string; compare_label: string; has_last: boolean };
  /** ③ 도나 답글을 받고 이번 주에 다시 온 손님 */
  revisits: {
    label: string; count: number; count_label: string; last_week_label: string;
    latest: { came_back_label: string; date_label: string; review: { rating: number; text: string; date_label: string }; reply: { text: string; by: 'donna' | 'owner' } } | null;
  };
  top_menus: { label: string; unit: string; items: { id: string; label: string; count: number }[] };
  /** ④ 이번 달 가장 많이 나간 메뉴 */
  top_menus_month: { label: string; unit: string; items: { id: string; label: string; count: number }[] } | null;
};

export type DayHours = { weekday: number; label: string; closed: boolean; open: string; close: string };
export type Settings = {
  negative_review_auto_reply: boolean | null;
  store: { id: string; name: string };
  open_time_label: string;
  close_time_label: string;
  /** 브리핑은 사장님이 부를 때 한다. 알림은 기본 문 열기 1시간 전이고 사장님이 고른다 (G-08). */
  briefing_notify: {
    on: boolean; time: string; time_label: string; is_default: boolean; default_time: string;
    options: { time: string; label: string; sub: string; is_default: boolean }[];
  };
  /** 요일별 장사 시간 (G-06). naver_days 는 '네이버에서 다시 불러오기'로 되돌릴 시간 */
  hours: { summary_label: string; days: DayHours[]; naver_days: DayHours[] };
  account: { store_name: string; address: string | null };
  /** 알바생 화면에 들어온 사람 수. 없으면 null (줄을 숨긴다) */
  staff_count: number | null;
  /** 아쉬운 리뷰 답글에 붙일 사장님이 정한 보상 한 문장 (불만 종류마다). 화면은 아직 없다 */
  compensation?: Record<'packaging' | 'missing' | 'taste_temp' | 'hall_service', string | null>;
  platforms: { key: string; name: string; connected: boolean }[];
};
export type SettingsPatch = {
  negative_review_auto_reply?: boolean | null;
  briefing_notify?: { on?: boolean; time?: string | null };
  hours?: { days: { closed: boolean; open: string; close: string }[] };
};

// ---------- 알바생 앱 (F-02 ~ F-09) ----------
export type StaffTask = {
  id: string; title: string; sub: string; fresh: boolean; repeat: 'daily' | 'today'; kind: 'do' | 'dont';
  must_confirm: boolean; confirmed: boolean; done: boolean; has_words: boolean;
  /** 아쉬운 리뷰에서 나온 교정 카드 (맨 위, 확인해야 퇴근) */
  urgent?: boolean; detail?: string | null;
};
export type StaffToday = {
  store: { name: string; logo_url: string | null };
  date_label: string;
  staff: { id: string; name: string; call: string };
  attendance: { state: 'in' | 'out'; label: string; detail: string };
  /** '지금' 선이 이 때 묶음 뒤에 온다. null 이면 맨 위 */
  now_after: 'before_open' | 'open' | 'closing' | null;
  groups: { phase: 'before_open' | 'open' | 'closing'; label: string; now: boolean; must: StaffTask[]; tasks: StaffTask[] }[];
  /** 아직 확인하지 않은 교정 카드. 화면 맨 위 */
  urgent?: StaffTask[];
};
export type StaffTaskDetail = StaffTask & { tag: string; owner_words: string | null; owner_words_label: string | null; until: string | null };
/** 가입·로그인하면 받는 것. token 은 그 뒤 알바생 요청마다 X-Staff-Token 으로 보낸다 */
export type StaffSignedIn = { token: string; staff_id: string; store: { name: string; logo_url: string | null }; name: string; call: string };

/** 시연 화면의 알바생 휴대폰에 띄우는 '사장님이 보낸 글' (Figma F-01, 카카오톡 모양 예시. GET /v1/dev/messenger) */
export type Messenger = {
  from: string; to: string | null; store: { name: string; logo_url: string | null };
  items: { id: string; text: string; url: string; code: string; link: string; time_label: string; date_label: string; usable: boolean }[];
};

/** 시연 화면 오른쪽 위 '리뷰 플랫폼' (GET /v1/dev/platform). 올라간 답글이 보인다. */
export type Platform = {
  now: string; now_label: string;
  items: { id: string; platform_label: string; rating: number; text: string; menus: string[]; written_label: string;
    reply: { text: string; posted_label: string; fresh: boolean } | null }[];
};

/** 서버가 거절한 까닭. code 는 화면에 보여 주지 않고, message 는 사장님이 읽을 수 있는 말이다 */
export class ApiFailure extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

/** timeout: 말로 하는 대화는 5초를 넘기면 못 쓴다. 가게를 네이버 지도에서 읽는 것처럼 오래 걸리는 것은 늘려 부른다 */
export async function request<T>(path: string, init?: RequestInit, timeout = 5000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
    if (!res.ok) {
      // 가입 흐름(/api/*)은 {"error": {"code", "message"}} 로 까닭을 알려 준다
      const body = (await res.json().catch(() => null)) as { error?: { code?: string; message?: string } | string } | null;
      const err = body && typeof body.error === 'object' ? body.error : null;
      throw new ApiFailure(err?.code ?? `HTTP_${res.status}`, err?.message ?? `서버 오류 ${res.status}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

/** 알바생 요청에 붙이는 로그인 표시 */
const staffAuth = (): Record<string, string> => {
  const token = staffSession.get().token;
  return token ? { 'X-Staff-Token': token } : {};
};

let seq = 0;
const newId = (p: string) => `${p}_${Date.now().toString(36)}_${(seq++).toString(36)}`;
const SESSION_ID = newId('sess');

export const api = {
  home: () => request<Home>(`/v1/home?store_id=${storeId()}`),
  week: () => request<Week>(`/v1/week?store_id=${storeId()}`),
  sales: () => request<Sales>(`/v1/sales?store_id=${storeId()}`),
  settings: () => request<Settings>(`/v1/settings?store_id=${storeId()}`),
  patchSettings: (patch: SettingsPatch) =>
    request<Settings>('/v1/settings', { method: 'PATCH', body: JSON.stringify({ store_id: storeId(), ...patch }) }),
  notices: () => request<{ notices: Notice[] }>(`/v1/notices?store_id=${storeId()}`),
  /** 시연 화면(/demo)만 쓴다 (개발용 API, 문서 9장) */
  dev: {
    fixtures: (fixture = 's005_choongjang') => request<{ store_id: string; now: string }>('/v1/dev/fixtures', { method: 'POST', body: JSON.stringify({ fixture }) }, 180000),
    clock: (now: string | null) => request<{ now: string }>('/v1/dev/clock', { method: 'POST', body: JSON.stringify({ now }) }, 60000),
    demoReview: (name: string) => request<{ review_id: string; alert: boolean }>('/v1/dev/demo_review', { method: 'POST', body: JSON.stringify({ store_id: storeId(), name }) }, 60000),
    platform: () => request<Platform>(`/v1/dev/platform?store_id=${storeId()}`),
    messenger: (to: string) => request<Messenger>(`/v1/dev/messenger?store_id=${storeId()}&to=${encodeURIComponent(to)}`),
    /** 연습용: 초대·가입을 건너뛰고 가입한 상태로 (개발자 모드 '하린 바로 가입') */
    staffJoin: (name: string) => request<{ token: string; staff_id: string; name: string }>('/v1/dev/staff_join', { method: 'POST', body: JSON.stringify({ store_id: storeId(), name }) }),
  },
  instagramConnect: () => request<{ connected: boolean; say: string }>('/v1/instagram/connect', { method: 'POST', body: '{}' }),
  // 알바생: 가입·로그인 뒤의 요청은 로그인 표시(토큰)로 누구인지 알린다. 서버가 거절하면 ApiFailure('not_signed_in')
  staff: {
    checkCode: (code: string) => request<{ ok: boolean; message?: string; store?: { name: string; logo_url: string }; staff_id?: string; name?: string }>('/v1/staff/invite/check', { method: 'POST', body: JSON.stringify({ code }) }),
    signup: (body: { code: string; name: string; login_id: string; password: string }) =>
      request<StaffSignedIn>('/v1/staff/signup', { method: 'POST', body: JSON.stringify(body) }),
    login: (login_id: string, password: string) => request<StaffSignedIn>('/v1/staff/login', { method: 'POST', body: JSON.stringify({ login_id, password }) }),
    start: () => request<{ ok: boolean }>('/v1/staff/start', { method: 'POST', body: '{}', headers: staffAuth() }),
    today: () => request<StaffToday>('/v1/staff/today', { headers: staffAuth() }),
    task: (id: string) => request<StaffTaskDetail>(`/v1/staff/tasks/${id}`, { headers: staffAuth() }),
    done: (id: string, undo = false) => request<{ ok: boolean }>(`/v1/staff/tasks/${id}/done`, { method: 'POST', body: JSON.stringify({ undo }), headers: staffAuth() }),
    confirm: (id: string) => request<{ ok: boolean }>(`/v1/staff/tasks/${id}/confirm`, { method: 'POST', body: '{}', headers: staffAuth() }),
    checkout: () => request<{ ok: boolean }>('/v1/staff/checkout', { method: 'POST', body: '{}', headers: staffAuth() }),
  },
  turn: (input: { text?: string; source?: 'voice'; confidence?: number; addressed?: boolean; event?: 'auto_next' | 'notice' | 'night_hr' | 'called'; noticeId?: string; lastTurnId?: string | null }) =>
    request<Turn>('/v1/turn', {
      method: 'POST',
      body: JSON.stringify({
        request_id: newId('req'),
        store_id: storeId(),
        session_id: SESSION_ID,
        client_time: new Date().toISOString(),
        // addressed: "도나야"로 불러서 한 말 (부르는 말은 떼고 보낸다). v0.2.1부터 칩이 없어 source 는 voice 하나다.
        utterance: input.text ? { text: input.text, confidence: input.confidence ?? 1, source: 'voice', addressed: !!input.addressed } : null,
        event: input.event ?? null,
        notice_id: input.noticeId ?? null,
        context: { last_turn_id: input.lastTurnId ?? null, donna_was_speaking: false, heard_until: null },
      }),
    }),
};
