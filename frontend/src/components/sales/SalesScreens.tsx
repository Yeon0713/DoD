"use client";
// 매출 (Figma 05-70 첫 화면, 05-71 이번 주와 지난주, 05-72 메뉴별, 05-73 시간대와 요일, 05-74 어디서 누가, 05-75 달별).
// 첫 화면은 사장님이 가장 자주 보는 두 가지(오늘 실시간, 이번 주와 지난주)만 크게 보여 주고, 나머지는 눌러서 들어간다.
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/icons/Icon";
import { BottomTabs } from "@/components/ui/BottomTabs";
import { Bone, PrimaryButton } from "@/components/ui/parts";
import { ToastHost } from "@/components/ui/sub";
import { ApiFailure, salesApi } from "@/lib/api";
import { withSubject } from "@/lib/labels";
import { currentNow, monthDay, weekdayName } from "@/lib/time";
import { useMounted } from "@/lib/useHome";
import type { SalesPeriod } from "@/types/sales";

// ---------- 숫자 ----------
const won = (n: number) => `${Math.round(n).toLocaleString("ko-KR")}원`;
/** 1,249만 원 */
const man = (n: number) => `${Math.round(n / 1e4).toLocaleString("ko-KR")}만 원`;
const pct = (a: number, b: number) => (b ? Math.round(((a - b) / b) * 100) : 0);
const DP_ORDER = ["LUNCH", "DINNER", "NIGHT"] as const;
const WD = ["월", "화", "수", "목", "금", "토", "일"];

function Compare({ diff, unit, future }: { diff: number; unit: string; future?: boolean }) {
  const up = diff > 0;
  const same = Math.abs(diff) < 1;
  return (
    <p className={`flex items-center gap-1.5 text-body font-medium ${same ? "text-ink-2" : up ? "text-done" : "text-urgent"}`}>
      {!same && <Icon name={up ? "arrowUp" : "arrowDown"} size={20} />}
      {same
        ? `${unit} 비슷${future ? "할 것 같아요" : "해요"}`
        : `${unit} ${Math.abs(diff)}% ${up ? (future ? "많을 것 같아요" : "많아요") : future ? "적을 것 같아요" : "적어요"}`}
    </p>
  );
}

function DiffPill({ diff }: { diff: number }) {
  const up = diff >= 0;
  return <span className={`shrink-0 rounded-full px-2.5 py-1 text-label ${up ? "bg-done-soft text-done" : "bg-urgent-soft text-urgent"}`}>{`${up ? "+" : ""}${diff}%`}</span>;
}

function Card({ children, className = "", label }: { children: ReactNode; className?: string; label?: string }) {
  return (
    <section aria-label={label} className={`flex flex-col gap-3 rounded-[20px] border border-line bg-surface p-5 ${className}`}>
      {children}
    </section>
  );
}

function Stat({ label, value, plain, compact }: { label: string; value: string; plain?: boolean; compact?: boolean }) {
  return (
    <div className={`flex flex-1 flex-col gap-0.5 rounded-[14px] px-3.5 py-2.5 ${plain ? "border border-line bg-surface" : "bg-paper"}`}>
      <span className="text-small text-ink-2">{label}</span>
      <span className={`${compact ? "text-body font-bold" : "text-title"} whitespace-nowrap text-ink`}>{value}</span>
    </div>
  );
}

function Chips<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="flex gap-2" role="radiogroup" aria-label="기간">
      {options.map(([k, label]) => (
        <button
          key={k}
          type="button"
          role="radio"
          aria-checked={value === k}
          onClick={() => onChange(k)}
          className={`h-10 rounded-full border px-4 text-label ${value === k ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface text-ink-2"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Stacked({ parts }: { parts: { label: string; value: number; cls: string }[] }) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  return (
    <div className="flex h-4 gap-0.5 overflow-hidden rounded-md" aria-hidden>
      {parts.map((p) => (
        <span key={p.label} className={p.cls} style={{ width: `${(p.value / total) * 100}%` }} />
      ))}
    </div>
  );
}

// ---------- 화면 틀 ----------
function SalesPage({ title, back, children }: { title: string; back?: boolean; children: ReactNode }) {
  const router = useRouter();
  return (
    <>
      <ToastHost />
      <main className="flex flex-1 flex-col gap-4 px-6 pt-[max(12px,env(safe-area-inset-top))] pb-6">
        {back && (
          <div className="flex h-11 items-center">
            <button type="button" aria-label="뒤로" onClick={() => router.back()} className="-ml-2.5 flex h-11 w-11 items-center justify-center rounded-full text-ink active:bg-brand-soft">
              <Icon name="chevL" size={26} />
            </button>
          </div>
        )}
        <h1 className={`text-display ${back ? "" : "pt-2"}`}>{title}</h1>
        {children}
      </main>
      <BottomTabs />
    </>
  );
}

function useNow() {
  const mounted = useMounted();
  return mounted ? currentNow() : null;
}

/** 매출 응답 불러오기. 오늘 실시간은 1분마다 새로 받는다. */
function useSales<T>(key: string, fn: (now: Date) => Promise<T>, live = false) {
  const now = useNow();
  const q = useQuery({
    queryKey: ["sales", key, now?.toISOString().slice(0, 16)],
    queryFn: () => fn(now!),
    enabled: !!now,
    refetchInterval: live ? 60_000 : false,
    retry: 0,
  });
  return { ...q, now };
}

function Problem({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const offline = error instanceof ApiFailure && error.offline;
  return (
    <Card label="불러오지 못했어요">
      <span className="flex items-center gap-2 text-urgent">
        <Icon name="wifiOff" size={24} />
        <span className="text-body font-medium">{offline ? "인터넷이 잠시 끊겼어요" : "매출을 불러오지 못했어요"}</span>
      </span>
      <p className="text-small text-ink-2">연결되면 다시 보여 드릴게요</p>
      <PrimaryButton onClick={onRetry}>다시 불러오기</PrimaryButton>
    </Card>
  );
}

const Loading = ({ h = "h-48" }: { h?: string }) => <Bone className={`${h} w-full rounded-[20px]`} />;

// ---------- 05-70 첫 화면 ----------
function TodayCard() {
  const { data, error, refetch, now } = useSales("live", (n) => salesApi.live(n), true);
  if (error) return <Problem error={error} onRetry={() => refetch()} />;
  if (!data || !now) return <Loading h="h-[430px]" />;
  const wd = weekdayName(data.date);
  const max = Math.max(...data.hourly.map((h) => Math.max(h.amount, h.usual)), 1);
  const past = data.hourly.filter((h) => h.state !== "future");
  const best = [...past].sort((a, b) => b.amount - a.amount)[0];
  const share = data.usualDay ? Math.min(100, Math.round((data.amount / data.usualDay) * 100)) : 0;
  const hhmm = `${String(new Date(now.getTime() + 9 * 3600e3).getUTCHours()).padStart(2, "0")}:${String(now.getUTCMinutes()).padStart(2, "0")}`;
  return (
    <Card label="오늘 매출">
      <div className="flex items-center">
        <span className="flex-1 text-body font-medium text-ink-2">오늘 매출</span>
        <span className="flex items-center gap-1.5 rounded-full bg-done-soft px-2.5 py-1 text-label text-done">
          <span className="h-2 w-2 rounded-full bg-done" aria-hidden />
          지금 {hhmm}
        </span>
      </div>
      <p className="text-[36px] leading-[46px] font-bold tabular-nums text-ink">{won(data.amount)}</p>
      <Compare diff={pct(data.amount, data.yesterdaySame)} unit="어제 이 시간보다" />
      <div className="flex flex-col gap-1.5">
        <span className="text-small text-ink-2">{`평소 ${wd} 하루 ${man(data.usualDay)} 중 ${share}%`}</span>
        <div className="h-2.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={share} aria-valuemin={0} aria-valuemax={100} aria-label="평소 하루와 비교">
          <div className="h-full rounded-full bg-brand" style={{ width: `${share}%` }} />
        </div>
      </div>
      <div className="flex gap-2.5">
        <Stat label="주문" value={`${data.orders}건`} />
        <Stat label="주문 1번 평균" value={won(data.avg)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <span className="text-small text-ink-2">시간별</span>
        <div className="flex h-[76px] items-end gap-1" role="img" aria-label={`시간별 매출. 지금까지 ${best ? `${best.hour}시` : ""}가 제일 많았어요`}>
          {data.hourly.map((h) => {
            const v = h.state === "future" ? h.usual : h.amount;
            return (
              <span
                key={h.hour}
                className={`flex-1 rounded-t ${h.state === "past" ? "bg-brand" : h.state === "now" ? "bg-brand opacity-55" : "border border-dashed border-ink-3 bg-brand-soft"}`}
                style={{ height: `${Math.max(4, (v / max) * 76)}px` }}
              />
            );
          })}
        </div>
        <div className="flex gap-1" aria-hidden>
          {data.hourly.map((h) => (
            <span key={h.hour} className="flex-1 text-center text-small text-ink-3">
              {h.hour % 2 ? h.hour : ""}
            </span>
          ))}
        </div>
        <p className="pre-line text-small text-ink-2">{`점선은 평소 ${wd}이에요${best && best.amount ? `\n지금까지 ${best.hour}시가 제일 많았어요` : ""}`}</p>
      </div>
    </Card>
  );
}

function WeekCard() {
  const { data, error, refetch } = useSales("weeks", (n) => salesApi.weeks(n));
  if (error) return <Problem error={error} onRetry={() => refetch()} />;
  if (!data) return <Loading h="h-[360px]" />;
  const max = Math.max(...data.days.map((d) => Math.max(d.amount, d.last)), 1);
  const events = data.days.filter((d) => d.state === "forecast" && d.reasons.some((r) => r === "경기" || r === "축제"));
  // 같은 일은 요일을 묶는다: "목요일 경기, 토요일과 일요일 축제"
  const groups = new Map<string, string[]>();
  for (const d of events) {
    const k = d.reasons.find((r) => r === "경기" || r === "축제")!;
    groups.set(k, [...(groups.get(k) ?? []), weekdayName(d.date)]);
  }
  const why = [...groups.entries()].map(([k, ds]) => `${ds.join("과 ")} ${k}`).join(", ");
  return (
    <Link href="/sales/week" className="block" aria-label="이번 주와 지난주 자세히 보기">
      <Card label="이번 주와 지난주">
        <div className="flex items-center">
          <span className="flex-1 text-body font-medium text-ink-2">이번 주 지금까지</span>
          <span className="flex items-center gap-0.5 text-label text-brand">
            자세히
            <Icon name="chevR" size={18} />
          </span>
        </div>
        <p className="text-[30px] leading-10 font-bold tabular-nums text-ink">{won(data.toDate)}</p>
        <Compare diff={pct(data.toDate, data.lastSamePeriod)} unit="지난주 같은 때보다" />
        <div className="flex h-[120px] items-end gap-1.5" role="img" aria-label="요일별 이번 주와 지난주 매출">
          {data.days.map((d) => (
            <span key={d.date} className="flex flex-1 items-end gap-[3px]">
              <span
                className={`flex-1 rounded-t ${d.state === "forecast" ? "border border-dashed border-brand bg-brand-soft" : d.state === "now" ? "bg-brand opacity-55" : "bg-brand"}`}
                style={{ height: `${Math.max(4, (d.amount / max) * 120)}px` }}
              />
              <span className="flex-1 rounded-t bg-line" style={{ height: `${Math.max(4, (d.last / max) * 120)}px` }} />
            </span>
          ))}
        </div>
        <div className="flex gap-1.5" aria-hidden>
          {data.days.map((d) => (
            <span key={d.date} className={`flex-1 text-center text-small ${d.state === "now" ? "font-bold text-ink" : "text-ink-3"}`}>
              {WD[(new Date(`${d.date}T12:00:00+09:00`).getUTCDay() + 6) % 7]}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-3.5 text-small text-ink-2" aria-hidden>
          <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm bg-brand" />이번 주</span>
          <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm border border-dashed border-brand bg-brand-soft" />예상</span>
          <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm bg-line" />지난주</span>
        </div>
        <div className="flex gap-2.5">
          <Stat label="지난주 합계" value={man(data.lastTotal)} />
          <Stat label="이번 주 예상" value={man(data.forecastTotal)} />
        </div>
        {why && <p className="pre-line text-small text-ink-2">{`${why}로\n더 늘 것 같아요`}</p>}
      </Card>
    </Link>
  );
}

function MoreRow({ href, icon, title, sub }: { href: string; icon: IconName; title: string; sub?: string }) {
  return (
    <Link href={href} className="flex min-h-14 items-center gap-3 border-b border-line py-3">
      <Icon name={icon} size={24} className="shrink-0 text-ink-2" />
      <span className="flex-1 text-body text-ink">{title}</span>
      {sub && <span className="text-label text-ink-2">{sub}</span>}
      <Icon name="chevR" size={20} className="text-ink-3" />
    </Link>
  );
}

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
      <section aria-label="더 알아보기" className="mt-1">
        <h2 className="text-title">더 알아보기</h2>
        <MoreRow href="/sales/menu" icon="list" title="메뉴별" sub={top ? `${withSubject(top.name)} 1등` : undefined} />
        <MoreRow href="/sales/time" icon="clock" title="시간대와 요일" sub={dpTop && dpTotal ? `${withSubject(dpTop.label)} ${Math.round((dpTop.amount / dpTotal) * 100)}%` : undefined} />
        <MoreRow href="/sales/channel" icon="truck" title="배달앱과 단골" sub={c && known ? `단골이 ${Math.round((c.regular.amount / known) * 100)}%` : undefined} />
        <MoreRow href="/sales/month" icon="trendUp" title="달별 흐름" sub={thisMonth?.forecast ? `이번 달 예상 ${man(thisMonth.forecast)}` : undefined} />
      </section>
    </SalesPage>
  );
}

// ---------- 05-71 이번 주와 지난주 ----------
export function SalesWeekScreen() {
  const { data, error, refetch, now } = useSales("weeks", (n) => salesApi.weeks(n));
  return (
    <SalesPage title="이번 주와 지난주" back>
      {error ? (
        <Problem error={error} onRetry={() => refetch()} />
      ) : !data || !now ? (
        <Loading h="h-[520px]" />
      ) : (
        <>
          <Card label="합계">
            <div className="flex gap-2.5">
              <div className="flex flex-1 flex-col">
                <span className="text-small text-ink-2">이번 주 (예상 포함)</span>
                <span className="text-title">{man(data.forecastTotal)}</span>
              </div>
              <div className="flex flex-1 flex-col">
                <span className="text-small text-ink-2">지난주</span>
                <span className="text-title text-ink-2">{man(data.lastTotal)}</span>
              </div>
            </div>
            <Compare diff={pct(data.forecastTotal, data.lastTotal)} unit="지난주보다" future />
          </Card>
          <ul aria-label="요일별">
            {data.days.map((d) => (
              <li key={d.date} className="flex items-center gap-3 border-b border-line py-3.5">
                <span className="flex w-24 shrink-0 flex-col">
                  <span className="text-body font-medium">{weekdayName(d.date)}</span>
                  <span className={`text-small ${d.state === "forecast" ? "text-brand" : "text-ink-2"}`}>
                    {d.state === "forecast" ? "예상" : d.state === "now" ? "오늘, 지금까지" : monthDay(d.date)}
                  </span>
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className={`text-title ${d.state === "forecast" ? "text-ink-2" : "text-ink"}`}>{man(d.amount)}</span>
                  <span className="text-small text-ink-2">지난주 {man(d.last)}</span>
                  {d.state === "now" && d.usual ? <span className="text-small text-ink-3">평소면 {man(d.usual)}쯤</span> : null}
                  {d.state === "forecast" && d.reasons.length > 0 && <span className="text-small text-ink-3">{d.reasons.join(", ")}</span>}
                </span>
                {d.state === "now" ? <span className="shrink-0 rounded-full bg-paper px-2.5 py-1 text-label text-ink-2">진행 중</span> : <DiffPill diff={pct(d.amount, d.last)} />}
              </li>
            ))}
          </ul>
          <p className="pre-line text-small text-ink-2">{"예상은 지난 4주 같은 요일 평균에\n이번 주 달력(행사, 경기, 날씨)을 더해 계산했어요"}</p>
        </>
      )}
    </SalesPage>
  );
}

// ---------- 05-72 메뉴별 ----------
const PERIOD_LABEL: Record<SalesPeriod, string> = { today: "오늘", week: "이번 주", "4w": "지난 4주", month: "이번 달" };
const PREV_LABEL: Record<SalesPeriod, string> = { today: "어제보다", week: "지난주보다", "4w": "그전 4주보다", month: "지난달보다" };

export function SalesMenuScreen() {
  const [period, setPeriod] = useState<SalesPeriod>("week");
  const { data, error, refetch } = useSales(`menus-${period}`, (n) => salesApi.menus(n, period));
  const top = data?.items[0];
  return (
    <SalesPage title="메뉴별 매출" back>
      <Chips value={period} onChange={setPeriod} options={[["today", "오늘"], ["week", "이번 주"], ["month", "이번 달"]]} />
      {error ? (
        <Problem error={error} onRetry={() => refetch()} />
      ) : !data ? (
        <Loading h="h-[480px]" />
      ) : !top ? (
        <p className="text-body text-ink-2">아직 팔린 메뉴가 없어요</p>
      ) : (
        <>
          <section className="flex flex-col gap-1.5 rounded-[20px] bg-brand-soft p-5" aria-label="1등 메뉴">
            <span className="text-label text-brand">{PERIOD_LABEL[period]} 1등</span>
            <span className="text-title">{`${top.name} ${top.qty}개`}</span>
            {top.prevAmount > 0 && <Compare diff={pct(top.amount, top.prevAmount)} unit={PREV_LABEL[period]} />}
          </section>
          <ol aria-label="메뉴 순위">
            {data.items.slice(0, 8).map((m, i) => (
              <li key={m.name} className="flex flex-col gap-2 border-b border-line py-3.5">
                <span className="flex items-center gap-2.5">
                  <span className={`w-5 text-title ${i === 0 ? "text-brand" : "text-ink-3"}`}>{i + 1}</span>
                  <span className="flex-1 text-body font-medium">{m.name}</span>
                  <span className="text-body font-medium">{man(m.amount)}</span>
                  {m.prevAmount > 0 && <DiffPill diff={pct(m.amount, m.prevAmount)} />}
                </span>
                <span className="flex items-center gap-2">
                  <span className="h-2 flex-1 overflow-hidden rounded-full bg-line">
                    <span className={`block h-full rounded-full ${i === 0 ? "bg-brand" : "bg-ink-2"}`} style={{ width: `${(m.amount / top.amount) * 100}%` }} />
                  </span>
                  <span className="w-10 text-right text-small text-ink-2">{m.qty}개</span>
                </span>
              </li>
            ))}
          </ol>
          <p className="text-small text-ink-2">막대는 1등 메뉴 매출과 비교한 길이예요</p>
        </>
      )}
    </SalesPage>
  );
}

// ---------- 05-73 시간대와 요일 ----------
const DP_CLS: Record<string, string> = { LUNCH: "bg-calm", DINNER: "bg-brand", NIGHT: "bg-busy" };

export function SalesTimeScreen() {
  const [period, setPeriod] = useState<SalesPeriod>("4w");
  const { data, error, refetch } = useSales(`times-${period}`, (n) => salesApi.times(n, period));
  const total = data?.dayparts.reduce((a, d) => a + d.amount, 0) ?? 0;
  const top = data && [...data.dayparts].sort((a, b) => b.amount - a.amount)[0];
  const max = data ? Math.max(...data.grid.map((g) => g.avg), 1) : 1;
  const peak = data ? [...data.grid].sort((a, b) => b.avg - a.avg)[0] : null;
  const dpKo = (k: string) => data?.dayparts.find((d) => d.key === k)?.label ?? "";
  return (
    <SalesPage title="언제 많이 팔렸나" back>
      <Chips value={period} onChange={setPeriod} options={[["week", "이번 주"], ["4w", "지난 4주"], ["month", "이번 달"]]} />
      {error ? (
        <Problem error={error} onRetry={() => refetch()} />
      ) : !data || !top ? (
        <Loading h="h-[520px]" />
      ) : (
        <>
          <Card label="시간대">
            <h2 className="text-title">{`${top.label}에 가장 많이 팔려요`}</h2>
            <Stacked parts={DP_ORDER.map((k) => ({ label: k, value: data.dayparts.find((d) => d.key === k)!.amount, cls: DP_CLS[k] }))} />
            <p className="text-small text-ink-2">{data.dayparts.map((d) => `${d.label} ${d.range}`).join(", ")}</p>
            <ul>
              {data.dayparts.map((d) => (
                <li key={d.key} className="flex items-center gap-2.5 py-2">
                  <span className={`h-3 w-3 rounded-sm ${DP_CLS[d.key]}`} aria-hidden />
                  <span className="flex-1 text-body">{d.label}</span>
                  <span className="text-body font-medium">{man(d.amount)}</span>
                  <span className="w-11 text-right text-label text-ink-2">{total ? Math.round((d.amount / total) * 100) : 0}%</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card label="요일마다 바쁜 때">
            <h2 className="text-title">요일마다 바쁜 때</h2>
            <p className="text-small text-ink-2">진할수록 많이 팔렸어요. 지난 4주 평균이에요</p>
            <div className="grid grid-cols-[36px_repeat(7,1fr)] gap-1" role="table" aria-label="요일과 시간대별 평균 매출">
              <span />
              {WD.map((w) => (
                <span key={w} className="text-center text-small text-ink-2">{w}</span>
              ))}
              {DP_ORDER.map((dp) => (
                <div key={dp} className="contents" role="row">
                  <span className="text-small text-ink-2" role="rowheader">{dpKo(dp)}</span>
                  {WD.map((w, wd) => {
                    const g = data.grid.find((x) => x.weekday === wd && x.daypart === dp)!;
                    return <span key={w} role="cell" aria-label={`${w}요일 ${dpKo(dp)} ${man(g.avg)}`} className="h-[34px] rounded-md bg-brand" style={{ opacity: 0.12 + (g.avg / max) * 0.88 }} />;
                  })}
                </div>
              ))}
            </div>
            {peak && (
              <p className="pre-line rounded-[14px] bg-brand-soft px-3.5 py-3 text-small text-ink">
                {`${WD[peak.weekday]}요일 ${withSubject(dpKo(peak.daypart))} 제일 바빠요\n${WD[(peak.weekday + 6) % 7]}요일에 재료를 넉넉히 준비해요`}
              </p>
            )}
          </Card>
        </>
      )}
    </SalesPage>
  );
}

// ---------- 05-74 어디서, 누가 ----------
const CH_CLS: Record<string, string> = { BAEMIN: "bg-brand", COUPANG: "bg-brand/70", YOGIYO: "bg-brand/45", NAVER: "bg-done", HALL: "bg-calm" };

export function SalesChannelScreen() {
  const [period, setPeriod] = useState<SalesPeriod>("week");
  const { data, error, refetch } = useSales(`channels-${period}`, (n) => salesApi.channels(n, period));
  const total = data?.channels.reduce((a, c) => a + c.amount, 0) ?? 0;
  const delivery = data ? data.channels.filter((c) => c.key !== "HALL").reduce((a, c) => a + c.amount, 0) : 0;
  const c = data?.customers;
  const known = c ? c.regular.amount + c.fresh.amount + c.other.amount : 0;
  return (
    <SalesPage title="어디서, 누가 샀나" back>
      <Chips value={period} onChange={setPeriod} options={[["today", "오늘"], ["week", "이번 주"], ["month", "이번 달"]]} />
      {error ? (
        <Problem error={error} onRetry={() => refetch()} />
      ) : !data || !c ? (
        <Loading h="h-[560px]" />
      ) : (
        <>
          <Card label="어디서 팔렸나">
            <h2 className="text-title">{`배달이 ${total ? Math.round((delivery / total) * 100) : 0}%예요`}</h2>
            <Stacked parts={data.channels.map((x) => ({ label: x.key, value: x.amount, cls: CH_CLS[x.key] }))} />
            <ul>
              {data.channels.map((x) => (
                <li key={x.key} className="flex items-center gap-2.5 py-2">
                  <span className={`h-3 w-3 rounded-sm ${CH_CLS[x.key]}`} aria-hidden />
                  <span className="flex-1 text-body">{x.label}</span>
                  <span className="text-body font-medium">{man(x.amount)}</span>
                  <span className="w-11 text-right text-label text-ink-2">{total ? Math.round((x.amount / total) * 100) : 0}%</span>
                </li>
              ))}
            </ul>
            {data.platformsSimulated && <p className="text-small text-ink-3">배달앱별 나눔은 예시예요. 배달앱을 연결하면 실제 값으로 바뀌어요</p>}
          </Card>
          <Card label="누가 샀나">
            <h2 className="text-title">{`단골 손님이 ${known ? Math.round((c.regular.amount / known) * 100) : 0}%예요`}</h2>
            <Stacked parts={[{ label: "단골", value: c.regular.amount, cls: "bg-brand" }, { label: "그 밖", value: c.fresh.amount + c.other.amount, cls: "bg-line" }]} />
            <div className="flex gap-2.5">
              <Stat label="다시 온 단골" value={`${c.regular.people}명`} />
              <Stat label="처음 온 손님" value={`${c.fresh.people}명`} />
            </div>
            <p className="pre-line text-small text-ink-2">{"배달 손님만 셌어요\n가게에서 드신 손님은 누군지 몰라서 빼고 셌어요"}</p>
          </Card>
        </>
      )}
    </SalesPage>
  );
}

// ---------- 05-75 달별 ----------
export function SalesMonthScreen() {
  const { data, error, refetch } = useSales("months", (n) => salesApi.months(n));
  const cur = data?.months.at(-1);
  const prev = data?.months.at(-2);
  const max = data ? Math.max(...data.months.map((m) => m.forecast ?? m.amount), 1) : 1;
  const mLabel = (m: string) => `${Number(m.slice(5))}월`;
  return (
    <SalesPage title="달별 매출" back>
      {error ? (
        <Problem error={error} onRetry={() => refetch()} />
      ) : !data || !cur ? (
        <Loading h="h-[520px]" />
      ) : (
        <>
          <Card label="이번 달">
            <span className="text-body font-medium text-ink-2">{`${mLabel(cur.month)} 예상`}</span>
            <p className="text-[30px] leading-10 font-bold tabular-nums">{man(cur.forecast ?? cur.amount)}</p>
            {prev && <Compare diff={pct(cur.forecast ?? cur.amount, prev.amount)} unit={`${mLabel(prev.month)}보다`} future />}
            <div className="flex h-[110px] items-end gap-3" role="img" aria-label="달별 매출 막대">
              {data.months.map((m) => (
                <span key={m.month} className="relative flex flex-1 items-end">
                  {m.forecast && <span className="absolute bottom-0 w-full rounded-t border border-dashed border-brand bg-brand-soft" style={{ height: `${(m.forecast / max) * 110}px` }} />}
                  <span className={`relative w-full rounded-t ${m.partial && !m.forecast ? "bg-line" : "bg-brand"}`} style={{ height: `${Math.max(4, (m.amount / max) * 110)}px` }} />
                </span>
              ))}
            </div>
            <div className="flex gap-3" aria-hidden>
              {data.months.map((m) => (
                <span key={m.month} className="flex-1 text-center text-small text-ink-3">{mLabel(m.month)}</span>
              ))}
            </div>
            <p className="pre-line text-small text-ink-2">{"점선은 이번 달 남은 날 예상이에요\n옅은 막대는 한 달을 다 채우지 않은 달이에요"}</p>
          </Card>
          <div className="flex gap-2">
            <Stat plain compact label="하루 평균" value={man(data.avgDaily)} />
            <Stat plain compact label="이번 달 주문" value={`${cur.orders.toLocaleString("ko-KR")}건`} />
            <Stat plain compact label="1번 평균" value={won(data.avgOrder)} />
          </div>
          <Card label="달마다">
            <h2 className="text-title">달마다</h2>
            <ul>
              {[...data.months].reverse().map((m, i, arr) => {
                const before = arr[i + 1];
                return (
                  <li key={m.month} className="flex items-center gap-2.5 border-b border-line py-2.5">
                    <span className="flex flex-1 flex-col">
                      <span className="text-body">{mLabel(m.month)}</span>
                      <span className="text-small text-ink-2">{m.partial ? `${m.days}일 장사` : `${m.orders.toLocaleString("ko-KR")}건`}</span>
                    </span>
                    <span className="text-body font-medium">{man(m.forecast ?? m.amount)}</span>
                    {m.forecast ? <span className="rounded-full bg-paper px-2.5 py-1 text-label text-ink-2">예상</span> : before && !before.partial ? <DiffPill diff={pct(m.amount, before.amount)} /> : <span className="w-12" />}
                  </li>
                );
              })}
            </ul>
          </Card>
        </>
      )}
    </SalesPage>
  );
}
