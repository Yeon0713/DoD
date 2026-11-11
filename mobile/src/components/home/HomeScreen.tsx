// 홈 (Figma 07-1 할 일이 남았을 때, 07-2 다 끝냈을 때). 앱을 열면 먼저 보는 화면이다.
// 위에서부터: 날짜와 남은 일 수 → 지금 할 일 1장 → 다음 할 일 → 오늘 끝낸 일.
// 바탕은 home 색으로, 다른 화면(paper)과 구분한다.
import { useFocusEffect } from "expo-router";
import { useCallback, useState, type ReactNode } from "react";
import { Pressable, RefreshControl, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon, type IconName } from "@/components/icons/Icon";
import { TabPage } from "@/components/ui/TabPage";
import { DonnaImage, PrimaryButton, ProgressSteps, StatusPill } from "@/components/ui/parts";
import { go } from "@/components/ui/nav";
import { ApiFailure } from "@/lib/api";
import { isOpen, type CardStatus } from "@/lib/cardState";
import type { CardView } from "@/lib/cards";
import { devFlags } from "@/lib/dev";
import { slotLabel } from "@/lib/hours";
import { nextSlot } from "@/lib/queue";
import { addDays, dateOnly, hhmm, monthDay, relativeDay, weekdayName, ymd } from "@/lib/time";
import { useHome, useTodayCards } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";
import type { Slot, StoreSettings } from "@/types/contract";
import { Checking, Loading, NEXT_ICON, NotifyOffBanner, Offline, useWaitStage } from "@/components/task/states";

const C = tokens.colors;

const taskHref = (id: string) => `/task?id=${encodeURIComponent(id)}`;
const oneLine = (s: string) => s.replace(/\n/g, " ");
/** 모아 보기 줄에 적는 요일. 다음 주 알림(결과 알림)은 "다음 주 월요일" */
function dayOf(slot: string, now: Date) {
  const monday = addDays(ymd(now), -((dateOnly(ymd(now)).getUTCDay() + 6) % 7));
  return `${slot.slice(0, 10) >= addDays(monday, 7) ? "다음 주 " : ""}${weekdayName(slot)}`;
}
/** 끝낸 때. 오늘이 아니면 요일을 붙인다 (모아 보기에서는 다른 요일 카드도 끝낸다) */
const doneWhen = (at: string, now: Date) => `${ymd(new Date(at)) === ymd(now) ? "" : `${weekdayName(at)} `}${hhmm(at)}에 `;

function Header({ now, title, total, done, checking }: { now: Date; title: string; total: number; done: number; checking?: boolean }) {
  return (
    <View className="gap-1.5">
      <View className="h-7 flex-row items-center justify-between">
        <Text className="text-label text-ink-2">{`${monthDay(now)} ${weekdayName(now)}`}</Text>
        {checking ? <Checking /> : null}
      </View>
      <Text testID="home-title" className="text-display text-ink" accessibilityRole="header">
        {title}
      </Text>
      <View className="mt-1.5">
        <ProgressSteps total={Math.max(total, 1)} done={done} />
      </View>
    </View>
  );
}

function Group({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <View className="gap-2.5">
      <View className="flex-row items-center gap-1.5">
        <Text className="text-body font-bold text-ink" accessibilityRole="header">
          {title}
        </Text>
        {count != null ? <Text className="text-body font-bold text-ink-3">{count}</Text> : null}
      </View>
      {children}
    </View>
  );
}

/** 07-1: 지금 할 일 카드 한 장. 자세한 내용과 처리는 07-3에서 한다. */
function NowCard({ card }: { card: CardView }) {
  const line = card.draft ? "도나가 답글을 써 뒀어요" : (card.sub ?? oneLine(card.donna.text));
  return (
    <View testID="home-now" className={`gap-3 rounded-card bg-surface p-[22px] ${card.urgent ? "border-2 border-urgent" : "border border-line"}`}>
      {card.pill ? (
        <View className="flex-row">
          <StatusPill tone={card.tone} icon={card.pill.icon} solid={card.urgent}>
            {card.pill.text}
          </StatusPill>
        </View>
      ) : null}
      <View className="flex-row items-center gap-2">
        {card.titleIcon ? <Icon name={card.titleIcon} size={28} color={C.brand} /> : null}
        <Text className="flex-1 text-title text-ink">{card.title}</Text>
      </View>
      <Text className="text-label text-ink-2">{line}</Text>
      <PrimaryButton testID="home-start" href={taskHref(card.id)}>
        지금 하기
      </PrimaryButton>
    </View>
  );
}

/** 07-2: 다 끝냈을 때(또는 지금은 할 일이 없을 때) 지금 할 일 자리 */
function RestBox({ title, settings, now }: { title: string; settings: StoreSettings; now: Date }) {
  const next = nextSlot(settings.slots, now);
  return (
    <View testID="home-rest" className="items-center gap-2 rounded-card bg-surface px-[22px] pb-[22px] pt-5">
      <DonnaImage img="b4-2" size={120} />
      <Text className="text-center text-title text-ink">{title}</Text>
      <View className="flex-row items-center gap-2">
        <Icon name={NEXT_ICON[next.slot as Slot]} size={24} color={C["ink-2"]} />
        <Text className="text-body text-ink-2">
          다음 알림은 {next.tomorrow ? "내일 " : ""}
          {slotLabel(settings, next.slot as Slot)} {next.time}
        </Text>
      </View>
    </View>
  );
}

type Row = { id: string; title: string; sub: string; icon: IconName; done?: boolean; href: string };

/** 07-1, 07-2: 다음 할 일, 오늘 끝낸 일 목록 */
function List({ rows, testID }: { rows: Row[]; testID: string }) {
  return (
    <View testID={testID} className="overflow-hidden rounded-card border border-line bg-surface">
      {rows.map((r, i) => (
        <Pressable
          key={r.id}
          testID={`${testID}-${i}`}
          accessibilityRole="button"
          accessibilityLabel={`${r.title}. ${r.sub}`}
          onPress={() => go(r.href)}
          className={`min-h-[72px] flex-row items-center gap-3 py-3.5 pl-4 pr-3 active:bg-brand-soft ${i > 0 ? "border-t border-line" : ""}`}
        >
          <View className={`h-10 w-10 items-center justify-center rounded-full ${r.done ? "bg-done-soft" : "bg-brand-soft"}`}>
            <Icon name={r.icon} size={22} color={r.done ? C.done : C.brand} />
          </View>
          <View className="flex-1 gap-0.5">
            <Text className="text-body text-ink" numberOfLines={2}>
              {r.title}
            </Text>
            <Text className={`text-small ${r.done ? "text-done" : "text-ink-2"}`}>{r.sub}</Text>
          </View>
          <Icon name="chevR" size={20} color={C["ink-3"]} />
        </Pressable>
      ))}
    </View>
  );
}

function HomeBody() {
  const { data, view, store, error, isPending, isFetching, refetch, now, prefs: p, allWeek } = useTodayCards();
  const stage = useWaitStage(isPending);

  if (!data || !view) {
    const header = <Header now={now} title={"오늘 할 일을\n모으고 있어요"} total={1} done={0} />;
    if (error instanceof ApiFailure && error.offline) return <Offline header={header} onRetry={() => refetch()} />;
    return <Loading header={header} stage={error ? 3 : stage} onRetry={() => refetch()} />;
  }

  const settings = data.settings.settings;
  const statusOf = (c: CardView): CardStatus | undefined => store[c.id];

  // 나중에로 미룬 일: 아직 다시 알릴 때가 안 됐다.
  const later = view.cards.filter((c) => statusOf(c)?.kind === "snoozed" && !isOpen(store, c.id, now));
  // 오늘 끝낸 일: 늦게 끝낸 일이 위로
  const doneCards = view.cards
    .filter((c) => statusOf(c)?.kind === "done")
    .map((c) => ({ c, s: statusOf(c) as Extract<CardStatus, { kind: "done" }> }))
    .sort((a, b) => (b.s.at ?? "").localeCompare(a.s.at ?? ""));
  const [first, ...rest] = view.open;
  const remaining = view.open.length + later.length;
  const total = Math.max(view.total, doneCards.length + remaining);

  const title = remaining > 0 ? `오늘 할 일이\n${remaining}개 남았어요` : doneCards.length > 0 ? `오늘 할 일 ${doneCards.length}개를\n다 끝냈어요` : "오늘 할 일을\n다 끝냈어요";

  const nextRows: Row[] = [
    ...rest.map((c) => {
      // 모아 보기에서는 언제 온 카드인지 같이 적는다 (Figma 06 화면 이름의 "목 오전" 같은 때)
      const slot = view.slotOf[c.id];
      const when = allWeek && slot ? `${dayOf(slot, now)} ${hhmm(slot)} 알림` : null;
      const sub = [c.pill?.text, when].filter(Boolean).join(", ") || "할 일";
      return { id: c.id, title: oneLine(c.title), sub, icon: c.pill?.icon ?? "bell", href: taskHref(c.id) };
    }),
    ...later.map((c) => {
      const s = statusOf(c) as Extract<CardStatus, { kind: "snoozed" }>;
      const day = relativeDay(s.until, now);
      return { id: c.id, title: oneLine(c.title), sub: `${day === "오늘" ? "" : `${day} `}${hhmm(s.until)}에 다시 알려 드려요`, icon: c.pill?.icon ?? "clock", href: taskHref(c.id) };
    }),
  ];
  const doneRows: Row[] = doneCards.map(({ c, s }) => ({
    id: c.id,
    title: oneLine(c.title),
    sub: `${s.at ? doneWhen(s.at, now) : ""}${s.note ?? "끝냈어요"}`,
    icon: "check",
    done: true,
    href: `/done/${encodeURIComponent(c.id)}`,
  }));

  return (
    <View className="gap-6">
      <View>
        {p.notifyOff ? <NotifyOffBanner /> : null}
        <Header now={now} title={title} total={total} done={doneCards.length} checking={isFetching} />
        {allWeek ? (
          <Text testID="home-all-week" className="mt-2 text-small text-ink-3">
            검토용 목업: 데모 한 주(11월 16일~25일) 할 일을 모두 모아 보여 줘요
          </Text>
        ) : null}
      </View>
      {first ? (
        <Group title="지금 할 일">
          <NowCard card={first} />
        </Group>
      ) : (
        <RestBox title={remaining > 0 ? "지금은 할 일이 없어요" : "수고하셨어요"} settings={settings} now={now} />
      )}
      {nextRows.length > 0 ? (
        <Group title="다음 할 일" count={nextRows.length}>
          <List testID="home-next" rows={nextRows} />
        </Group>
      ) : null}
      {doneRows.length > 0 ? (
        <Group title="오늘 끝낸 일" count={doneRows.length}>
          <List testID="home-done" rows={doneRows} />
        </Group>
      ) : null}
    </View>
  );
}

export function HomeScreen() {
  const { refetch } = useHome();
  // 모아 보기에서 연 카드의 시각(scene)은 홈으로 돌아오면 비운다. 홈은 늘 가상 시각 기준이다.
  useFocusEffect(
    useCallback(() => {
      if (devFlags.read().scene) devFlags.write({ scene: null });
    }, []),
  );
  const [pulling, setPulling] = useState(false);
  // 아래로 당기면 새 할 일을 다시 받는다.
  const onRefresh = async () => {
    setPulling(true);
    try {
      await refetch();
    } finally {
      setPulling(false);
    }
  };
  return (
    <TabPage bg={C.home} refresh={<RefreshControl refreshing={pulling} onRefresh={onRefresh} tintColor={C.brand} colors={[C.brand]} />}>
      <HomeBody />
    </TabPage>
  );
}
