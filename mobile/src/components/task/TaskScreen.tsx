// 지금 할 일 (Figma 07-3, 카드 모양은 06-4 외 카드 전부, 06-22 나중에 시트).
// 홈에서 "지금 하기"나 다음 할 일 한 줄을 누르면 열린다. 카드 한 장만 보고 처리한 뒤 홈으로 돌아간다.
import { useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Text } from "@/components/ui/Text";
import { Icon, type IconName } from "@/components/icons/Icon";
import { Sheet, useSheetClose } from "@/components/ui/Sheet";
import { DonnaSays, PrimaryButton, ProgressSteps, SecondaryButton } from "@/components/ui/parts";
import { DraftBubble } from "@/components/ui/sub";
import { back, go } from "@/components/ui/nav";
import { publishReply } from "@/lib/actions";
import { ApiFailure } from "@/lib/api";
import { markDone, snooze, markPlanDone } from "@/lib/cardState";
import type { CardAction, CardView } from "@/lib/cards";
import { devFlags } from "@/lib/dev";
import { slotLabel } from "@/lib/hours";
import { drafts, flashToast, prefs } from "@/lib/localStore";
import { addDays, ymd } from "@/lib/time";
import { useTodayCards } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";
import type { Slot, StoreSettings } from "@/types/contract";
import { Checking, Loading, NEXT_ICON, NotifyOffBanner, Offline, Scroll, useWaitStage } from "./states";
import { TaskCard } from "./TaskCard";

const C = tokens.colors;

/** 07-3 위: 뒤로 + "지금 할 일" + 오늘 진행 막대 */
function Header({ total, done, checking }: { total: number; done: number; checking?: boolean }) {
  return (
    <View className="gap-3 pb-5">
      <View className="h-11 flex-row items-center gap-2">
        <Pressable
          testID="back"
          accessibilityRole="button"
          accessibilityLabel="홈으로"
          onPress={() => back("/")}
          className="-ml-2.5 h-11 w-11 items-center justify-center rounded-full active:bg-brand-soft"
        >
          <Icon name="chevL" size={26} />
        </Pressable>
        <Text className="flex-1 text-title text-ink" accessibilityRole="header">
          지금 할 일
        </Text>
        {checking ? <Checking /> : null}
      </View>
      <ProgressSteps total={total} done={done} />
    </View>
  );
}

/** "나중에 할게요" 시트 (06-22). 고를 수 있는 때는 지금 다음의 알림 시각 3개다. */
function LaterSheet({ open, onClose, onDismiss, onPick, settings, now }: { open: boolean; onClose: () => void; onDismiss: () => void; onPick: (iso: string) => void; settings: StoreSettings; now: Date }) {
  const slots = settings.slots;
  const choices = useMemo(() => {
    const today = ymd(now);
    const out: { label: string; time: string; iso: string; icon: IconName }[] = [];
    for (const day of [today, addDays(today, 1)]) {
      for (const slot of ["OPENING", "AFTERNOON", "CLOSING"] as Slot[]) {
        const iso = `${day}T${slots[slot]}:00+09:00`;
        if (new Date(iso).getTime() <= now.getTime()) continue;
        out.push({ label: `${day === today ? "오늘" : "내일"} ${slotLabel(settings, slot)}`, time: slots[slot], iso, icon: NEXT_ICON[slot] });
      }
    }
    return out.slice(0, 3);
  }, [slots, settings, now]);
  const [picked, setPicked] = useState(0);
  return (
    <Sheet open={open} onClose={onClose} onDismiss={onDismiss} title={"언제 다시\n알려 드릴까요?"}>
      <View className="gap-2.5" accessibilityRole="radiogroup" accessibilityLabel="다시 알려 드릴 때">
        {choices.map((c, i) => (
          <Pressable
            key={c.iso}
            testID={`later-${i}`}
            accessibilityRole="radio"
            accessibilityState={{ checked: picked === i }}
            onPress={() => setPicked(i)}
            className={`h-14 flex-row items-center gap-3 rounded-button border px-4 ${picked === i ? "border-brand bg-brand-soft" : "border-line bg-surface"}`}
          >
            <Icon name={c.icon} size={24} color={C["ink-2"]} />
            <Text className={`flex-1 text-body text-ink ${picked === i ? "font-medium" : ""}`}>{c.label}</Text>
            <Text className="text-body text-ink-2">{c.time}</Text>
          </Pressable>
        ))}
      </View>
      <View className="mt-5">
        <PrimaryButton testID="later-confirm" onPress={() => choices[picked] && onPick(choices[picked].iso)}>
          이때 알려 주세요
        </PrimaryButton>
      </View>
    </Sheet>
  );
}

/** 05-4, 06-4: 카드 아래 도나가 써 둔 답글. 누르기 전엔 올라가지 않는다. */
function DraftRow({ draft }: { draft: NonNullable<CardView["draft"]> }) {
  return (
    <View>
      <DraftBubble img={draft.img} text={draft.text} />
      <View className="mt-1 flex-row items-center gap-2">
        <Icon name="shield" size={18} color={C.done} />
        <Text className="flex-1 text-small text-ink-2">누르기 전엔 올라가지 않아요</Text>
        <Pressable testID="draft-edit" accessibilityRole="link" hitSlop={8} onPress={() => go(draft.editHref)} className="min-h-11 justify-center pl-2">
          <Text className="text-label font-bold text-brand">고쳐 쓰기</Text>
        </Pressable>
      </View>
    </View>
  );
}

function TaskBody() {
  const { data, view, store, error, isPending, isFetching, refetch, now, prefs: p, scope } = useTodayCards();
  const stage = useWaitStage(isPending);
  const [laterFor, setLaterFor] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const laterClose = useSheetClose();
  // id: 홈에서 누른 카드. 없으면 맨 앞 카드. 검토용: /task?sheet=later 로 열면 "나중에" 시트(06-22)를 연 채로 보여 준다.
  const { id, sheet } = useLocalSearchParams<{ id?: string; sheet?: string }>();
  const [sheetAsked, setSheetAsked] = useState(sheet === "later");

  // 처리하는 동안 카드가 바뀌지 않게, 처음 고른 카드를 붙잡아 둔다.
  const [pinnedId, setPinnedId] = useState<string | null>(id ?? null);
  const firstId = view?.open[0]?.id;
  if (!pinnedId && firstId) setPinnedId(firstId);
  const card = view && pinnedId ? (view.open.find((c) => c.id === pinnedId) ?? view.cards.find((c) => c.id === pinnedId)) : undefined;

  // 모아 보기: 이 카드가 온 때를 지금으로 본다. 답글, 메뉴판, 포스터 화면도 그 때 기준으로 움직인다.
  const moment = scope.all && card ? view?.momentOf[card.id] : undefined;
  useEffect(() => {
    if (moment && devFlags.read().cardNow !== moment) devFlags.write({ cardNow: moment });
  }, [moment]);

  // 카드를 끝내면(여기서든 답글, 점검 화면에서든) 홈으로 돌아간다. 이 화면이 보일 때만 움직인다.
  const finished = !!card && store[card.id]?.kind === "done";
  useFocusEffect(
    useCallback(() => {
      if (finished) back("/");
    }, [finished]),
  );

  if (sheetAsked && card) {
    setSheetAsked(false);
    setLaterFor(card.id);
  }

  if (!data) {
    const header = <Header total={1} done={0} />;
    if (error instanceof ApiFailure && error.offline)
      return (
        <Scroll>
          <Offline header={header} onRetry={() => refetch()} />
        </Scroll>
      );
    return (
      <Scroll>
        <Loading header={header} stage={error ? 3 : stage} onRetry={() => refetch()} />
      </Scroll>
    );
  }

  const settings = data.settings.settings;
  if (!view || !card) {
    // 할 일이 없거나 이미 끝낸 카드 주소로 들어왔다. 홈에서 오늘 일을 보게 한다.
    return (
      <View className="flex-1">
        <Header total={Math.max(view?.total ?? 0, 1)} done={view?.done ?? 0} />
        <View className="flex-1 items-center justify-center">
          <Text className="text-center text-title text-ink">{"지금 할 일이\n없어요"}</Text>
        </View>
        <PrimaryButton onPress={() => back("/")}>홈으로</PrimaryButton>
      </View>
    );
  }

  const act = (a: CardAction): { href?: string; onPress: () => void } => {
    if ("href" in a) return { href: a.href, onPress: () => a.done && markDone(card.id, { note: "확인했어요" }) };
    if (a.action === "snooze") return { onPress: () => setLaterFor(card.id) };
    const done = async () => {
      if (a.reply) {
        const r = a.reply;
        if (r.mode === "schedule") {
          // 실행 시각에 올리도록 맡긴다. 제안: POST /api/plan/{plan_id}/approve
          markDone(`APPROVAL_REQUEST:${r.planId}`, { note: "답글을 맡겼어요", reply: r.text });
          flashToast("답글을 맡겼어요", `${r.when}에 올릴게요`);
          return;
        }
        setSending(true);
        try {
          await publishReply(r.planId, r.text);
        } catch {
          flashToast("답글을 못 올렸어요", "인터넷이 끊겼어요. 다시 눌러 주세요");
          return;
        } finally {
          setSending(false);
        }
        const sent = { note: "답글을 올렸어요", reply: r.text };
        markPlanDone(r.planId, sent);
        flashToast("답글을 올렸어요", `${r.platform}에서 볼 수 있어요`);
        return;
      }
      if (a.publish) {
        setSending(true);
        try {
          const saved = drafts.read();
          for (const pid of a.publish) await publishReply(pid, saved[pid]);
        } catch {
          flashToast("답글을 못 올렸어요", "인터넷이 끊겼어요. 다시 눌러 주세요");
          return;
        } finally {
          setSending(false);
        }
        for (const pid of a.publish) markDone(`EXECUTE_REMINDER:${pid}`, { note: "답글을 올렸어요" });
      }
      if (a.declineNaver) prefs.write({ naverDeclined: true });
      if (a.toast) flashToast(a.toast.title, a.toast.sub);
      if (card.id === "FIRST_DAY") {
        // 첫날 카드는 카드 상태가 아니라 처음 설정 값으로 끝난다. 그래서 직접 홈으로 돌아간다.
        prefs.write({ firstDayPending: false });
        back("/");
      } else markDone(card.id, { note: a.publish ? "답글을 올렸어요" : a.toast?.title });
    };
    return { onPress: () => void done() };
  };

  return (
    <>
      {/* 카드와 도나 한마디만 스크롤한다. 버튼은 화면이 낮거나 글씨가 커도 늘 보이게 아래에 고정한다. */}
      <Scroll>
        {p.notifyOff ? <NotifyOffBanner /> : null}
        <Header total={view.total} done={view.done + 1} checking={isFetching} />
        <View accessibilityLiveRegion="polite">
          <TaskCard key={card.id} card={card} />
          <View className="h-5" />
          {card.draft ? (
            <DraftRow draft={card.draft} />
          ) : (
            <View className="gap-1">
              {card.aboveDonna ? <Text className="text-small text-brand">{card.aboveDonna}</Text> : null}
              <DonnaSays img={card.donna.img} size={card.aboveDonna ? 56 : 72}>
                {card.donna.text}
              </DonnaSays>
            </View>
          )}
          <View className="h-3" />
        </View>
      </Scroll>
      <View className="gap-1 pt-3">
        <PrimaryButton {...act(card.primary)} disabled={sending || finished}>
          {sending ? "올리는 중" : card.primary.label}
        </PrimaryButton>
        {card.secondary ? (
          <SecondaryButton {...act(card.secondary)} disabled={sending || finished}>
            {card.secondary.label}
          </SecondaryButton>
        ) : null}
      </View>
      <LaterSheet
        open={laterFor !== null}
        onClose={() => setLaterFor(null)}
        onDismiss={laterClose.onDismiss}
        settings={settings}
        now={now}
        onPick={async (iso) => {
          const id = laterFor;
          // 시트가 다 닫힌 뒤에 미루고 홈으로 간다. 열린 시트째 화면을 빼면 iOS에서 앱이 멈춘다.
          setLaterFor(null);
          await laterClose.closed();
          if (id) snooze(id, iso);
          flashToast("다시 알려 드릴게요", `${iso.slice(0, 10) === ymd(now) ? "오늘" : "내일"} ${iso.slice(11, 16)}에 알려 드려요`);
          back("/");
        }}
      />
    </>
  );
}

export function TaskScreen() {
  return (
    <SafeAreaView edges={["top", "bottom"]} style={{ flex: 1, backgroundColor: C.paper }}>
      <View className="flex-1 px-6 pb-5 pt-3">
        <TaskBody />
      </View>
    </SafeAreaView>
  );
}
