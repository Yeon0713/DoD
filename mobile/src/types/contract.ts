// 서버 응답 모양. 기준: contracts/sample_responses/*.example.json, docs/server-api-and-planner-guide.md 부록 A

export type Slot = "OPENING" | "AFTERNOON" | "CLOSING";
export type Weekday = "MON" | "TUE" | "WED" | "THU" | "FRI" | "SAT" | "SUN";
export type Daypart = "LUNCH" | "DINNER" | "NIGHT";
export type Signal = "HIGH" | "NORMAL" | "LOW";
export type Platform = "NAVER" | "BAEMIN" | "YOGIYO" | "COUPANG";
export type TaskType = "REVISIT_REPLY" | "MENU_ORDER" | "POSTER" | "REVIEW_FIX" | "REORDER_NUDGE";
export type RevisitClass = "QUICK" | "WEEKLY" | "MONTHLY" | "BASIC";
export type NotifyKind = "APPROVAL_REQUEST" | "EXECUTE_REMINDER" | "PREVIEW" | "NOTICE";
export type ReasonTag = "EVENT" | "GAME" | "WEATHER" | "SEASON";
export type ComplaintType = "TASTE" | "PORTION" | "HYGIENE" | "PHOTO_MISMATCH" | "DELIVERY_DELAY" | "SERVICE";
export type ComplaintGroup = "FOOD" | "DELIVERY" | "SERVICE";
export type BasisKind = "REVIEW" | "RISK_SIGNAL" | "CALENDAR_DAY" | "EVENT" | "GAME" | "CUSTOMER";

export interface Example {
  is_example: boolean;
}

export interface TodayEntry {
  plan_id: string | null;
  notice_id: string | null;
  notify_kind: NotifyKind;
  priority: 1 | 2 | 3 | 4;
}

export interface TodayBatch {
  slot_at: string;
  slot: Slot;
  entries: TodayEntry[];
}

export interface TodayResponse extends Example {
  date: string;
  batches: TodayBatch[];
}

export interface PlanItem {
  plan_id: string;
  task_type: TaskType;
  revisit_class: RevisitClass | null;
  basis: { kind: BasisKind; ref_id: string };
  target_date: string;
  approval_request_at: string;
  execute_at: string | null;
  deadline_at: string | null;
  reason_line: string;
  planned_at: string;
  /** 리뷰 답글·재주문 인사 초안. 서버가 CLOVA X로 리뷰를 읽고 쓴다. 없으면 앱 기본 문장(mocks/extras.ts)을 쓴다 */
  draft_text?: string | null;
}

export interface NoticeItem {
  notice_id: string;
  kind: "WEEKLY_PREVIEW" | "SALES_ANOMALY";
  slot_at: string;
  refs: string[];
  text: string;
}

export interface PlanResponse extends Example {
  plan_items: PlanItem[];
  notice_items: NoticeItem[];
}

export interface CalendarCell {
  date: string;
  daypart: Daypart;
  signal: Signal;
  baseline_sales: number;
  expected_sales: number;
  ratio: number;
  reasons: { tag: ReasonTag; ref_id: string; effect: number }[];
  reason_text: string;
  computed_at: string;
}

export interface CalendarResponse extends Example {
  cells: CalendarCell[];
}

export interface Review {
  review_id: string;
  platform: Platform;
  written_at: string;
  rating: number;
  text: string;
  customer_key: string | null;
  order_id: string | null;
  /** 리뷰가 달린 주문의 주문 시각. 점검 화면(06-24)이 "언제 늦었는지"를 보여 줄 때 쓴다. 서버에 아직 없는 필드 */
  ordered_at?: string | null;
  /** 손님이 올린 사진 주소. 서버에 아직 없는 필드 (docs/frontend_mock_and_api_needs.md, 06 A3) */
  photos?: string[];
  label: {
    sentiment: "POSITIVE" | "NEGATIVE" | "MIXED" | "NEUTRAL";
    complaint_types: ComplaintType[];
    complaint_groups: ComplaintGroup[];
    is_quick: boolean;
    labeler: "HCX" | "RULE";
    labeled_at: string;
  } | null;
}

export interface ReviewsResponse extends Example {
  reviews: Review[];
}

export interface StoreSettings {
  store_id: string;
  name: string;
  category: string;
  lat: number;
  lng: number;
  open_time: string;
  close_time: string;
  dayparts: Record<Daypart, { start: string; end: string }>;
  busy_dayparts: Daypart[];
  slots: Record<Slot, string>;
  /** 쉬는 날. 서버 코드값 MON ~ SUN */
  closed_weekdays: Weekday[];
  /** 요일별 장사 시간. null이면 쉬는 날. 서버에 아직 없는 필드 (06 E). open_time, close_time, closed_weekdays는 여기서 나온 값이다. */
  weekly_hours?: Record<Weekday, { open: string; close: string } | null>;
  /** 브레이크 타임. 서버에 아직 없는 필드 (docs/frontend_mock_and_api_needs.md 3장 P) */
  break_time?: { start: string; end: string } | null;
}

export interface SettingsResponse extends Example {
  settings: StoreSettings;
}

export interface ApiError {
  error: { code: string; message: string };
}
