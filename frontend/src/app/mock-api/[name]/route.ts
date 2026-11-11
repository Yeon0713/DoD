// 고정 샘플 모드에서만 쓰는 길. 서버와 같은 예시 파일(contracts/sample_responses)을 그대로 돌려준다.
// 예시 파일을 frontend 안에 복사하지 않아서, 서버 쪽에서 예시를 고치면 화면도 바로 같은 값을 쓴다.
// PATCH /mock-api/settings는 서버(server/app/modules/settings/data_provider.py)와 같은 검사에 05 시안의 장사 시간 검사(브레이크 타임, 새벽 마감, 쉬는 날)를 더해 메모리에만 저장한다.
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fromMin, sinceOpen, toMin } from "@/lib/hours";

const FILES: Record<string, string> = {
  today: "today_response.example.json",
  plan: "plan_response.example.json",
  calendar: "calendar_response.example.json",
  sales: "sales_response.example.json",
  reviews: "reviews_response.example.json",
  settings: "settings_response.example.json",
};

type Settings = {
  open_time: string;
  close_time: string;
  dayparts: Record<string, { start: string; end: string }>;
  busy_dayparts: string[];
  slots: Record<string, string>;
  closed_weekdays: string[];
  break_time?: { start: string; end: string } | null;
};
const EDITABLE = ["slots", "dayparts", "busy_dayparts", "open_time", "close_time", "closed_weekdays", "break_time"] as const;

let settingsOverride: Partial<Settings> | null = null;

async function loadJson(name: string) {
  const full = path.join(process.cwd(), "..", "contracts", "sample_responses", FILES[name]);
  return JSON.parse(await readFile(full, "utf8"));
}

function fail(status: number, code: string, message: string) {
  return Response.json({ error: { code, message } }, { status });
}

export async function GET(_req: Request, ctx: RouteContext<"/mock-api/[name]">) {
  const { name } = await ctx.params;
  if (!FILES[name]) return fail(404, "NOT_FOUND", "없는 예시예요.");
  const body = await loadJson(name);
  if (name === "settings" && settingsOverride) body.settings = { ...body.settings, ...settingsOverride };
  return Response.json(body);
}

const HHMM = /^\d\d:\d\d$/;
const DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];

export async function PATCH(req: Request, ctx: RouteContext<"/mock-api/[name]">) {
  const { name } = await ctx.params;
  if (name !== "settings") return fail(405, "METHOD_NOT_ALLOWED", "고칠 수 없는 항목이에요.");
  const update = (await req.json()) as Partial<Settings>;
  const current = (await loadJson("settings")).settings as Settings;
  const next: Settings = { break_time: null, ...current, ...settingsOverride, ...update };

  // 형식 검사
  const times = [next.open_time, next.close_time, ...Object.values(next.slots), ...(next.break_time ? [next.break_time.start, next.break_time.end] : [])];
  if (times.some((t) => !HHMM.test(t))) return fail(400, "INVALID_INPUT", "시각은 10:00처럼 적어 주세요.");
  if (next.closed_weekdays.some((d) => !DAYS.includes(d))) return fail(400, "INVALID_INPUT", "쉬는 날은 MON ~ SUN으로 보내 주세요.");
  if (next.closed_weekdays.length === 7) return fail(400, "INVALID_INPUT", "쉬는 날이 아닌 날이 하루는 있어야 해요.");
  // 새벽에 닫는 가게도 순서를 맞추려고 '문 열기 1시간 전'부터 분으로 센다. 알림은 출근 준비를 위해 문 열기 1시간 전부터 받을 수 있다.
  const len = sinceOpen(next.close_time, next.open_time) || 1440;
  const from = fromMin(toMin(next.open_time) - 60);
  const pos = (t: string) => sinceOpen(t, from);
  if (next.break_time) {
    const a = sinceOpen(next.break_time.start, next.open_time);
    const b = sinceOpen(next.break_time.end, next.open_time);
    if (!(a < b && b <= len)) return fail(400, "INVALID_BREAK_TIME", "브레이크 타임은 장사 시간 안에서 시작보다 끝이 늦게 정해 주세요.");
  }
  const order = ["OPENING", "AFTERNOON", "CLOSING"].map((sl) => pos(next.slots[sl]));
  if (!(order[0] < order[1] && order[1] < order[2])) return fail(400, "INVALID_INPUT", "출근 후, 한가할 때, 마감 전 순서로 정해 주세요.");
  for (const [slot, t] of Object.entries(next.slots)) {
    if (pos(t) > len + 60) {
      return fail(400, "SLOT_OUTSIDE_OPEN_HOURS", `${slot} 알림 시각 ${t} 이 영업시간(${next.open_time}~${next.close_time}) 밖입니다.`);
    }
    for (const d of next.busy_dayparts) {
      const busy = next.dayparts[d];
      const a = toMin(busy.start);
      const b = busy.end === "24:00" ? 1440 : toMin(busy.end);
      const x = toMin(t);
      const inside = a <= b ? a <= x && x < b : x >= a || x < b;
      if (inside) return fail(400, "SLOT_IN_BUSY_DAYPART", `${slot} 알림 시각 ${t} 이 바쁜 시간대(${d} ${busy.start}~${busy.end})에 걸립니다.`);
    }
  }
  settingsOverride = Object.fromEntries(EDITABLE.map((k) => [k, next[k]])) as Partial<Settings>;
  const body = await loadJson("settings");
  body.settings = { ...body.settings, ...settingsOverride };
  return Response.json(body);
}
