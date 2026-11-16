// 서버와 주고받는 곳은 이 파일 하나다. 모양은 docs/v0.2.0-voice-agent-handoff.md 4 ~ 5장, 17장(v0.2.1 화면 포맷).

export const BASE = (process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8100').replace(/\/$/, '');
export const STORE_ID = 's005';
/** 서버가 준 그림 주소 (/static/...)를 쓸 수 있는 주소로. */
export const media = (url: string | null | undefined) => (!url ? null : /^https?:/.test(url) ? url : `${BASE}${url}`);

export type RowKind =
  | 'event' | 'game' | 'reservation' | 'group_reservation' | 'schedule' | 'reviews' | 'scheduled_replies'
  | 'reply' | 'briefing' | 'off' | 'done'
  // v0.2.1
  | 'weather' | 'instagram' | 'staff' | 'person' | 'task' | 'ban' | 'warning' | 'time' | 'date' | 'phone'
  | 'lock' | 'message' | 'invite' | 'image' | 'users' | 'clock';

/** v0.2.1부터 줄에는 이름표(label)가 없다. value 하나로 읽힌다. title 은 '오늘 아침에 한 것' 같은 카드 제목. */
export type RowsCard = { type: 'rows'; id: string; title?: string; rows: { id: string; kind: RowKind; label?: string; value: string }[] };
export type CountsCard = { type: 'counts'; id: string; items: { id: string; kind: 'positive' | 'negative'; label: string; count: number; unit: string }[] };
export type ReviewCard = {
  type: 'review'; id: string; variant: 'summary' | 'full'; rating: number; text: string; written_at: string;
  reply: { text: string; posted_at: string | null; by: 'donna' | 'owner'; scheduled_label?: string | null } | null;
};
export type TipCard = { type: 'tip'; id: string; kind: 'improve' | 'keep' | 'prepare'; text: string };
export type BarsCard = { type: 'bars'; id: string; unit: string; title?: string; items: { id: string; label: string; count: number }[] };
export type ReasonKind = 'weather' | 'game' | 'event' | 'weekend' | 'season' | 'reservation' | 'lunch';
export type ScheduledCard = {
  type: 'scheduled'; id: string;
  items: { id: string; day_label: string; time_label: string; post_at: string; reason: { kind: ReasonKind; label: string }; text: string }[];
};
/** 이번 달 많이 나간 메뉴 (D-03, D-14). editable 이면 '바꾸기'가 붙는다. */
export type MenusCard = { type: 'menus'; id: string; title?: string | null; editable?: boolean; items: { id: string; rank: number; name: string; count_label: string; photo_url: string }[] };
export type QuoteCard = { type: 'quote'; id: string; label: string; text: string };
/** 인스타 게시물 모양 그대로 (D-15). */
export type InstaPostCard = { type: 'insta_post'; id: string; handle: string; logo_url: string; slide: number; slides: number; photo_url: string | null; top_label: string; title: string; caption: string };
/** 알바생에게 시킨 것 (D-24, D-33). state: todo / done / canceled */
export type ChecklistCard = { type: 'checklist'; id: string; title: string; items: { id: string; title: string; sub: string; state: 'todo' | 'done' | 'canceled' }[] };
export type PeopleCard = { type: 'people'; id: string; title: string; items: { id: string; name: string; sub: string }[] };
export type InviteCard = { type: 'invite'; id: string; message: string; url: string; code: string };
export type ManualCard = { type: 'manual'; id: string; groups: { id: string; kind: 'before_open' | 'open' | 'closing'; label: string; text: string }[] };
/** 말로 할 수 없는 한 번의 일 (D-01 인스타 연결). */
export type ActionCard = { type: 'action'; id: string; label: string; action: 'instagram_connect' };
export type Card =
  | RowsCard | CountsCard | ReviewCard | TipCard | BarsCard | ScheduledCard
  | MenusCard | QuoteCard | InstaPostCard | ChecklistCard | PeopleCard | InviteCard | ManualCard | ActionCard;

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

export type Notice = { id: string; kind: 'staff_joined' | 'unconfirmed' | 'story'; text: string; time_label: string };

export type TurnType = 'answer' | 'ask' | 'ask_permission' | 'show_detail' | 'end' | 'not_understood' | 'ignore' | 'stop' | 'navigate';

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
  /** 앱이 열어야 하는 것 (카카오톡 공유, 인스타) */
  open?: 'kakao_share' | 'instagram';
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

export type Sales = {
  headline: string;
  primary: { label: string; amount: number; amount_label: string; compare_label: string; compare_amount_label: string; direction: 'up' | 'down'; compare_text: string };
  week: { bars: { weekday_label: string; date: string; amount: number; amount_label: string | null; last_week_amount: number; last_week_label: string; is_today: boolean; is_future: boolean }[]; max_amount: number; total_label: string; compare_text: string; direction: 'up' | 'down' };
  top_menus: { label: string; unit: string; items: { id: string; label: string; count: number }[] };
};

export type Settings = {
  negative_review_auto_reply: boolean | null;
  store: { id: string; name: string };
  open_time_label: string;
  close_time_label: string;
  briefing_time_label: string;
  platforms: { key: string; name: string; connected: boolean }[];
};

// ---------- 알바생 앱 (F-02 ~ F-09) ----------
export type StaffTask = {
  id: string; title: string; sub: string; fresh: boolean; repeat: 'daily' | 'today'; kind: 'do' | 'dont';
  must_confirm: boolean; confirmed: boolean; done: boolean; has_words: boolean;
};
export type StaffToday = {
  store: { name: string; logo_url: string | null };
  date_label: string;
  staff: { id: string; name: string; call: string };
  attendance: { state: 'in' | 'out'; label: string; detail: string };
  /** '지금' 선이 이 때 묶음 뒤에 온다. null 이면 맨 위 */
  now_after: 'before_open' | 'open' | 'closing' | null;
  groups: { phase: 'before_open' | 'open' | 'closing'; label: string; now: boolean; must: StaffTask[]; tasks: StaffTask[] }[];
};
export type StaffTaskDetail = StaffTask & { tag: string; owner_words: string | null; owner_words_label: string | null; until: string | null };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 5000); // 말로 하는 대화는 5초를 넘기면 못 쓴다
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
    if (!res.ok) throw new Error(`서버 오류 ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

let seq = 0;
const newId = (p: string) => `${p}_${Date.now().toString(36)}_${(seq++).toString(36)}`;
const SESSION_ID = newId('sess');

export const api = {
  home: () => request<Home>(`/v1/home?store_id=${STORE_ID}`),
  week: () => request<Week>(`/v1/week?store_id=${STORE_ID}`),
  sales: () => request<Sales>(`/v1/sales?store_id=${STORE_ID}`),
  settings: () => request<Settings>(`/v1/settings?store_id=${STORE_ID}`),
  patchSettings: (patch: Partial<Pick<Settings, 'negative_review_auto_reply'>>) =>
    request<Settings>('/v1/settings', { method: 'PATCH', body: JSON.stringify({ store_id: STORE_ID, ...patch }) }),
  notices: () => request<{ notices: Notice[] }>(`/v1/notices?store_id=${STORE_ID}`),
  instagramConnect: () => request<{ connected: boolean; say: string }>('/v1/instagram/connect', { method: 'POST', body: '{}' }),
  staff: {
    checkCode: (code: string) => request<{ ok: boolean; message?: string; store?: { name: string; logo_url: string }; staff_id?: string; name?: string }>('/v1/staff/invite/check', { method: 'POST', body: JSON.stringify({ code }) }),
    signup: (body: { code: string; name: string; login_id: string; password: string }) =>
      request<{ staff_id: string; store: { name: string; logo_url: string }; name: string; call: string }>('/v1/staff/signup', { method: 'POST', body: JSON.stringify(body) }),
    start: (staff_id: string) => request<{ ok: boolean }>('/v1/staff/start', { method: 'POST', body: JSON.stringify({ staff_id }) }),
    today: (staff_id: string) => request<StaffToday>(`/v1/staff/today?staff_id=${staff_id}`),
    task: (id: string, staff_id: string) => request<StaffTaskDetail>(`/v1/staff/tasks/${id}?staff_id=${staff_id}`),
    done: (id: string, staff_id: string, undo = false) => request<{ ok: boolean }>(`/v1/staff/tasks/${id}/done`, { method: 'POST', body: JSON.stringify({ staff_id, undo }) }),
    confirm: (id: string, staff_id: string) => request<{ ok: boolean }>(`/v1/staff/tasks/${id}/confirm`, { method: 'POST', body: JSON.stringify({ staff_id }) }),
    checkout: (staff_id: string) => request<{ ok: boolean }>('/v1/staff/checkout', { method: 'POST', body: JSON.stringify({ staff_id }) }),
  },
  turn: (input: { text?: string; source?: 'voice'; confidence?: number; addressed?: boolean; event?: 'auto_next'; lastTurnId?: string | null }) =>
    request<Turn>('/v1/turn', {
      method: 'POST',
      body: JSON.stringify({
        request_id: newId('req'),
        store_id: STORE_ID,
        session_id: SESSION_ID,
        client_time: new Date().toISOString(),
        // addressed: "도나야"로 불러서 한 말 (부르는 말은 떼고 보낸다). v0.2.1부터 칩이 없어 source 는 voice 하나다.
        utterance: input.text ? { text: input.text, confidence: input.confidence ?? 1, source: 'voice', addressed: !!input.addressed } : null,
        event: input.event ?? null,
        context: { last_turn_id: input.lastTurnId ?? null, donna_was_speaking: false, heard_until: null },
      }),
    }),
};
