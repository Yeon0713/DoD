"use client";
// 이번 주 (Figma 04-7, 04-7-월~일, 04-7L, 04-7E) 와 바쁜 날 자세히 (04-18, 04-18b).
// 시안 C "하루씩 크게": 위에 요일 7칸, 아래에 고른 날의 점심, 저녁, 밤.
import Image from "next/image";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Icon, type IconName } from "@/components/icons/Icon";
import { Bone, PrimaryButton } from "@/components/ui/parts";
import { ListRow, SubPage } from "@/components/ui/sub";
import { ApiFailure, USE_MOCK } from "@/lib/api";
import { addDays, monthDay, weekdayName, ymd } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import type { CalendarCell, Daypart, PlanItem, Signal } from "@/types/contract";
import { SKY_KO, WEATHER, type Sky } from "@/mocks/extras";

const SKY_ICON: Record<Sky, IconName> = { SUNNY: "weatherSun", PARTLY: "weatherPartly", CLOUDY: "weatherCloud", RAIN: "weatherRain" };

const DAYPARTS: { key: Daypart; label: string; icon: IconName }[] = [
  { key: "LUNCH", label: "점심", icon: "sun" },
  { key: "DINNER", label: "저녁", icon: "sunset" },
  { key: "NIGHT", label: "밤", icon: "moon" },
];
const DP_KO: Record<Daypart, string> = { LUNCH: "점심", DINNER: "저녁", NIGHT: "밤" };

function chip(signal: Signal | undefined) {
  if (signal === "HIGH") return { text: "많음", cls: "bg-busy text-white border-busy" };
  if (signal === "LOW") return { text: "적음", cls: "bg-calm-soft text-calm border-calm-soft" };
  return { text: "보통", cls: "bg-surface text-ink-2 border-line" };
}

function eventLabel(cells: CalendarCell[]): { tag: "GAME" | "EVENT"; refId: string; name: string } | null {
  for (const c of cells) {
    for (const r of c.reasons) {
      if (r.tag !== "GAME" && r.tag !== "EVENT") continue;
      const name =
        r.tag === "GAME"
          ? c.reason_text.match(/(국가대표 )?(축구|야구|농구|배구|e스포츠) 경기/)?.[0] ?? "경기"
          : c.reason_text.match(/(지역 축제|대학 축제|마라톤|지역 행사)/)?.[0] ?? "지역 행사";
      return { tag: r.tag, refId: r.ref_id, name };
    }
  }
  return null;
}

/** 하루 요약: 제목, 이유 상자 */
function daySummary(all: CalendarCell[], date: string) {
  const cells = all.filter((c) => c.date === date);
  const high = cells.filter((c) => c.signal === "HIGH").map((c) => DP_KO[c.daypart]);
  const low = cells.filter((c) => c.signal === "LOW").map((c) => DP_KO[c.daypart]);
  const title = high.length ? `${high.join(", ")}에\n손님이 많아요` : low.length ? `${low.join(", ")}에는\n조금 한가해요` : "평소와\n같아요";
  const ev = eventLabel(cells);
  const seasonToday = cells.some((c) => c.reasons.some((r) => r.tag === "SEASON"));
  const seasonBefore = all.some((c) => c.date === addDays(date, -1) && c.reasons.some((r) => r.tag === "SEASON"));
  let reason = "특별한 일정은 없어요";
  if (ev) reason = `${ev.name}가 있어요`;
  else if (seasonToday) reason = seasonBefore ? "추운 날이 이어져요" : "오늘부터 추워져요";
  const highCell = cells.find((c) => c.signal === "HIGH");
  const sub = ev ? highCell?.reason_text : seasonToday ? cells[0]?.reason_text : undefined;
  return { cells, busy: high.length > 0, title, reason, sub, ev };
}

function DayStrip({ days, today, selected, busy, onPick }: { days: string[]; today: string; selected: string; busy: Set<string>; onPick: (d: string) => void }) {
  return (
    <div className="mt-4 grid grid-cols-7 gap-1.5" role="tablist" aria-label="요일 고르기">
      {days.map((d) => {
        const on = d === selected;
        const isToday = d === today;
        return (
          <div key={d} className="flex flex-col items-center gap-1">
            <button
              type="button"
              role="tab"
              aria-selected={on}
              aria-label={`${monthDay(d)} ${weekdayName(d)}${isToday ? ", 오늘" : ""}${busy.has(d) ? ", 바쁨" : ""}`}
              onClick={() => onPick(d)}
              className={`flex h-[52px] w-full flex-col items-center justify-center rounded-xl border ${
                on ? "border-brand bg-brand text-brand-ink" : isToday ? "border-2 border-brand bg-brand-soft text-ink" : "border-line bg-surface text-ink"
              }`}
            >
              <span className="text-body leading-6 font-medium">{weekdayName(d)[0]}</span>
              <span className={`text-small ${on ? "text-brand-ink" : "text-ink-2"}`}>{Number(d.slice(8))}</span>
            </button>
            <span className={`h-5 text-small font-bold ${busy.has(d) ? "text-busy" : ""}`}>{busy.has(d) ? "바쁨" : ""}</span>
          </div>
        );
      })}
    </div>
  );
}

function WeekHeader({ range }: { range?: [string, string] }) {
  return (
    <header className="pt-2">
      <h1 className="text-display">이번 주 손님</h1>
      {range && (
        <p className="text-label text-ink-2">
          {monthDay(range[0])}부터 {Number(range[1].slice(8))}일까지
        </p>
      )}
    </header>
  );
}

export function WeekScreen() {
  const { data, mounted, now, error, refetch } = useHome();
  // ?day=2026-11-19 처럼 고른 날로 연다 (04-7-월~일 검토용)
  const [picked, setPicked] = useState<string | null>(() => (typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("day")));
  const today = mounted ? ymd(now) : "";

  if (!data) {
    if (error instanceof ApiFailure && error.offline) {
      return (
        <>
          <WeekHeader />
          <div className="flex flex-1 flex-col items-center justify-center text-center">
            <Image loading="eager" src="/donna/question.png" alt="" width={133} height={196} />
            <h2 className="mt-3 text-display">
              인터넷이
              <br />
              잠시 끊겼어요
            </h2>
            <p className="mt-2 text-body text-ink-2">연결되면 이번 주를 다시 보여 드릴게요</p>
          </div>
          <PrimaryButton onClick={() => refetch()}>다시 불러오기</PrimaryButton>
        </>
      );
    }
    // 04-7L 불러오는 중
    return (
      <>
        <WeekHeader />
        <div className="mt-4 grid grid-cols-7 gap-1.5" aria-hidden>
          {Array.from({ length: 7 }, (_, i) => (
            <Bone key={i} className="h-[52px] rounded-xl" />
          ))}
        </div>
        <div className="mt-8 flex flex-col gap-3" role="status" aria-label="이번 주를 불러오고 있어요">
          <Bone className="h-6 w-40" />
          <Bone className="h-6 w-48" />
          <Bone className="mt-2 h-16 w-full rounded-2xl" />
          {DAYPARTS.map((d) => (
            <Bone key={d.key} className="h-10 w-full" />
          ))}
        </div>
      </>
    );
  }

  const cells = data.calendar.cells;
  const days = [...new Set(cells.map((c) => c.date))].sort();
  const busy = new Set(cells.filter((c) => c.signal === "HIGH").map((c) => c.date));
  const selected = picked ?? (days.includes(today) ? today : days[0]);
  const s = daySummary(cells, selected);
  const w = USE_MOCK ? WEATHER[selected] : undefined;
  const linkTo = s.ev ? `/week/${s.ev.refId}` : null;

  return (
    <>
      <WeekHeader range={[days[0], days[days.length - 1]]} />
      <DayStrip days={days} today={today} selected={selected} busy={busy} onPick={setPicked} />

      <section className="mt-3" aria-live="polite">
        <p className="text-label text-ink-2">
          {monthDay(selected)} {weekdayName(selected)}
          {selected === today ? ", 오늘" : ""}
        </p>
        <div className="flex items-start justify-between">
          <h2 className="pre-line text-display">{s.title}</h2>
          <Image loading="eager" src={`/donna/${s.busy ? "b1-1" : "b2-1"}.png`} alt="" width={72} height={72} />
        </div>
        <div className={`mt-2 flex items-center gap-3 rounded-2xl px-4 py-3 ${s.busy ? "bg-busy-soft" : "border border-line bg-surface"}`}>
          <div className="min-w-0 flex-1">
            <p className="text-body font-medium text-ink">{s.reason}</p>
            {s.sub && <p className="text-small text-ink-2">{s.sub}</p>}
          </div>
          {w && (
            <div className="flex shrink-0 items-center gap-2" aria-label={`${SKY_KO[w.sky]}, 낮 ${w.high}도, 아침 ${w.low}도`}>
              <Icon name={SKY_ICON[w.sky]} size={32} className="text-brand" />
              <span className="flex flex-col items-end" aria-hidden>
                <span className="text-title text-ink">{w.high}°</span>
                <span className="text-small text-ink-2">아침 {w.low}°</span>
              </span>
            </div>
          )}
        </div>
        <ul className="mt-3">
          {DAYPARTS.map((d) => {
            const c = chip(s.cells.find((x) => x.daypart === d.key)?.signal);
            return (
              <li key={d.key} className="flex h-12 items-center gap-3 border-b border-line">
                <Icon name={d.icon} size={26} className="text-ink-2" />
                <span className="flex-1 text-body">{d.label}</span>
                <span className={`inline-flex h-8 w-14 items-center justify-center rounded-lg border text-small font-bold ${c.cls}`}>{c.text}</span>
              </li>
            );
          })}
        </ul>
        {linkTo && (
          <ListRow icon="list" title="같이 하면 좋은 일 2가지" href={linkTo} />
        )}
      </section>
    </>
  );
}

/** 04-18, 04-18b: 바쁜 날 자세히. 주소는 /week/{행사 ref_id} */
export function WeekDetailScreen() {
  const refId = decodeURIComponent(useParams<{ refId: string }>().refId ?? "");
  const { data } = useHome();
  if (!data) {
    return (
      <SubPage title="이번 주">
        <Bone className="h-40 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const cells = data.calendar.cells.filter((c) => c.reasons.some((r) => r.ref_id === refId));
  const ev = eventLabel(cells);
  const days = [...new Set(cells.map((c) => c.date))].sort();
  const highCells = cells.filter((c) => c.signal === "HIGH");
  const dps = [...new Set(highCells.map((c) => DP_KO[c.daypart]))];
  const kindWord = ev?.tag === "GAME" ? "경기" : "축제";
  const multi = days.length > 1;
  const title = multi ? days.map((d) => weekdayName(d)).join(", ") : `${weekdayName(days[0] ?? "")} ${dps[0] ?? ""}`;
  const poster = data.plan.plan_items.find((p) => p.task_type === "POSTER" && p.basis.ref_id === refId);
  const menu = data.plan.plan_items.find((p: PlanItem) => p.task_type === "MENU_ORDER" && p.target_date === days[0]);
  const first = highCells[0];

  return (
    <SubPage title={title}>
      <Icon name={ev?.tag === "GAME" ? "ball" : "tent"} size={48} className="text-urgent" />
      <h2 className="mt-3 text-display">
        {ev?.name.replace("국가대표 ", "")}로
        <br />
        {multi ? `${dps.join(", ")}이 바빠요` : ev?.tag === "GAME" ? "배달이 늘 것 같아요" : "손님이 늘 것 같아요"}
      </h2>
      {multi && <p className="mt-1 text-body text-ink-2">{days.map((d) => weekdayName(d)).join("과 ")} {days.length === 2 ? "이틀" : `${days.length}일`} 동안이에요</p>}

      {!multi && first && (
        <div className="mt-6 flex flex-col gap-2">
          {[
            { label: `평소 ${weekdayName(first.date)} ${DP_KO[first.daypart]}`, v: first.baseline_sales, cls: "bg-ink-3", tcls: "text-ink-2" },
            { label: `이번 ${weekdayName(first.date)} 예상`, v: first.expected_sales, cls: "bg-busy", tcls: "text-busy" },
          ].map((r) => (
            <div key={r.label} className="flex flex-col gap-1.5">
              <div className="flex justify-between text-label text-ink-2">
                <span>{r.label}</span>
                <span className={`text-body font-bold ${r.tcls}`}>{r.v.toLocaleString("ko-KR")}원</span>
              </div>
              <div className="h-2.5 overflow-hidden rounded-full bg-line">
                <div className={`h-full rounded-full ${r.cls}`} style={{ width: `${(r.v / Math.max(first.expected_sales, first.baseline_sales)) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="mt-8 border-t border-line pt-4 text-label text-ink-2">같이 하면 좋은 일</p>
      <div>
        {poster && <ListRow icon="image" title={`${kindWord} 포스터 만들기`} href={`/poster/${encodeURIComponent(poster.plan_id)}`} />}
        {menu && <ListRow icon="list" title={`메뉴판 ${kindWord} 맞춤으로`} href={`/menu-order/${encodeURIComponent(menu.plan_id)}`} />}
      </div>
    </SubPage>
  );
}
