"use client";
// 오늘 화면 (Figma 04-4 외 카드 전부, 04-6, 04-8 계열, 04-9, 04-22).
// 할 일 카드는 한 번에 1장만 보여 준다. 하나를 끝내면 다음 카드가 나온다.
import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { Icon, type IconName } from "@/components/icons/Icon";
import { Bone, DonnaSays, PrimaryButton, ProgressSteps, SecondaryButton } from "@/components/ui/parts";
import { Sheet } from "@/components/ui/Sheet";
import { DraftBubble } from "@/components/ui/sub";
import { publishReply } from "@/lib/actions";
import { ApiFailure } from "@/lib/api";
import { markDone, snooze, useCardState } from "@/lib/cardState";
import type { CardView } from "@/lib/cards";
import { drafts, flashToast, prefs } from "@/lib/localStore";
import { nextSlot } from "@/lib/queue";
import { buildTodayCards } from "@/lib/todayCards";
import { addDays, currentNow, ymd } from "@/lib/time";
import { useHomeData } from "@/lib/useHomeData";
import { slotLabel } from "@/lib/hours";
import type { StoreSettings } from "@/types/contract";
import type { Slot } from "@/types/contract";
import { TaskCard } from "./TaskCard";

const subscribeNothing = () => () => {};

/** 화면이 브라우저에 붙은 뒤에만 true. 이 기기에 저장한 값을 서버 렌더와 섞지 않으려고 쓴다. */
function useMounted() {
  return useSyncExternalStore(subscribeNothing, () => true, () => false);
}

/** 불러오기 시작 후 지난 시간 단계: 0 = 0.3초 전, 1 = 뼈대, 2 = 3초 넘음, 3 = 10초 넘음 */
function useWaitStage(waiting: boolean) {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    if (!waiting) return;
    const timers = [setTimeout(() => setStage(1), 300), setTimeout(() => setStage(2), 3000), setTimeout(() => setStage(3), 10000)];
    return () => {
      timers.forEach(clearTimeout);
      setStage(0);
    };
  }, [waiting]);
  return waiting ? stage : 0;
}

function Header({ total, done, checking }: { total: number; done: number; checking?: boolean }) {
  return (
    <header className="flex flex-col gap-3 pt-2 pb-5">
      <div className="flex items-center justify-between">
        <h1 className="text-display">오늘 할 일</h1>
        {checking && (
          <span className="inline-flex h-7 items-center gap-1 rounded-full bg-brand-soft px-2.5 text-small text-ink-2" role="status">
            <Icon name="refresh" size={16} className="animate-spin [animation-duration:2s]" />새 할 일 확인 중
          </span>
        )}
      </div>
      <ProgressSteps total={total} done={done} />
    </header>
  );
}

function SkeletonCard() {
  return (
    <div className="flex flex-col gap-4 rounded-[20px] border border-line bg-surface p-5" aria-hidden>
      <Bone className="h-8 w-[110px] rounded-full" />
      <Bone className="h-4 w-[160px]" />
      <Bone className="h-4 w-[136px]" />
      <Bone className="mt-2 h-4 w-[130px]" />
      <Bone className="mt-2 h-3.5 w-full" />
      <Bone className="h-3.5 w-[155px]" />
    </div>
  );
}

function Loading({ stage, onRetry }: { stage: number; onRetry: () => void }) {
  if (stage === 0) return <Header total={1} done={0} />;
  const say = stage === 1 ? "새 할 일을\n확인하고 있어요" : stage === 2 ? "조금만 기다려 주세요\n하나도 빠짐없이 모을게요" : "생각보다 오래 걸려요\n다시 불러와 볼까요?";
  return (
    <>
      <Header total={1} done={0} />
      <div role="status" aria-live="polite" className="flex flex-1 flex-col">
        <SkeletonCard />
        <div className="h-5" />
        <DonnaSays img="b1-1">{say}</DonnaSays>
        <div className="flex-1" />
        {stage === 3 ? (
          <SecondaryButton outline onClick={onRetry}>
            <Icon name="refresh" size={22} />
            <span className="ml-1.5">다시 불러오기</span>
          </SecondaryButton>
        ) : (
          <Bone className="h-14 w-full rounded-[14px]" />
        )}
      </div>
    </>
  );
}

function Offline({ onRetry }: { onRetry: () => void }) {
  return (
    <>
      <Header total={0} done={0} />
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <Image loading="eager" src="/donna/question.png" alt="" width={133} height={196} />
        <h2 className="mt-3 text-display">
          인터넷이
          <br />
          잠시 끊겼어요
        </h2>
        <p className="mt-2 text-body text-ink-2">할 일은 그대로 있어요</p>
      </div>
      <PrimaryButton onClick={onRetry}>다시 불러오기</PrimaryButton>
    </>
  );
}

const NEXT_ICON: Record<Slot, IconName> = { OPENING: "sunrise", AFTERNOON: "sun", CLOSING: "moon" };

function AllDone({ total, settings, now }: { total: number; settings: StoreSettings; now: Date }) {
  const next = nextSlot(settings.slots, now);
  return (
    <>
      <Header total={Math.max(total, 1)} done={Math.max(total, 1)} />
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <Image src="/donna/b4-2.png" alt="" width={212} height={220} priority />
        <h2 className="mt-3 text-display">
          오늘 할 일을
          <br />다 끝냈어요
        </h2>
        <p className="mt-3.5 flex items-center gap-2 text-body text-ink-2">
          <Icon name={NEXT_ICON[next.slot as Slot]} size={24} />
          다음 알림은 {next.tomorrow ? "내일 " : ""}
          {slotLabel(settings, next.slot as Slot)} {next.time}
        </p>
      </div>
    </>
  );
}

/** "나중에 할게요" 시트 (04-22). 고를 수 있는 때는 지금 다음의 알림 시각 3개다. */
function LaterSheet({ open, onClose, onPick, settings, now }: { open: boolean; onClose: () => void; onPick: (iso: string) => void; settings: StoreSettings; now: Date }) {
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
    <Sheet open={open} onClose={onClose} title={"언제 다시\n알려 드릴까요?"}>
      <fieldset className="flex flex-col gap-2.5">
        <legend className="sr-only">다시 알려 드릴 때</legend>
        {choices.map((c, i) => (
          <label
            key={c.iso}
            className={`flex h-14 cursor-pointer items-center gap-3 rounded-[14px] border px-4 text-body ${
              picked === i ? "border-brand bg-brand-soft font-medium" : "border-line bg-surface"
            }`}
          >
            <input type="radio" name="later" className="sr-only" checked={picked === i} onChange={() => setPicked(i)} />
            <Icon name={c.icon} size={24} className="text-ink-2" />
            <span className="flex-1">{c.label}</span>
            <span className="text-ink-2">{c.time}</span>
          </label>
        ))}
      </fieldset>
      <div className="mt-5">
        <PrimaryButton onClick={() => choices[picked] && onPick(choices[picked].iso)}>이때 알려 주세요</PrimaryButton>
      </div>
    </Sheet>
  );
}

/** 04-4n: 알림을 켜지 않고 들어왔을 때 위에 뜨는 띠 */
function NotifyOffBanner() {
  const turnOn = async () => {
    // 띠는 누르자마자 닫는다. 브라우저가 권한 창을 띄운 채 답을 안 주면 기다리다 띠가 남기 때문이다.
    prefs.write({ notifyOff: false });
    let result: NotificationPermission | "unsupported" = "unsupported";
    try {
      result = typeof Notification === "undefined" ? "unsupported" : await Notification.requestPermission();
    } catch {
      /* 알림을 물어볼 수 없는 브라우저 */
    }
    if (result === "granted") flashToast("알림을 켰어요", "고른 시간에만 알려 드려요");
    else flashToast("휴대폰 설정에서 알림을 허용해 주세요", "허용하면 고른 시간에 알려 드려요");
  };
  return (
    <div className="mb-2 flex items-center gap-2 rounded-2xl bg-urgent-soft py-2 pr-2 pl-3.5 text-urgent">
      <Icon name="bellOff" size={22} />
      <span className="flex-1 text-label">알림이 꺼져 있어요</span>
      <button type="button" onClick={turnOn} className="h-9 rounded-xl bg-brand px-3.5 text-small font-bold text-brand-ink">
        켜기
      </button>
    </div>
  );
}

export function TodayScreen() {
  const mounted = useMounted();
  const now = useMemo(() => (mounted ? currentNow() : new Date(0)), [mounted]);
  const { data, error, isPending, isFetching, refetch } = useHomeData();
  const store = useCardState();
  const p = prefs.use();
  const savedDrafts = drafts.use();
  const stage = useWaitStage(mounted && isPending);
  const [laterFor, setLaterFor] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  // 검토용 ?sheet=later 이면 맨 앞 카드의 "나중에" 시트(04-22)를 연 채로 보여 준다.
  const [sheetAsked, setSheetAsked] = useState(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("sheet") === "later");

  const view = useMemo(() => {
    if (!data || !mounted) return null;
    return buildTodayCards(data, now, p, store, new URLSearchParams(window.location.search).get("card"), savedDrafts);
  }, [data, mounted, now, store, p, savedDrafts]);

  if (!mounted) return <Header total={1} done={0} />;

  if (!data) {
    if (error instanceof ApiFailure && error.offline) return <Offline onRetry={() => refetch()} />;
    if (error) return <Loading stage={3} onRetry={() => refetch()} />;
    return <Loading stage={stage} onRetry={() => refetch()} />;
  }

  if (!view || view.open.length === 0) {
    return <AllDone total={view?.total ?? 0} settings={data.settings.settings} now={now} />;
  }

  const card = view.open[0];
  if (sheetAsked && laterFor === null) {
    setSheetAsked(false);
    setLaterFor(card.id);
  }
  const act = (a: NonNullable<CardView["secondary"]>) => {
    if ("href" in a) return a.done ? { href: a.href, onClick: () => markDone(card.id) } : { href: a.href };
    const done = async () => {
      if (a.reply) {
        const r = a.reply;
        if (r.mode === "schedule") {
          // 실행 시각에 올리도록 맡긴다. 제안: POST /api/plan/{plan_id}/approve
          markDone(`APPROVAL_REQUEST:${r.planId}`);
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
        markDone(`APPROVAL_REQUEST:${r.planId}`);
        markDone(`EXECUTE_REMINDER:${r.planId}`);
        flashToast("답글을 올렸어요", `${r.platform}에서 볼 수 있어요`);
        return;
      }
      if (a.publish) {
        setSending(true);
        try {
          const saved = drafts.read();
          for (const id of a.publish) await publishReply(id, saved[id]);
        } catch {
          flashToast("답글을 못 올렸어요", "인터넷이 끊겼어요. 다시 눌러 주세요");
          return;
        } finally {
          setSending(false);
        }
        for (const id of a.publish) markDone(`EXECUTE_REMINDER:${id}`);
      }
      if (card.id === "FIRST_DAY") prefs.write({ firstDayPending: false });
      else markDone(card.id);
      if (a.declineNaver) prefs.write({ naverDeclined: true });
      if (a.toast) flashToast(a.toast.title, a.toast.sub);
    };
    return { onClick: a.action === "done" ? done : () => setLaterFor(card.id) };
  };

  return (
    <>
      {p.notifyOff && <NotifyOffBanner />}
      <Header total={view.total} done={view.done + 1} checking={isFetching} />
      <section aria-live="polite" className="flex flex-1 flex-col">
        <TaskCard key={card.id} card={card} />
        <div className="h-5" />
        {card.draft ? (
          <>
            <DraftBubble img={card.draft.img} text={card.draft.text} />
            <div className="mt-1 flex items-center gap-2 text-ink-2">
              <Icon name="shield" size={18} className="shrink-0 text-done" />
              <span className="flex-1 text-small">누르기 전엔 올라가지 않아요</span>
              <Link href={card.draft.editHref} className="flex min-h-11 items-center gap-0.5 pl-2 text-label text-brand">
                고쳐 쓰기
                <Icon name="chevR" size={18} />
              </Link>
            </div>
          </>
        ) : (
          <DonnaSays img={card.donna.img}>{card.donna.text}</DonnaSays>
        )}
        <div className="min-h-6 flex-1" />
        <div className="flex flex-col gap-1">
          <PrimaryButton {...act(card.primary)} disabled={sending}>
            {sending ? "올리는 중" : card.primary.label}
          </PrimaryButton>
          {card.secondary && <SecondaryButton {...act(card.secondary)}>{card.secondary.label}</SecondaryButton>}
        </div>
      </section>
      <LaterSheet
        open={laterFor !== null}
        onClose={() => setLaterFor(null)}
        settings={data.settings.settings}
        now={now}
        onPick={(iso) => {
          if (laterFor) snooze(laterFor, iso);
          setLaterFor(null);
          flashToast("다시 알려 드릴게요", `${iso.slice(0, 10) === ymd(now) ? "오늘" : "내일"} ${iso.slice(11, 16)}에 알려 드려요`);
        }}
      />
    </>
  );
}
