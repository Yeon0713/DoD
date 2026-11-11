// 06-24 점검 화면: 같은 불만 리뷰를 모아 사실만 보여 준다 (06 B. 가르치지 않고, 판단은 사장님이).
import type { ComplaintType, PlanItem, Review, StoreSettings } from "@/types/contract";
import { PLATFORM_KO } from "./labels";
import { toMin } from "./hours";
import { addDays } from "./time";

const DAYPART_KO = { LUNCH: "점심", DINNER: "저녁", NIGHT: "밤" } as const;

function seoulMin(iso: string) {
  const d = new Date(new Date(iso).getTime() + 9 * 3600e3);
  return d.getUTCHours() * 60 + d.getUTCMinutes();
}

function partWord(min: number) {
  if (min < 6 * 60) return "새벽";
  if (min < 11 * 60) return "아침";
  if (min < 15 * 60) return "점심";
  if (min < 21 * 60) return "저녁";
  return "밤";
}

function clockWord(min: number) {
  const h = Math.round(min / 60) % 24;
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${partWord(min)} ${h12}시쯤`;
}

export interface CheckData {
  type: ComplaintType;
  reviews: Review[];
  /** "도나가 찾은 것" 줄들 */
  facts: string[];
}

/** 이 점검 일(REVIEW_FIX)의 지난 7일 같은 불만 리뷰와 거기서 찾은 사실 */
export function checkData(p: PlanItem, reviews: Review[], s: StoreSettings): CheckData {
  const from = addDays(p.target_date, -7);
  const recent = reviews.filter((r) => r.label?.complaint_types.length && r.written_at.slice(0, 10) > from && r.written_at.slice(0, 10) <= p.target_date);
  const counts = new Map<ComplaintType, number>();
  for (const r of recent) for (const t of r.label!.complaint_types) counts.set(t, (counts.get(t) ?? 0) + 1);
  const type = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "SERVICE";
  const mine = recent.filter((r) => r.label!.complaint_types.includes(type)).sort((a, b) => a.written_at.localeCompare(b.written_at));
  const facts: string[] = [];
  const times = mine.map((r) => seoulMin(r.ordered_at ?? r.written_at));
  if (times.length >= 2) {
    const spread = Math.max(...times) - Math.min(...times);
    const avg = times.reduce((a, b) => a + b, 0) / times.length;
    if (spread <= 90) {
      facts.push(`${times.length}번 모두 ${clockWord(avg)}이에요`);
      const busy = s.busy_dayparts.find((d) => {
        const a = toMin(s.dayparts[d].start);
        const b = s.dayparts[d].end === "24:00" ? 1440 : toMin(s.dayparts[d].end);
        return times.every((t) => t >= a - 30 && t <= b + 30);
      });
      if (busy) facts.push(`주문이 가장 몰리는 ${DAYPART_KO[busy]} 시간과 겹쳐요`);
    }
  }
  const platforms = [...new Set(mine.map((r) => r.platform))];
  if (mine.length >= 2 && platforms.length === 1) facts.push(`모두 ${PLATFORM_KO[platforms[0]]} 주문이에요`);
  if (!facts.length && mine.length) facts.push(`일주일에 ${mine.length}번 같은 말이 나왔어요`);
  return { type, reviews: mine, facts };
}

/** 06-24o 펼치면 보이는 "다른 가게는 이렇게 하기도 해요" */
export const OTHER_STORES: Record<ComplaintType, string[]> = {
  DELIVERY_DELAY: ["바쁜 시간엔 배달앱 준비 시간을 10분 늘려 둬요", "배달 주문은 포장 자리를 따로 비워 둬요", "저녁 7시 전에 국물을 미리 데워 둬요"],
  TASTE: ["간은 장사 시작 전에 한 번 더 봐요", "육수 끓이는 시간을 적어 두고 맞춰요", "양념 양을 레시피에 다시 적어 둬요"],
  PORTION: ["담는 그릇에 선을 정해 둬요", "메뉴 사진과 같은 양인지 한 번 봐요", "포장 전에 한 번 더 봐요"],
  HYGIENE: ["장사 전후로 조리대를 닦아 둬요", "포장 용기 뚜껑을 한 번 더 확인해요", "위생 장갑을 자주 바꿔 껴요"],
  PHOTO_MISMATCH: ["메뉴 사진을 새로 찍어 둬요", "사진과 같은 모양으로 담아요", "배달앱 사진을 바꿔 둬요"],
  SERVICE: ["전화 받는 말을 정해 둬요", "요청사항을 한 번 더 읽어요", "주문 확인 문자를 보내요"],
};
