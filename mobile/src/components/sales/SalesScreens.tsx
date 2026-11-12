// 매출 (Figma 06-70 첫 화면, 06-71 이번 주와 지난주, 06-72 메뉴별, 06-73 시간대와 요일, 06-74 어디서 누가, 06-75 달별).
// 첫 화면은 사장님이 가장 자주 보는 두 가지(오늘 실시간, 이번 주와 지난주)만 크게 보여 주고, 나머지는 눌러서 들어간다.
// 그래프는 View 막대로 그린다 (Next.js 판의 div 막대와 같은 방식).
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { SafeAreaView } from "react-native-safe-area-context";
import { Icon, type IconName } from "@/components/icons/Icon";
import { back, go } from "@/components/ui/nav";
import { Bone, PrimaryButton } from "@/components/ui/parts";
import { ApiFailure, salesApi, USE_MOCK } from "@/lib/api";
import { devFlags } from "@/lib/dev";
import { useHome } from "@/lib/useHome";
import { withSubject } from "@/lib/labels";
import { addDays, currentNow, hhmm, monthDay, weekdayName } from "@/lib/time";
import { RESULT_NOTICES } from "@/mocks/extras";
import tokens from "@/theme/tokens.json";
import type { CalendarCell } from "@/types/contract";
import type { SalesPeriod } from "@/types/sales";

const C = tokens.colors;

// ---------- 숫자 ----------
const won = (n: number) => `${Math.round(n).toLocaleString("ko-KR")}원`;
/** 1,249만 원 */
const man = (n: number) => `${Math.round(n / 1e4).toLocaleString("ko-KR")}만 원`;
/** 1.7만 원 (좁은 칸에 넣는 짧은 금액) */
const manShort = (n: number) => `${(Math.round(n / 1e3) / 10).toLocaleString("ko-KR")}만 원`;
const pct = (a: number, b: number) => (b ? Math.round(((a - b) / b) * 100) : 0);
const DP_ORDER = ["LUNCH", "DINNER", "NIGHT"] as const;
const DP_KO = { LUNCH: "점심", DINNER: "저녁", NIGHT: "밤" } as const;
const WD = ["월", "화", "수", "목", "금", "토", "일"];
/** 목업 주문을 시간대로 나누는 기준 (목업 서버와 같다: 15시 전 점심, 20시 전 저녁) */
const partOf = (h: number): keyof typeof DP_KO => (h < 15 ? "LUNCH" : h < 20 ? "DINNER" : "NIGHT");
/** 국물 메뉴는 "그릇"으로 센다 (06-72 "곱창전골 84그릇") */
const SOUP = /(전골|탕|찌개|국밥|칼국수|잔치국수|멸치국수|우동|라면)/;
const unitOf = (name: string) => (SOUP.test(name) ? "그릇" : "개");

/** 오르면 초록 화살표, 내리면 빨강 화살표 */
function Change({ diff, text, size = "body" }: { diff: number; text: string; size?: "body" | "label" }) {
  const same = Math.abs(diff) < 1;
  const color = same ? C["ink-2"] : diff > 0 ? C.done : C.urgent;
  return (
    <View className="flex-row items-center gap-1.5">
      {!same && <Icon name={diff > 0 ? "arrowUp" : "arrowDown"} size={size === "body" ? 20 : 18} color={color} />}
      <Text className={size === "body" ? "text-body font-medium" : "text-label text-ink"} style={size === "body" ? { color } : undefined}>
        {text}
      </Text>
    </View>
  );
}

function cmp(diff: number, unit: string, future?: boolean) {
  if (Math.abs(diff) < 1) {
    // "어제 이 시간보다 비슷해요"는 틀린 말이다. "어제 이 시간과 비슷해요"로 쓴다 (받침에 따라 과/와)
    const base = unit.replace(/보다$/, "");
    const code = base.charCodeAt(base.length - 1) - 0xac00;
    const withJosa = unit === base ? unit : `${base}${code >= 0 && code % 28 !== 0 ? "과" : "와"}`;
    return `${withJosa} 비슷${future ? "할 것 같아요" : "해요"}`;
  }
  const up = diff > 0;
  return `${unit} ${Math.abs(diff)}% ${up ? (future ? "많을 것 같아요" : "많아요") : future ? "적을 것 같아요" : "적어요"}`;
}

function DiffPill({ diff, prefix = "" }: { diff: number; prefix?: string }) {
  const up = diff >= 0;
  return (
    <View className={`rounded-full px-2.5 py-1 ${up ? "bg-done-soft" : "bg-urgent-soft"}`}>
      <Text className={`text-label ${up ? "text-done" : "text-urgent"}`}>{`${prefix}${up ? "+" : ""}${diff}%`}</Text>
    </View>
  );
}

function Card({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <View accessibilityLabel={label} className="gap-3 rounded-card border border-line bg-surface p-5">
      {children}
    </View>
  );
}

function Stat({ label, value, plain }: { label: string; value: string; plain?: boolean }) {
  return (
    <View className={`flex-1 gap-0.5 rounded-[14px] px-3.5 py-2.5 ${plain ? "border border-line bg-surface" : "bg-paper"}`}>
      <Text className="text-small text-ink-2">{label}</Text>
      <Text className={`${plain ? "text-body font-bold" : "text-title"} text-ink`} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

function Chips<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <View className="flex-row gap-2" accessibilityRole="radiogroup" accessibilityLabel="기간">
      {options.map(([k, label]) => (
        <Pressable
          key={k}
          testID={`period-${k}`}
          accessibilityRole="radio"
          accessibilityState={{ checked: value === k }}
          onPress={() => onChange(k)}
          className={`h-10 justify-center rounded-full border px-4 ${value === k ? "border-brand bg-brand" : "border-line bg-surface"}`}
        >
          <Text className={`text-label ${value === k ? "text-brand-ink" : "text-ink-2"}`}>{label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

/** 한 줄 띠그래프. 색은 토큰 hex, 옅게 할 때는 opacity */
function Stacked({ parts }: { parts: { key: string; value: number; color: string; opacity?: number }[] }) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  return (
    <View className="h-4 flex-row gap-0.5 overflow-hidden rounded-md" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {parts.map((p) => (
        <View key={p.key} style={{ flex: p.value / total, backgroundColor: p.color, opacity: p.opacity ?? 1 }} />
      ))}
    </View>
  );
}

function Dot({ color, opacity = 1 }: { color: string; opacity?: number }) {
  return <View className="h-3 w-3 rounded-sm" style={{ backgroundColor: color, opacity }} />;
}

function Small({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <Text className={`text-small text-ink-2 ${className}`}>{children}</Text>;
}

// ---------- 화면 틀 ----------
function SalesPage({ title, back: hasBack, children }: { title: string; back?: boolean; children: ReactNode }) {
  return (
    <SafeAreaView edges={["top"]} style={{ flex: 1, backgroundColor: C.paper }}>
      <ScrollView contentContainerStyle={{ flexGrow: 1, paddingHorizontal: 24, paddingTop: 12, paddingBottom: 24, gap: 16 }}>
        {hasBack && (
          <View className="h-11 flex-row items-center">
            <Pressable
              testID="back"
              accessibilityRole="button"
              accessibilityLabel="뒤로"
              onPress={() => back("/sales")}
              className="-ml-2.5 h-11 w-11 items-center justify-center rounded-full active:bg-brand-soft"
            >
              <Icon name="chevL" size={26} />
            </Pressable>
          </View>
        )}
        <Text className={`text-display text-ink ${hasBack ? "" : "pt-2"}`} accessibilityRole="header">
          {title}
        </Text>
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

/** 매출 응답 불러오기. 오늘 실시간은 1분마다 새로 받는다. 개발 화면에서 가상 시각을 바꾸면 다시 받는다. */
function useSales<T>(key: string, fn: (now: Date) => Promise<T>, live = false) {
  const dev = devFlags.useValue();
  return useQuery({
    queryKey: ["sales", key, dev.now ?? "now"],
    queryFn: () => fn(currentNow()),
    refetchInterval: live ? 60_000 : false,
    retry: 0,
  });
}

function Problem({ error, onRetry, id }: { error: unknown; onRetry: () => void; id: string }) {
  const offline = error instanceof ApiFailure && error.offline;
  return (
    <Card label="불러오지 못했어요">
      <View className="flex-row items-center gap-2">
        <Icon name="wifiOff" size={24} color={C.urgent} />
        <Text className="text-body font-medium text-urgent">{offline ? "인터넷이 잠시 끊겼어요" : "매출을 불러오지 못했어요"}</Text>
      </View>
      <Small>연결되면 다시 보여 드릴게요</Small>
      <PrimaryButton testID={`retry-${id}`} onPress={onRetry}>
        다시 불러오기
      </PrimaryButton>
    </Card>
  );
}

const Loading = ({ h }: { h: number }) => <Bone className="w-full rounded-card" style={{ height: h }} />;

/** 이번 주 달력에서 그 날 매출이 달라지는 까닭 한 줄 (06-71 "저녁에 축구 경기", "지역 축제", "추워져요, 국물 메뉴가 늘어요") */
function dayReason(cells: CalendarCell[] | undefined, date: string): string | null {
  // 달력을 아직 못 받았으면 까닭 줄을 비워 둔다 (매출 응답의 "추워져요, 경기"는 시안 글과 달라서 쓰지 않는다).
  if (!cells?.length) return null;
  const day = cells.filter((c) => c.date === date);
  for (const c of day) {
    for (const r of c.reasons) {
      if (r.tag === "GAME") {
        const name = c.reason_text.match(/(축구|야구|농구|배구|e스포츠) 경기/)?.[0] ?? "경기";
        const high = day.find((x) => x.signal === "HIGH" && x.reasons.some((y) => y.ref_id === r.ref_id));
        return high ? `${DP_KO[high.daypart]}에 ${name}` : name;
      }
      if (r.tag === "EVENT") return c.reason_text.match(/(지역 축제|대학 축제|마라톤|지역 행사)/)?.[0] ?? "지역 행사";
    }
  }
  const season = (d: string) => cells.some((c) => c.date === d && c.reasons.some((r) => r.tag === "SEASON"));
  if (season(date) && !season(addDays(date, -1))) return "추워져요, 국물 메뉴가 늘어요";
  return null;
}

// ---------- 06-70 첫 화면 ----------
function TodayCard() {
  const { data, error, refetch } = useSales("live", (n) => salesApi.live(n), true);
  if (error) return <Problem id="live" error={error} onRetry={() => refetch()} />;
  if (!data) return <Loading h={430} />;
  const wd = weekdayName(data.date);
  const max = Math.max(...data.hourly.map((h) => Math.max(h.amount, h.usual)), 1);
  // 지금까지 가장 많이 판 시간대 (06-70 "지금까지 점심이 제일 많았어요")
  const byPart = new Map<string, number>();
  for (const h of data.hourly) if (h.state !== "future") byPart.set(partOf(h.hour), (byPart.get(partOf(h.hour)) ?? 0) + h.amount);
  const best = [...byPart.entries()].sort((a, b) => b[1] - a[1])[0];
  const share = data.usualDay ? Math.min(100, Math.round((data.amount / data.usualDay) * 100)) : 0;
  return (
    <Card label="오늘 매출">
      <View className="flex-row items-center">
        <Text className="flex-1 text-body font-medium text-ink-2">오늘 매출</Text>
        <View className="flex-row items-center gap-1.5 rounded-full bg-done-soft px-2.5 py-1">
          <View className="h-2 w-2 rounded-full bg-done" />
          <Text className="text-label text-done">지금 {hhmm(data.now)}</Text>
        </View>
      </View>
      <Text className="text-display text-ink" style={{ fontSize: 36, lineHeight: 46 }}>
        {won(data.amount)}
      </Text>
      <Change diff={pct(data.amount, data.yesterdaySame)} text={cmp(pct(data.amount, data.yesterdaySame), "어제 이 시간보다")} />
      <View className="gap-1.5">
        <Small>{`평소 ${wd} 하루 ${man(data.usualDay)} 중 ${share}%`}</Small>
        <View
          className="h-2.5 overflow-hidden rounded-full bg-line"
          accessibilityRole="progressbar"
          accessibilityValue={{ min: 0, max: 100, now: share }}
          accessibilityLabel="평소 하루와 비교"
        >
          <View className="h-full rounded-full bg-brand" style={{ width: `${share}%` }} />
        </View>
      </View>
      <View className="flex-row gap-2.5">
        <Stat label="주문" value={`${data.orders}건`} />
        <Stat label="주문 1번 평균" value={won(data.avg)} />
      </View>
      <View className="gap-1.5">
        <Small>시간별</Small>
        <View className="h-[76px] flex-row items-end gap-1" accessibilityRole="image" accessibilityLabel={`시간별 매출. 지금까지 ${best ? DP_KO[best[0] as keyof typeof DP_KO] : ""}이 제일 많았어요`}>
          {data.hourly.map((h) => {
            const v = h.state === "future" ? h.usual : h.amount;
            return (
              <View
                key={h.hour}
                className={`flex-1 rounded-t ${h.state === "future" ? "border border-dashed border-ink-3 bg-brand-soft" : "bg-brand"}`}
                style={{ height: Math.max(4, (v / max) * 76), opacity: h.state === "now" ? 0.55 : 1 }}
              />
            );
          })}
        </View>
        <View className="flex-row gap-1">
          {data.hourly.map((h) => (
            <Text key={h.hour} className="flex-1 text-center text-small text-ink-3">
              {h.hour % 2 ? h.hour : ""}
            </Text>
          ))}
        </View>
        <Small>{`점선은 평소 ${wd}이에요${best && best[1] && data.orders >= 5 ? `\n지금까지 ${withSubject(DP_KO[best[0] as keyof typeof DP_KO])} 제일 많았어요` : ""}`}</Small>
      </View>
    </Card>
  );
}

function WeekCard() {
  const { data, error, refetch } = useSales("weeks", (n) => salesApi.weeks(n));
  if (error) return <Problem id="weeks" error={error} onRetry={() => refetch()} />;
  if (!data) return <Loading h={360} />;
  const max = Math.max(...data.days.map((d) => Math.max(d.amount, d.last)), 1);
  const events = data.days.filter((d) => d.state === "forecast" && d.reasons.some((r) => r === "경기" || r === "축제"));
  // 같은 일은 요일을 묶는다: "목요일 경기, 토요일과 일요일 축제"
  const groups = new Map<string, string[]>();
  for (const d of events) {
    const k = d.reasons.find((r) => r === "경기" || r === "축제")!;
    groups.set(k, [...(groups.get(k) ?? []), weekdayName(d.date)]);
  }
  const why = [...groups.entries()].map(([k, ds]) => `${ds.join("과 ")} ${k}`).join(", ");
  const H = 120;
  return (
    <Pressable testID="sales-week-card" accessibilityRole="button" accessibilityLabel="이번 주와 지난주 자세히 보기" onPress={() => go("/sales/week")}>
      <Card label="이번 주와 지난주">
        <View className="flex-row items-center">
          <Text className="flex-1 text-body font-medium text-ink-2">이번 주 지금까지</Text>
          <View className="flex-row items-center gap-0.5">
            <Text className="text-label text-brand">자세히</Text>
            <Icon name="chevR" size={18} color={C.brand} />
          </View>
        </View>
        <Text className="text-display text-ink" style={{ fontSize: 30, lineHeight: 40 }}>
          {won(data.toDate)}
        </Text>
        <Change diff={pct(data.toDate, data.lastSamePeriod)} text={cmp(pct(data.toDate, data.lastSamePeriod), "지난주 같은 때보다")} />
        <View className="flex-row items-end gap-1.5" style={{ height: H }} accessibilityRole="image" accessibilityLabel="요일별 이번 주와 지난주 매출">
          {data.days.map((d) => (
            <View key={d.date} className="flex-1 flex-row items-end gap-[3px]">
              <View
                className={`flex-1 rounded-t ${d.state === "forecast" ? "border border-dashed border-brand bg-brand-soft" : "bg-brand"}`}
                style={{ height: Math.max(4, (d.amount / max) * H), opacity: d.state === "now" ? 0.55 : 1 }}
              />
              <View className="flex-1 rounded-t bg-line" style={{ height: Math.max(4, (d.last / max) * H) }} />
            </View>
          ))}
        </View>
        <View className="flex-row gap-1.5">
          {data.days.map((d) => (
            <Text key={d.date} className={`flex-1 text-center text-small ${d.state === "now" ? "font-bold text-ink" : "text-ink-3"}`}>
              {WD[(new Date(`${d.date}T12:00:00+09:00`).getUTCDay() + 6) % 7]}
            </Text>
          ))}
        </View>
        <View className="flex-row items-center gap-3.5">
          <View className="flex-row items-center gap-1.5">
            <Dot color={C.brand} />
            <Small>이번 주</Small>
          </View>
          <View className="flex-row items-center gap-1.5">
            <View className="h-3 w-3 rounded-sm border border-dashed border-brand bg-brand-soft" />
            <Small>예상</Small>
          </View>
          <View className="flex-row items-center gap-1.5">
            <Dot color={C.line} />
            <Small>지난주</Small>
          </View>
        </View>
        <View className="flex-row gap-2.5">
          <Stat label="지난주 합계" value={man(data.lastTotal)} />
          <Stat label="이번 주 예상" value={man(data.forecastTotal)} />
        </View>
        {why ? <Small>{`${why}로 더 늘 것 같아요`}</Small> : null}
      </Card>
    </Pressable>
  );
}

function MoreRow({ href, icon, title, sub, id }: { href: string; icon: IconName; title: string; sub?: string; id: string }) {
  return (
    <Pressable testID={`sales-more-${id}`} accessibilityRole="button" onPress={() => go(href)} className="min-h-14 flex-row items-center gap-3 border-b border-line py-3 active:bg-brand-soft">
      <Icon name={icon} size={24} color={C["ink-2"]} />
      <Text className="flex-1 text-body text-ink">{title}</Text>
      {sub ? <Text className="text-label text-ink-2">{sub}</Text> : null}
      <Icon name="chevR" size={20} color={C["ink-3"]} />
    </Pressable>
  );
}

const mLabel = (m: string) => `${Number(m.slice(5))}월`;

export function SalesHomeScreen() {
  const menus = useSales("menus-week", (n) => salesApi.menus(n, "week"));
  const times = useSales("times-4w", (n) => salesApi.times(n, "4w"));
  const ch = useSales("channels-week", (n) => salesApi.channels(n, "week"));
  const months = useSales("months", (n) => salesApi.months(n));
  const top = menus.data?.items[0];
  const dpTotal = times.data?.dayparts.reduce((a, d) => a + d.amount, 0) ?? 0;
  const dpTop = times.data ? [...times.data.dayparts].sort((a, b) => b.amount - a.amount)[0] : null;
  const c = ch.data?.customers;
  const known = c ? c.regular.amount + c.fresh.amount + c.other.amount : 0;
  const thisMonth = months.data?.months.at(-1);
  return (
    <SalesPage title="매출">
      <TodayCard />
      <WeekCard />
      <View accessibilityLabel="더 알아보기" className="mt-1">
        <Text className="text-title text-ink">더 알아보기</Text>
        <MoreRow id="menu" href="/sales/menu" icon="list" title="메뉴별" sub={top ? `${withSubject(top.name)} 1등` : undefined} />
        <MoreRow id="time" href="/sales/time" icon="clock" title="시간대와 요일" sub={dpTop && dpTotal ? `${withSubject(dpTop.label)} ${Math.round((dpTop.amount / dpTotal) * 100)}%` : undefined} />
        <MoreRow id="channel" href="/sales/channel" icon="scooter" title="배달앱과 단골" sub={c && known ? `단골이 ${Math.round((c.regular.amount / known) * 100)}%` : undefined} />
        <MoreRow id="month" href="/sales/month" icon="trendUp" title="달별 흐름" sub={thisMonth?.forecast ? `${mLabel(thisMonth.month)} 예상 ${man(thisMonth.forecast)}` : undefined} />
      </View>
    </SalesPage>
  );
}

// ---------- 06-71 이번 주와 지난주 ----------
export function SalesWeekScreen() {
  const { data, error, refetch } = useSales("weeks", (n) => salesApi.weeks(n));
  // 예상 까닭은 이번 주 달력에서 고른다 (오늘 화면과 같은 캐시)
  const home = useHome();
  const cells = home.data?.calendar.cells;
  const nowText = hhmm(home.now.toISOString());
  const diff = data ? data.forecastTotal - data.lastTotal : 0;
  const p = data ? pct(data.forecastTotal, data.lastTotal) : 0;
  return (
    <SalesPage title="이번 주와 지난주" back>
      {error ? (
        <Problem id="weeks" error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <Loading h={520} />
      ) : (
        <>
          <Card label="합계">
            <View className="flex-row gap-2.5">
              <View className="flex-1">
                <Small>이번 주 (예상 포함)</Small>
                <Text className="text-title text-ink">{man(data.forecastTotal)}</Text>
              </View>
              <View className="flex-1">
                <Small>지난주</Small>
                <Text className="text-title text-ink">{man(data.lastTotal)}</Text>
              </View>
            </View>
            <Change diff={p} text={Math.abs(p) < 1 ? "지난주와 비슷할 것 같아요" : `${man(Math.abs(diff))}, ${Math.abs(p)}% 더 ${p > 0 ? "많을" : "적을"} 것 같아요`} />
          </Card>
          <View accessibilityLabel="요일별">
            {data.days.map((d) => {
              const why = d.state === "forecast" ? dayReason(cells, d.date) : null;
              return (
                <View key={d.date} className="flex-row items-center gap-3 border-b border-line py-3.5">
                  <View className="w-24">
                    <Text className="text-body font-medium text-ink">{weekdayName(d.date)}</Text>
                    <Small>{d.state === "forecast" ? "예상" : d.state === "now" ? `오늘, ${nowText}까지` : monthDay(d.date)}</Small>
                  </View>
                  <View className="min-w-0 flex-1">
                    <Text className="text-title text-ink">{man(d.amount)}</Text>
                    <Small>지난주 {man(d.last)}</Small>
                    {d.state === "now" && d.usual ? <Small>평소면 {man(d.usual)}쯤</Small> : null}
                    {why ? <Small>{why}</Small> : null}
                  </View>
                  {d.state === "now" ? <Text className="text-label text-ink-2">진행 중</Text> : <DiffPill diff={pct(d.amount, d.last)} />}
                </View>
              );
            })}
          </View>
          <Small>{"예상은 이번 주 달력(행사, 경기, 날씨)으로 계산했어요\n날마다 저녁에 다시 맞춰요"}</Small>
        </>
      )}
    </SalesPage>
  );
}

// ---------- 06-72 메뉴별 ----------
const PERIOD_LABEL: Record<SalesPeriod, string> = { today: "오늘", week: "이번 주", "4w": "지난 4주", month: "이번 달" };
const PREV_LABEL: Record<SalesPeriod, string> = { today: "어제보다", week: "지난주보다", "4w": "그전 4주보다", month: "지난달보다" };

export function SalesMenuScreen() {
  const [period, setPeriod] = useState<SalesPeriod>("week");
  const { data, error, refetch } = useSales(`menus-${period}`, (n) => salesApi.menus(n, period));
  const home = useHome();
  // 추워지는 날이 시작된 뒤 1등이 국물 메뉴면 까닭을 붙인다 (06-72 "추워지면서 국물 메뉴가 잘 나가요")
  const cold = (home.data?.calendar.cells ?? []).some((c) => c.reasons.some((r) => r.tag === "SEASON") && c.date <= (data?.to ?? ""));
  const top = data?.items[0];
  const tp = top ? pct(top.amount, top.prevAmount) : 0;
  return (
    <SalesPage title="메뉴별 매출" back>
      <Chips
        value={period}
        onChange={setPeriod}
        options={[
          ["today", "오늘"],
          ["week", "이번 주"],
          ["month", "이번 달"],
        ]}
      />
      {error ? (
        <Problem id="menus" error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <Loading h={480} />
      ) : !top ? (
        <Text className="text-body text-ink-2">아직 팔린 메뉴가 없어요</Text>
      ) : (
        <>
          <View className="gap-1.5 rounded-card bg-brand-soft p-5" accessibilityLabel="1등 메뉴">
            <Text className="text-label text-brand">{PERIOD_LABEL[period]} 1등</Text>
            <Text className="text-title text-ink">{`${top.name} ${top.qty}${unitOf(top.name)}`}</Text>
            {top.prevAmount > 0 && (
              <Change size="label" diff={tp} text={Math.abs(tp) < 1 ? `${PREV_LABEL[period]} 비슷해요` : `${PREV_LABEL[period]} ${Math.abs(tp)}% ${tp > 0 ? "늘었어요" : "줄었어요"}`} />
            )}
            {cold && SOUP.test(top.name) ? <Small className="mt-1">추워지면서 국물 메뉴가 잘 나가요</Small> : null}
          </View>
          <View accessibilityLabel="메뉴 순위">
            {data.items.slice(0, 5).map((m, i) => (
              <View key={m.name} className="gap-2 border-b border-line py-3.5">
                <View className="flex-row items-center gap-2.5">
                  <Text className={`w-5 text-title ${i === 0 ? "text-brand" : "text-ink-2"}`}>{i + 1}</Text>
                  <Text className="flex-1 text-body font-medium text-ink">{m.name}</Text>
                  <Text className="text-body font-medium text-ink">{man(m.amount)}</Text>
                  {m.prevAmount > 0 && <DiffPill diff={pct(m.amount, m.prevAmount)} />}
                </View>
                <View className="flex-row items-center gap-2">
                  <View className="h-2 flex-1 overflow-hidden rounded-full bg-line">
                    <View className="h-full rounded-full" style={{ width: `${(m.amount / top.amount) * 100}%`, backgroundColor: i === 0 ? C.brand : C["ink-2"] }} />
                  </View>
                  <Text className="w-10 text-right text-small text-ink-2">{m.qty}개</Text>
                </View>
              </View>
            ))}
          </View>
          <Small>막대는 1등 메뉴 매출과 비교한 길이예요</Small>
        </>
      )}
    </SalesPage>
  );
}

// ---------- 06-73 시간대와 요일 ----------
const DP_COLOR: Record<string, string> = { LUNCH: C.calm, DINNER: C.brand, NIGHT: C.busy };

/** 목업 범위 글("15시 전", "15시 ~ 20시", "20시 뒤")을 가게 장사 시간으로 "11~15시" 꼴로 */
function rangeText(range: string, open?: string, close?: string): string {
  const oh = open ? Number(open.slice(0, 2)) : null;
  const ch = close ? Number(close.slice(0, 2)) || 24 : null;
  let m = range.match(/^(\d+)시 전$/);
  if (m && oh !== null) return `${oh}~${m[1]}시`;
  m = range.match(/^(\d+)시 ~ (\d+)시$/);
  if (m) return `${m[1]}~${m[2]}시`;
  m = range.match(/^(\d+)시 뒤$/);
  if (m && ch !== null) return `${m[1]}~${ch}시`;
  return range;
}

export function SalesTimeScreen() {
  const [period, setPeriod] = useState<SalesPeriod>("4w");
  const { data, error, refetch } = useSales(`times-${period}`, (n) => salesApi.times(n, period));
  const st = useHome().data?.settings.settings;
  const total = data?.dayparts.reduce((a, d) => a + d.amount, 0) ?? 0;
  const top = data && [...data.dayparts].sort((a, b) => b.amount - a.amount)[0];
  const max = data ? Math.max(...data.grid.map((g) => g.avg), 1) : 1;
  const peak = data ? [...data.grid].sort((a, b) => b.avg - a.avg)[0] : null;
  const dpKo = (k: string) => data?.dayparts.find((d) => d.key === k)?.label ?? "";
  return (
    <SalesPage title="언제 많이 팔렸나" back>
      <Chips
        value={period}
        onChange={setPeriod}
        options={[
          ["week", "이번 주"],
          ["4w", "지난 4주"],
          ["month", "이번 달"],
        ]}
      />
      {error ? (
        <Problem id="times" error={error} onRetry={() => refetch()} />
      ) : !data || !top ? (
        <Loading h={520} />
      ) : (
        <>
          <Card label="시간대">
            <Text className="text-title text-ink">{`${top.label}에 가장 많이 팔려요`}</Text>
            <Stacked parts={DP_ORDER.map((k) => ({ key: k, value: data.dayparts.find((d) => d.key === k)?.amount ?? 0, color: DP_COLOR[k] }))} />
            <Small>{data.dayparts.map((d) => `${d.label} ${rangeText(d.range, st?.open_time, st?.close_time)}`).join(", ")}</Small>
            <View>
              {data.dayparts.map((d) => (
                <View key={d.key} className="flex-row items-center gap-2.5 py-2.5">
                  <Dot color={DP_COLOR[d.key]} />
                  <Text className="flex-1 text-body text-ink">{d.label}</Text>
                  <Text className="text-body font-medium text-ink">{man(d.amount)}</Text>
                  <Text className="w-11 text-right text-label text-ink-2">{total ? Math.round((d.amount / total) * 100) : 0}%</Text>
                </View>
              ))}
            </View>
          </Card>
          <Card label="요일마다 바쁜 때">
            <Text className="text-title text-ink">요일마다 바쁜 때</Text>
            <Small>진할수록 많이 팔렸어요. 지난 4주 평균이에요</Small>
            <View className="gap-1" accessibilityLabel="요일과 시간대별 평균 매출">
              <View className="flex-row gap-1">
                <View className="w-9" />
                {WD.map((w) => (
                  <Text key={w} className="flex-1 text-center text-small text-ink-2">
                    {w}
                  </Text>
                ))}
              </View>
              {DP_ORDER.map((dp) => (
                <View key={dp} className="flex-row items-center gap-1">
                  <Text className="w-9 text-small text-ink-2">{dpKo(dp)}</Text>
                  {WD.map((w, wd) => {
                    const g = data.grid.find((x) => x.weekday === wd && x.daypart === dp);
                    const v = g?.avg ?? 0;
                    return (
                      <View key={w} accessibilityLabel={`${w}요일 ${dpKo(dp)} ${man(v)}`} className="h-[34px] flex-1 rounded-md bg-brand" style={{ opacity: 0.12 + (v / max) * 0.88 }} />
                    );
                  })}
                </View>
              ))}
            </View>
            {peak && (
              <View className="rounded-[14px] bg-brand-soft px-3.5 py-3">
                <Text className="text-small text-ink">{`${WD[peak.weekday]}요일 ${withSubject(dpKo(peak.daypart))} 제일 바빠요\n${WD[(peak.weekday + 6) % 7]}요일에 재료를 넉넉히 준비해요`}</Text>
              </View>
            )}
          </Card>
        </>
      )}
    </SalesPage>
  );
}

// ---------- 06-74 어디서, 누가 ----------
const CH_STYLE: Record<string, { color: string; opacity: number }> = {
  BAEMIN: { color: C.brand, opacity: 1 },
  COUPANG: { color: C.brand, opacity: 0.6 },
  YOGIYO: { color: C.brand, opacity: 0.35 },
  NAVER: { color: C.done, opacity: 1 },
  HALL: { color: C.calm, opacity: 1 },
};
const CH_LABEL: Record<string, string> = { HALL: "가게에서 드신 손님" };

export function SalesChannelScreen() {
  const [period, setPeriod] = useState<SalesPeriod>("week");
  const { data, error, refetch } = useSales(`channels-${period}`, (n) => salesApi.channels(n, period));
  const total = data?.channels.reduce((a, c) => a + c.amount, 0) ?? 0;
  const delivery = data ? data.channels.filter((c) => c.key !== "HALL").reduce((a, c) => a + c.amount, 0) : 0;
  const c = data?.customers;
  const known = c ? c.regular.amount + c.fresh.amount + c.other.amount : 0;
  // 답글 단 손님이 다시 주문한 결과 (06-74 아래 초록 띠). 서버에 생기기 전까지 결과 알림 목업을 쓴다.
  const replied = USE_MOCK ? RESULT_NOTICES.find((n) => n.kind === "REPLY_RESULT")?.data : undefined;
  return (
    <SalesPage title="어디서, 누가 샀나" back>
      <Chips
        value={period}
        onChange={setPeriod}
        options={[
          ["week", "이번 주"],
          ["4w", "지난 4주"],
          ["month", "이번 달"],
        ]}
      />
      {error ? (
        <Problem id="channels" error={error} onRetry={() => refetch()} />
      ) : !data || !c ? (
        <Loading h={560} />
      ) : (
        <>
          <Card label="어디서 팔렸나">
            <Text className="text-title text-ink">{`배달이 ${total ? Math.round((delivery / total) * 100) : 0}%예요`}</Text>
            <Stacked parts={data.channels.map((x) => ({ key: x.key, value: x.amount, ...(CH_STYLE[x.key] ?? { color: C["ink-3"], opacity: 1 }) }))} />
            <View>
              {data.channels.map((x) => (
                <View key={x.key} className="flex-row items-center gap-2.5 py-2.5">
                  <Dot color={CH_STYLE[x.key]?.color ?? C["ink-3"]} opacity={CH_STYLE[x.key]?.opacity} />
                  <Text className="flex-1 text-body text-ink">{CH_LABEL[x.key] ?? x.label}</Text>
                  <Text className="text-body font-bold text-ink">{man(x.amount)}</Text>
                  <Text className="w-11 text-right text-label text-ink-2">{total ? Math.round((x.amount / total) * 100) : 0}%</Text>
                </View>
              ))}
            </View>
          </Card>
          <Card label="누가 샀나">
            <Text className="text-title text-ink">{`단골 손님이 ${known ? Math.round((c.regular.amount / known) * 100) : 0}%예요`}</Text>
            <Stacked
              parts={[
                { key: "regular", value: c.regular.amount, color: C.brand },
                { key: "rest", value: c.fresh.amount + c.other.amount, color: C.line },
              ]}
            />
            <View className="flex-row gap-2.5">
              <Stat label="다시 온 단골" value={`${c.regular.people}명`} />
              <Stat label="처음 온 손님" value={`${c.fresh.people}명`} />
            </View>
            {replied && (
              <View className="rounded-[14px] bg-done-soft px-3.5 py-3">
                <Text className="text-small text-ink">{`지난주 토요일 답글 단 손님 ${replied.before}분 중\n${replied.after}분이 다시 주문했어요`}</Text>
              </View>
            )}
          </Card>
        </>
      )}
    </SalesPage>
  );
}

// ---------- 06-75 달별 ----------
export function SalesMonthScreen() {
  const { data, error, refetch } = useSales("months", (n) => salesApi.months(n));
  const list = data?.months ?? [];
  const cur = list.at(-1);
  const prev = list.at(-2);
  const max = Math.max(...list.map((m) => m.forecast ?? m.amount), 1);
  const H = 110;
  const recent = list.slice(-3);
  return (
    <SalesPage title="달별 매출" back>
      {error ? (
        <Problem id="months" error={error} onRetry={() => refetch()} />
      ) : !data || !cur ? (
        <Loading h={520} />
      ) : (
        <>
          <Card label="이번 달">
            <Text className="text-body font-medium text-ink-2">{`${mLabel(cur.month)} 예상`}</Text>
            <Text className="text-display text-ink" style={{ fontSize: 30, lineHeight: 40 }}>
              {man(cur.forecast ?? cur.amount)}
            </Text>
            {prev && (
              <Change diff={pct(cur.forecast ?? cur.amount, prev.amount)} text={cmp(pct(cur.forecast ?? cur.amount, prev.amount), `${mLabel(prev.month)}보다`, true)} />
            )}
            <View className="flex-row items-end gap-1.5" style={{ height: H }} accessibilityRole="image" accessibilityLabel="달별 매출 막대">
              {list.map((m, i) => {
                const isCur = i === list.length - 1;
                const dark = i >= list.length - 3;
                return isCur && m.forecast ? (
                  <View key={m.month} className="flex-1 rounded-t border border-dashed border-brand bg-brand-soft" style={{ height: Math.max(4, (m.forecast / max) * H) }} />
                ) : (
                  <View key={m.month} className="flex-1 rounded-t" style={{ height: Math.max(4, (m.amount / max) * H), backgroundColor: dark ? C.brand : C.line }} />
                );
              })}
            </View>
            <View className="flex-row gap-1.5">
              {list.map((m, i) => (
                <Text key={m.month} className="flex-1 text-center text-small text-ink-3">
                  {(list.length - 1 - i) % 3 === 0 ? Number(m.month.slice(5)) : ""}
                </Text>
              ))}
            </View>
            <Small>{"점선은 이번 달 예상이에요\n최근 석 달은 진하게 칠했어요"}</Small>
          </Card>
          <View className="flex-row gap-2">
            <Stat plain label="하루 평균" value={man(data.avgDaily)} />
            <Stat plain label="주문" value={`${cur.orders.toLocaleString("ko-KR")}건`} />
            <Stat plain label="주문 1번 평균" value={manShort(data.avgOrder)} />
          </View>
          <Card label="지난 석 달">
            <Text className="text-title text-ink">지난 석 달</Text>
            <View>
              {recent.map((m) => {
                const i = list.indexOf(m);
                const before = list[i - 1];
                const v = m.forecast ?? m.amount;
                return (
                  <View key={m.month} className="min-h-14 flex-row items-center gap-2.5 border-b border-line py-2.5">
                    <Text className="flex-1 text-body text-ink">{mLabel(m.month)}</Text>
                    <Small>{`${m.orders.toLocaleString("ko-KR")}건`}</Small>
                    <Text className="text-body font-bold text-ink">{man(v)}</Text>
                    {before && !before.partial ? <DiffPill diff={pct(v, before.amount)} prefix={m.forecast ? "예상 " : ""} /> : <View className="w-12" />}
                  </View>
                );
              })}
            </View>
          </Card>
        </>
      )}
    </SalesPage>
  );
}
