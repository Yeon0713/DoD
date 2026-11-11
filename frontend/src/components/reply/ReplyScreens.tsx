"use client";
// 답글 흐름: 04-5 답글 보기, 04-5f 못 올렸을 때, 04-11r/04-35r 단골 답글, 04-21 고쳐 쓰기,
// 04-25 좋은 리뷰 묶음, 04-25b 하나씩 보기.
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Icon } from "@/components/icons/Icon";
import { Bone, PrimaryButton, SecondaryButton, Stars } from "@/components/ui/parts";
import { DraftBubble, FailNote, Note, ReviewBox, SubPage } from "@/components/ui/sub";
import { publishReply, rewriteReply } from "@/lib/actions";
import { markDone } from "@/lib/cardState";
import { PLATFORM_KO } from "@/lib/labels";
import { drafts, flashToast, prefs } from "@/lib/localStore";
import { clockKo, relativeDay } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import { mockDraft, mockNudge } from "@/mocks/extras";
import type { PlanItem, Review } from "@/types/contract";

function useParam(name: string) {
  const params = useParams<Record<string, string>>();
  return decodeURIComponent(params[name] ?? "");
}

function findReview(p: PlanItem | undefined, reviews: Review[]): Review | undefined {
  if (!p) return undefined;
  if (p.basis.kind === "REVIEW") return reviews.find((r) => r.review_id === p.basis.ref_id);
  if (p.basis.kind === "CUSTOMER")
    return reviews.filter((r) => r.customer_key === p.basis.ref_id).sort((a, b) => b.written_at.localeCompare(a.written_at))[0];
  return undefined;
}

function LoadingSub({ title }: { title: string }) {
  return (
    <SubPage title={title}>
      <div className="flex flex-col gap-4" aria-busy>
        <Bone className="h-6 w-40" />
        <Bone className="h-20 w-full rounded-2xl" />
        <Bone className="h-28 w-full rounded-2xl" />
      </div>
    </SubPage>
  );
}

export function ReplyScreen() {
  const planId = useParam("planId");
  const router = useRouter();
  const { data, now } = useHome();
  const saved = drafts.use();
  // 검토용 ?view=failed 이면 04-5f 못 올렸을 때를 바로 본다.
  const [state, setState] = useState<"idle" | "sending" | "failed">(useSearchParams().get("view") === "failed" ? "failed" : "idle");

  if (!data) return <LoadingSub title="리뷰 답글" />;
  const p = data.plan.plan_items.find((x) => x.plan_id === planId);
  const review = findReview(p, data.reviews.reviews);
  if (!p || !review) {
    return (
      <SubPage title="리뷰 답글" backHref="/">
        <p className="text-body text-ink-2">이 답글은 이미 끝났거나 찾을 수 없어요.</p>
      </SubPage>
    );
  }
  const nudge = p.task_type === "REORDER_NUDGE";
  const text = saved[planId] ?? (nudge ? mockNudge(review) : mockDraft(review));
  const regular = p.revisit_class === "WEEKLY" || p.revisit_class === "MONTHLY" || p.task_type === "REORDER_NUDGE";
  const exec = p.execute_at ?? p.approval_request_at;
  // 실행 시각이 지났으면 지금 올리고, 아직이면 그때 올리도록 맡긴다.
  const postNow = !regular || new Date(exec).getTime() <= now.getTime();
  const title = p.task_type === "REORDER_NUDGE" ? "단골 손님 인사" : regular ? "단골 손님 답글" : "리뷰 답글";

  const send = async () => {
    setState("sending");
    try {
      await publishReply(planId, text);
      markDone(`APPROVAL_REQUEST:${planId}`);
      markDone(`EXECUTE_REMINDER:${planId}`);
      flashToast(nudge ? "인사를 보냈어요" : "답글을 올렸어요", `${PLATFORM_KO[review.platform]}에서 볼 수 있어요`);
      router.push("/");
    } catch {
      setState("failed");
    }
  };
  const approve = () => {
    markDone(`APPROVAL_REQUEST:${planId}`);
    flashToast(nudge ? "인사를 맡겼어요" : "답글을 맡겼어요", `${relativeDay(exec, now)} ${clockKo(exec)}에 ${nudge ? "보낼게요" : "올릴게요"}`);
    router.push("/");
  };

  return (
    <SubPage
      title={title}
      footer={
        <>
          {postNow ? (
            <PrimaryButton onClick={send} disabled={state === "sending"}>
              {state === "sending" ? "올리는 중" : state === "failed" ? "다시 올리기" : "이대로 올리기"}
            </PrimaryButton>
          ) : (
            <PrimaryButton onClick={approve}>이대로 좋아요</PrimaryButton>
          )}
          <SecondaryButton outline href={`/reply/${encodeURIComponent(planId)}/edit`}>
            고쳐 쓰기
          </SecondaryButton>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <ReviewBox review={review} showPlatform={regular} />
        <DraftBubble text={text} />
        {postNow ? <Note icon="shield">사장님이 누르기 전엔 올라가지 않아요</Note> : <Note icon="clock">{`${relativeDay(exec, now)} ${clockKo(exec)}에 올려요`}</Note>}
      </div>
      <div className="flex-1" />
      {state === "failed" && <FailNote title={nudge ? "인사를 못 보냈어요" : "답글을 못 올렸어요"} sub={"인터넷이 끊겼어요.\n쓴 글은 그대로 있어요"} />}
    </SubPage>
  );
}

export function EditReplyScreen() {
  const planId = useParam("planId");
  const router = useRouter();
  const { data } = useHome();
  const saved = drafts.use();
  const [text, setText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  if (!data) return <LoadingSub title="답글 고쳐 쓰기" />;
  const p = data.plan.plan_items.find((x) => x.plan_id === planId);
  const review = findReview(p, data.reviews.reviews);
  const value = text ?? saved[planId] ?? (p?.task_type === "REORDER_NUDGE" ? mockNudge(review) : mockDraft(review));

  const rewrite = async (style: "short" | "polite") => {
    setBusy(true);
    setFailed(false);
    try {
      setText(await rewriteReply(value, style));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <SubPage
      title="답글 고쳐 쓰기"
      footer={
        <PrimaryButton
          onClick={() => {
            drafts.write({ [planId]: value });
            router.back();
          }}
        >
          다 고쳤어요
        </PrimaryButton>
      }
    >
      <label className="sr-only" htmlFor="reply-text">
        답글
      </label>
      <textarea
        id="reply-text"
        value={value}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        aria-busy={busy}
        className={`w-full resize-none rounded-2xl border-2 border-brand bg-surface px-4 py-3.5 text-body text-ink outline-none ${busy ? "opacity-60" : ""}`}
      />
      <div className="mt-3 flex gap-2.5">
        {(["short", "polite"] as const).map((s) => (
          <button
            key={s}
            type="button"
            disabled={busy}
            onClick={() => rewrite(s)}
            className="h-12 flex-1 rounded-full border border-brand bg-surface text-body font-medium text-ink active:bg-brand-soft disabled:opacity-50"
          >
            {s === "short" ? "더 짧게" : "더 정중하게"}
          </button>
        ))}
      </div>
      <p className="mt-2 text-center text-small text-ink-2" aria-live="polite">
        {busy ? "도나가 다시 쓰고 있어요" : "누르면 도나가 다시 써요"}
      </p>
      {failed && <FailNote title="다시 쓰지 못했어요" sub={"인터넷이 끊겼어요.\n쓴 답글은 그대로 있어요"} />}
    </SubPage>
  );
}

export function BatchReplyScreen() {
  const planId = useParam("planId");
  const router = useRouter();
  const search = useSearchParams();
  const { data, now } = useHome();
  const saved = drafts.use();

  if (!data) return <LoadingSub title="좋은 리뷰" />;
  const first = data.plan.plan_items.find((x) => x.plan_id === planId);
  const group = data.plan.plan_items.filter(
    (x) => x.task_type === "REVISIT_REPLY" && x.revisit_class === "BASIC" && x.execute_at === first?.execute_at,
  );
  const items = group.map((p) => ({ p, r: findReview(p, data.reviews.reviews) })).filter((x): x is { p: PlanItem; r: Review } => !!x.r);
  const exec = first?.execute_at ?? "";
  const when = exec ? `${relativeDay(exec, now)} ${clockKo(exec)}` : "토요일 오전";
  const n = items.length;

  const finish = () => {
    markDone(`BASIC:APPROVAL_REQUEST:${exec}`);
    prefs.write({ firstDayPending: false });
    flashToast(`답글 ${n}개를 맡겼어요`, `${when}에 함께 올릴게요`);
    router.push("/");
  };

  const one = search.get("one");
  if (one !== null) {
    const i = Number(one);
    const it = items[i];
    if (!it) return null;
    return (
      <SubPage
        title="리뷰 답글"
        footer={
          <>
            <PrimaryButton onClick={() => (i + 1 < n ? router.replace(`?one=${i + 1}`) : finish())}>이대로 좋아요</PrimaryButton>
            <SecondaryButton outline href={`/reply/${encodeURIComponent(it.p.plan_id)}/edit`}>
              고쳐 쓰기
            </SecondaryButton>
          </>
        }
      >
        <div className="flex flex-col gap-5">
          <ReviewBox review={it.r} />
          <DraftBubble text={saved[it.p.plan_id] ?? mockDraft(it.r)} />
          <Note icon="clock">{`주말 주문 전에 손님이 보게\n${when}에 함께 올려요`}</Note>
          <p className="text-small text-ink-3">
            {n}개 중 {i + 1}번째
          </p>
        </div>
      </SubPage>
    );
  }

  return (
    <SubPage
      title={`좋은 리뷰 ${n}개`}
      footer={
        <>
          <div className="mb-2">
            <Note icon="clock" center>{`주말 주문 전에 손님이 보게\n${when}에 올려요`}</Note>
          </div>
          <PrimaryButton onClick={finish}>{n}개 모두 올려 주세요</PrimaryButton>
          <SecondaryButton outline href="?one=0">
            하나씩 볼게요
          </SecondaryButton>
        </>
      }
    >
      <ul className="flex flex-col">
        {items.map(({ p, r }) => (
          <li key={p.plan_id} className="flex items-start gap-3 border-b border-line py-3.5">
            <div className="flex flex-1 flex-col gap-1">
              <Stars rating={r.rating} suffix={PLATFORM_KO[r.platform]} />
              <p className="text-body text-balance text-ink">{r.text}</p>
            </div>
            <span className="flex shrink-0 flex-col items-center gap-1 pt-2 text-small text-done">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-done-soft">
                <Icon name="check" size={20} />
              </span>
              답글 써 둠
            </span>
          </li>
        ))}
      </ul>
    </SubPage>
  );
}
