// 이번 주 (Figma 06-7, 06-7-월~일, 06-7L, 06-7E) 와 바쁜 날 자세히 (06-18, 06-18b).
// 시안 C "하루씩 크게": 위에 요일 7칸, 아래에 고른 날의 점심, 저녁, 밤.
// 06: 추워지는 날 이유에는 온도계 아이콘. 쉬는 요일(요일별 장사 시간)은 "쉬는 날"로 보여 준다.
import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon, type IconName } from "@/components/icons/Icon";
import { Bone, DonnaImage, PrimaryButton } from "@/components/ui/parts";
import { ListRow, SubPage } from "@/components/ui/sub";
import { TabPage } from "@/components/ui/TabPage";
import { ApiFailure, USE_MOCK } from "@/lib/api";
import { weekdayOf, weeklyOf } from "@/lib/hours";
import { addDays, monthDay, weekdayName, ymd } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import { SKY_KO, WEATHER, type Sky } from "@/mocks/extras";
import tokens from "@/theme/tokens.json";
import type { CalendarCell, Daypart, PlanItem, Signal } from "@/types/contract";

const C = tokens.colors;

const SKY_ICON: Record<Sky, IconName> = { SUNNY: "weatherSun", PARTLY: "weatherPartly", CLOUDY: "weatherCloud", RAIN: "weatherRain" };

const DAYPARTS: { key: Daypart; label: string; icon: IconName }[] = [
  { key: "LUNCH", label: "점심", icon: "sun" },
  { key: "DINNER", label: "저녁", icon: "sunset" },
  { key: "NIGHT", label: "밤", icon: "moon" },
];
const DP_KO: Record<Daypart, string> = { LUNCH: "점심", DINNER: "저녁", NIGHT: "밤" };

/** 받침에 따라 은/는 */
function withTopic(word: string) {
  const ch = [...word].reverse().find((x) => x >= "가" && x <= "힣");
  return `${word}${ch && (ch.charCodeAt(0) - 0xac00) % 28 !== 0 ? "은" : "는"}`;
}

function chip(signal: Signal | undefined) {
  if (signal === "HIGH") return { text: "많음", box: "bg-busy border-busy", txt: "text-white" };
  if (signal === "LOW") return { text: "적음", box: "bg-calm-soft border-calm-soft", txt: "text-calm" };
  return { text: "보통", box: "bg-surface border-line", txt: "text-ink-2" };
}

function eventLabel(cells: CalendarCell[]): { tag: "GAME" | "EVENT"; refId: string; name: string } | null {
  for (const c of cells) {
    for (const r of c.reasons) {
      if (r.tag !== "GAME" && r.tag !== "EVENT") continue;
      const name =
        r.tag === "GAME"
          ? (c.reason_text.match(/(국가대표 )?(축구|야구|농구|배구|e스포츠) 경기/)?.[0] ?? "경기")
          : (c.reason_text.match(/(지역 축제|대학 축제|마라톤|지역 행사)/)?.[0] ?? "지역 행사");
      return { tag: r.tag, refId: r.ref_id, name };
    }
  }
  return null;
}

/** 하루 요약: 제목, 이유 상자 (06-7 계열 글) */
function daySummary(all: CalendarCell[], date: string, today?: string) {
  const cells = all.filter((c) => c.date === date);
  const high = cells.filter((c) => c.signal === "HIGH").map((c) => DP_KO[c.daypart]);
  const low = cells.filter((c) => c.signal === "LOW").map((c) => DP_KO[c.daypart]);
  const title = high.length ? `${high.join(", ")}에\n손님이 많아요` : "평소와\n같아요";
  const ev = eventLabel(cells);
  const seasonToday = cells.some((c) => c.reasons.some((r) => r.tag === "SEASON"));
  const seasonBefore = all.some((c) => c.date === addDays(date, -1) && c.reasons.some((r) => r.tag === "SEASON"));
  const season = !ev && seasonToday;
  let reason = "특별한 일정은 없어요";
  let sub: string | undefined;
  if (ev) {
    reason = `${ev.name}가 있어요`;
    if (low.length) sub = `${withTopic(low.join(", "))} 한가할 것 같아요`;
    else if (high.length) sub = ev.tag === "GAME" ? `${high[0]} 배달이 평소보다 늘 것 같아요` : `${high.join(", ")} 주문이 늘 것 같아요`;
  } else if (season) {
    reason = seasonBefore ? "추운 날이 이어져요" : date === today ? "오늘부터 추워져요" : "이날부터 추워져요";
    sub = "국물 메뉴가 더 나가요";
  } else if (low.length) {
    sub = `${low.join(", ")}에는 조금 한가해요`;
  }
  return { cells, busy: high.length > 0, title, reason, sub, ev, season };
}

/** 이번 주 월요일부터 일요일까지 (불러오는 중에도 요일 칸을 그린다) */
function weekOf(today: string): string[] {
  const wd = (new Date(`${today}T12:00:00+09:00`).getUTCDay() + 6) % 7;
  const mon = addDays(today, -wd);
  return Array.from({ length: 7 }, (_, i) => addDays(mon, i));
}

/**
 * 요일 줄에 보일 7일. 달력에 이번 주의 지난 날이 있으면 월요일부터 일요일까지(고정 샘플은 한 주를 준다),
 * 없으면 오늘부터 7일이다 (서버 달력은 오늘부터 35일을 주고, 쉬는 날 칸은 빠져 있다).
 * 쉬는 날도 줄에 넣으려고 달력에 있는 날짜가 아니라 이어진 7일을 만든다.
 */
function stripDays(cellDates: string[], today: string): string[] {
  const week = weekOf(today);
  if (today === week[0] || cellDates.some((d) => d >= week[0] && d < today)) return week;
  return Array.from({ length: 7 }, (_, i) => addDays(today, i));
}

type Mark = "busy" | "closed" | null;

function DayStrip({ days, today, selected, marks, onPick }: { days: string[]; today: string; selected: string; marks?: Record<string, Mark>; onPick?: (d: string) => void }) {
  return (
    <View className="mt-4 flex-row gap-1.5" accessibilityRole="tablist" accessibilityLabel="요일 고르기">
      {days.map((d) => {
        const on = d === selected;
        const isToday = d === today;
        const mark = marks?.[d] ?? null;
        const closed = mark === "closed";
        const box = on ? "border-brand bg-brand" : isToday ? "border-2 border-brand bg-brand-soft" : closed ? "border-line bg-paper" : "border-line bg-surface";
        const ink = on ? "text-brand-ink" : closed ? "text-ink-3" : "text-ink";
        return (
          <View key={d} className="flex-1 items-center gap-1">
            <Pressable
              testID={`week-day-${d}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: on }}
              accessibilityLabel={`${monthDay(d)} ${weekdayName(d)}${isToday ? ", 오늘" : ""}${mark === "busy" ? ", 바쁨" : closed ? ", 쉬는 날" : ""}`}
              disabled={!onPick}
              onPress={() => onPick?.(d)}
              className={`h-[52px] w-full items-center justify-center rounded-xl border ${box}`}
            >
              <Text className={`text-body font-medium ${ink}`} style={{ lineHeight: 24 }}>
                {weekdayName(d)[0]}
              </Text>
              <Text className={`text-small ${on ? "text-brand-ink" : closed ? "text-ink-3" : "text-ink-2"}`}>{Number(d.slice(8))}</Text>
            </Pressable>
            <Text className={`h-5 text-small font-bold ${mark === "busy" ? "text-busy" : "text-ink-3"}`}>{mark === "busy" ? "바쁨" : closed ? "쉼" : ""}</Text>
          </View>
        );
      })}
    </View>
  );
}

function WeekHeader({ range }: { range?: [string, string] }) {
  return (
    <View className="pt-2">
      <Text className="text-display text-ink" accessibilityRole="header">
        이번 주 손님
      </Text>
      {range && (
        <Text className="text-label text-ink-2">
          {monthDay(range[0])}부터 {range[0].slice(0, 7) === range[1].slice(0, 7) ? `${Number(range[1].slice(8))}일` : monthDay(range[1])}까지
        </Text>
      )}
    </View>
  );
}

function DateLine({ date, today }: { date: string; today: string }) {
  return (
    <Text className="text-label text-ink-2">
      {monthDay(date)} {weekdayName(date)}
      {date === today ? ", 오늘" : ""}
    </Text>
  );
}

function DaypartRows({ cells, loading }: { cells: CalendarCell[]; loading?: boolean }) {
  return (
    <View className="mt-3">
      {DAYPARTS.map((d) => {
        const c = chip(cells.find((x) => x.daypart === d.key)?.signal);
        return (
          <View key={d.key} className="h-12 flex-row items-center gap-3 border-b border-line">
            <Icon name={d.icon} size={26} color={C["ink-2"]} />
            <Text className="flex-1 text-body text-ink">{d.label}</Text>
            {loading ? (
              <Bone className="h-9 w-[76px] rounded-[10px]" />
            ) : (
              <View className={`h-9 w-[76px] items-center justify-center rounded-[10px] border ${c.box}`} accessibilityLabel={`${d.label} 손님 ${c.text}`}>
                <Text className={`text-small font-bold ${c.txt}`}>{c.text}</Text>
              </View>
            )}
          </View>
        );
      })}
    </View>
  );
}

export function WeekScreen() {
  const { data, now, error, refetch } = useHome();
  // 개발 화면에서 /week?day=2026-11-19 처럼 고른 날로 연다 (06-7-월~일 검토용)
  const params = useLocalSearchParams<{ day?: string }>();
  const [picked, setPicked] = useState<string | null>(null);
  // 주소의 day가 바뀌면 고른 날을 비운다 (렌더 중에 바로 맞춘다)
  const [dayParam, setDayParam] = useState(params.day);
  if (dayParam !== params.day) {
    setDayParam(params.day);
    setPicked(null);
  }
  const today = ymd(now);

  if (!data) {
    if (error) {
      // 06-7E 인터넷이 끊겼을 때. 서버가 아직 다루지 못하는 가게(자정을 넘겨 여는 가게)면 그렇게 알린다
      const notReady = error instanceof ApiFailure && error.code === "OVERNIGHT_STORE_NOT_SUPPORTED";
      return (
        <TabPage>
          <WeekHeader />
          <View className="flex-1 items-center justify-center">
            <DonnaImage img={notReady ? "q-clipboard" : "q-laptop"} size={160} />
            <Text className="mt-3 text-center text-display text-ink">{notReady ? "아직 준비 중이에요" : "인터넷이\n잠시 끊겼어요"}</Text>
            <Text className="mt-2 text-center text-body text-ink-2">{notReady ? "자정을 넘겨 여는 가게는\n곧 쓸 수 있게 준비하고 있어요" : "연결되면 이번 주를 다시 보여 드릴게요"}</Text>
          </View>
          <PrimaryButton onPress={() => refetch()}>다시 불러오기</PrimaryButton>
        </TabPage>
      );
    }
    // 06-7L 불러오는 중: 요일 칸과 시간대 이름은 그대로, 내용만 뼈대로
    const days = USE_MOCK ? weekOf(today) : stripDays([], today);
    return (
      <TabPage>
        <WeekHeader range={[days[0], days[6]]} />
        <DayStrip days={days} today={today} selected={today} />
        <View className="mt-3" accessibilityRole="progressbar" accessibilityLabel="이번 주를 불러오고 있어요">
          <DateLine date={today} today={today} />
          <View className="flex-row items-center justify-between">
            <View className="flex-1 gap-3 py-2">
              <Bone className="h-6 w-36" />
              <Bone className="h-6 w-44" />
            </View>
            <DonnaImage img="b1-1" size={72} />
          </View>
          <View className="mt-2 gap-2 rounded-2xl border border-line bg-surface px-4 py-4">
            <Bone className="h-4 w-[85%]" />
            <Bone className="h-4 w-[55%]" />
          </View>
          <DaypartRows cells={[]} loading />
        </View>
      </TabPage>
    );
  }

  const cells = data.calendar.cells;
  const days = stripDays([...new Set(cells.map((c) => c.date))], today);
  const weekly = weeklyOf(data.settings.settings);
  const isClosed = (d: string) => weekly[weekdayOf(d)] === null;
  const marks: Record<string, Mark> = {};
  for (const d of days) marks[d] = isClosed(d) ? "closed" : cells.some((c) => c.date === d && c.signal === "HIGH") ? "busy" : null;
  const want = picked ?? (typeof params.day === "string" ? params.day : null);
  const selected = want && days.includes(want) ? want : days.includes(today) ? today : days[0];
  const closed = isClosed(selected);
  const s = daySummary(cells, selected, today);
  const w = USE_MOCK ? WEATHER[selected] : undefined;
  const linkTo = !closed && s.ev ? `/week/${encodeURIComponent(s.ev.refId)}` : null;
  const busy = !closed && s.busy;
  const seasonMenu = !closed && s.season && !linkTo ? data.plan.plan_items.find((p) => p.task_type === "MENU_ORDER" && p.target_date === selected) : undefined;

  return (
    <TabPage>
      <WeekHeader range={[days[0], days[days.length - 1]]} />
      <DayStrip days={days} today={today} selected={selected} marks={marks} onPick={setPicked} />

      <View className="mt-3" accessibilityLiveRegion="polite">
        <DateLine date={selected} today={today} />
        <View className="flex-row items-start justify-between">
          <Text className="flex-1 text-display text-ink">{closed ? "쉬는 날이에요" : s.title}</Text>
          <DonnaImage img={busy ? "b1-1" : "b2-1"} size={72} />
        </View>
        <View className={`mt-2 flex-row items-center gap-3 rounded-2xl px-4 py-3 ${busy ? "bg-busy-soft" : !closed && s.season ? "bg-brand-soft" : "border border-line bg-surface"}`}>
          {!closed && s.season && <Icon name="thermometerDown" size={28} color={C.calm} />}
          <View className="min-w-0 flex-1">
            <Text className="text-body font-medium text-ink">{closed ? "가게 문을 닫는 날이에요" : s.reason}</Text>
            {closed ? <Text className="text-label text-ink-2">이날은 알림을 보내지 않아요</Text> : s.sub ? <Text className="text-label text-ink-2">{s.sub}</Text> : null}
          </View>
          {w && (
            <View className="flex-row items-center gap-2" accessibilityLabel={`${SKY_KO[w.sky]}, 낮 ${w.high}도, 아침 ${w.low}도`}>
              <Icon name={SKY_ICON[w.sky]} size={32} color={C.brand} />
              <View className="items-end">
                <Text className="text-title text-ink">{w.high}°</Text>
                <Text className="text-small text-ink-2">아침 {w.low}°</Text>
              </View>
            </View>
          )}
        </View>
        {!closed && <DaypartRows cells={s.cells} />}
        {linkTo && <ListRow icon="list" title="같이 하면 좋은 일 2가지" href={linkTo} testID="week-together" />}
        {/* 06-7-수: 추워지는 날은 그날 메뉴판 순서 바꾸기로 바로 간다 */}
        {seasonMenu && <ListRow icon="list" title="국물 메뉴를 위로 올리는 날" href={`/menu-order/${encodeURIComponent(seasonMenu.plan_id)}`} testID="week-season-menu" />}
      </View>
    </TabPage>
  );
}

/** 06-18, 06-18b: 바쁜 날 자세히. 주소는 /week/{행사 ref_id} */
export function WeekDetailScreen() {
  const params = useLocalSearchParams<{ refId: string }>();
  const refId = decodeURIComponent(String(params.refId ?? ""));
  const { data } = useHome();
  if (!data) {
    return (
      <SubPage title="이번 주" backHref="/week">
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
  const max = first ? Math.max(first.expected_sales, first.baseline_sales) : 1;

  return (
    <SubPage title={title}>
      <Icon name={ev?.tag === "GAME" ? "ball" : "tent"} size={48} color={C.busy} />
      <Text className="mt-3 text-display text-ink">
        {`${ev?.name.replace("국가대표 ", "") ?? ""}로\n`}
        {multi ? `${dps.join(", ")}이 바빠요` : ev?.tag === "GAME" ? "배달이 늘 것 같아요" : "손님이 늘 것 같아요"}
      </Text>
      {multi && (
        <Text className="mt-1 text-body text-ink-2">
          {days.map((d) => weekdayName(d)).join("과 ")} {days.length === 2 ? "이틀" : `${days.length}일`} 동안이에요
        </Text>
      )}

      {!multi && first && (
        <View className="mt-6 gap-2">
          {[
            { label: `평소 ${weekdayName(first.date)} ${DP_KO[first.daypart]}`, v: first.baseline_sales, bar: C["ink-3"], tcls: "text-ink-2" },
            { label: `이번 ${weekdayName(first.date)} 예상`, v: first.expected_sales, bar: C.busy, tcls: "text-busy" },
          ].map((r) => (
            <View key={r.label} className="gap-1.5">
              <View className="flex-row items-end justify-between">
                <Text className="text-label text-ink-2">{r.label}</Text>
                <Text className={`text-body font-bold ${r.tcls}`}>{r.v.toLocaleString("ko-KR")}원</Text>
              </View>
              <View className="h-2.5 overflow-hidden rounded-full bg-line">
                <View className="h-full rounded-full" style={{ width: `${(r.v / max) * 100}%`, backgroundColor: r.bar }} />
              </View>
            </View>
          ))}
        </View>
      )}

      <View className="mt-8 border-t border-line pt-4">
        <Text className="text-label text-ink-2">같이 하면 좋은 일</Text>
      </View>
      <View>
        {poster && <ListRow icon="image" title={`${kindWord} 포스터 만들기`} href={`/poster/${encodeURIComponent(poster.plan_id)}`} testID="week-poster" />}
        {menu && <ListRow icon="list" title={`메뉴판 ${kindWord} 맞춤으로`} href={`/menu-order/${encodeURIComponent(menu.plan_id)}`} testID="week-menu" />}
      </View>
    </SubPage>
  );
}
