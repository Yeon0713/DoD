// 답글 흐름: 06-5 답글 보기, 06-5f 못 올렸을 때, 06-11r/06-35r 단골 답글, 06-39r 긴 리뷰와 사진, 06-21 고쳐 쓰기,
// 06-25 좋은 리뷰 묶음, 06-25b 하나씩 보기.
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, TextInput, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon } from "@/components/icons/Icon";
import { StarRow } from "@/components/task/StarRow";
import { back, goHome } from "@/components/ui/nav";
import { Bone, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { DraftBubble, FailNote, Note, ReviewBox, SubPage } from "@/components/ui/sub";
import { publishReply, rewriteReply } from "@/lib/actions";
import { ApiFailure } from "@/lib/api";
import { markDone, markPlanDone } from "@/lib/cardState";
import { PLATFORM_KO } from "@/lib/labels";
import { drafts, flashToast, prefs } from "@/lib/localStore";
import { clockKo, relativeDay } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import { draftFor } from "@/mocks/extras";
import tokens from "@/theme/tokens.json";
import type { PlanItem, Review } from "@/types/contract";
import { PhotoViewer } from "./PhotoViewer";

const C = tokens.colors;

/** 주소의 [planId]. 이미 풀린 값이면 그대로 쓴다. */
export function usePlanId(): string {
  const { planId } = useLocalSearchParams<{ planId?: string }>();
  const raw = Array.isArray(planId) ? planId[0] : (planId ?? "");
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
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
      <View className="gap-4" accessibilityState={{ busy: true }}>
        <Bone className="h-6 w-40" />
        <Bone className="h-20 w-full rounded-2xl" />
        <Bone className="h-28 w-full rounded-2xl" />
      </View>
    </SubPage>
  );
}

/** 손님 리뷰(6줄까지)와 사진. 사진을 누르면 크게 본다. */
function ReviewWithPhotos({ review, showPlatform = true }: { review: Review; showPlatform?: boolean }) {
  const [photo, setPhoto] = useState<number | null>(null);
  return (
    <>
      <ReviewBox review={review} showPlatform={showPlatform} lines={6} onPhoto={setPhoto} />
      <PhotoViewer photos={review.photos ?? []} index={photo} onClose={() => setPhoto(null)} />
    </>
  );
}

export function ReplyScreen() {
  const planId = usePlanId();
  const { view } = useLocalSearchParams<{ view?: string }>();
  const { data, now } = useHome();
  const saved = drafts.useValue();
  // 검토용 ?view=failed 이면 06-5f 못 올렸을 때를 바로 본다.
  const [state, setState] = useState<"idle" | "sending" | "failed">(view === "failed" ? "failed" : "idle");

  if (!data) return <LoadingSub title="리뷰 답글" />;
  const p = data.plan.plan_items.find((x) => x.plan_id === planId);
  const review = findReview(p, data.reviews.reviews);
  if (!p || !review) {
    return (
      <SubPage title="리뷰 답글" backHref="/">
        <Text className="text-body text-ink-2">이 답글은 이미 끝났거나 찾을 수 없어요.</Text>
      </SubPage>
    );
  }
  const nudge = p.task_type === "REORDER_NUDGE";
  // 빈 글이 저장돼 있으면 도나 초안을 쓴다 (빈 답글은 올리지 않는다).
  const text = saved[planId]?.trim() ? saved[planId] : draftFor(p, review);
  const regular = p.revisit_class === "WEEKLY" || p.revisit_class === "MONTHLY" || nudge;
  const exec = p.execute_at ?? p.approval_request_at;
  // 실행 시각이 지났으면 지금 올리고, 아직이면 그때 올리도록 맡긴다.
  const postNow = !regular || new Date(exec).getTime() <= now.getTime();
  const title = nudge ? "단골 손님 인사" : regular ? "단골 손님 답글" : "리뷰 답글";

  const send = async () => {
    setState("sending");
    try {
      await publishReply(planId, text);
    } catch {
      setState("failed");
      return;
    }
    const sent = { note: nudge ? "인사를 보냈어요" : "답글을 올렸어요", reply: text };
    markPlanDone(planId, sent);
    flashToast(nudge ? "인사를 보냈어요" : "답글을 올렸어요", `${PLATFORM_KO[review.platform]}에서 볼 수 있어요`);
    goHome();
  };
  const approve = () => {
    markDone(`APPROVAL_REQUEST:${planId}`, { note: nudge ? "인사를 맡겼어요" : "답글을 맡겼어요", reply: text });
    flashToast(nudge ? "인사를 맡겼어요" : "답글을 맡겼어요", `${relativeDay(exec, now)} ${clockKo(exec)}에 ${nudge ? "보낼게요" : "올릴게요"}`);
    goHome();
  };

  return (
    <SubPage
      title={title}
      footer={
        <>
          {postNow ? (
            <PrimaryButton onPress={send} disabled={state === "sending"}>
              {state === "sending" ? "올리는 중" : state === "failed" ? "다시 올리기" : "이대로 올리기"}
            </PrimaryButton>
          ) : (
            <PrimaryButton onPress={approve}>이대로 좋아요</PrimaryButton>
          )}
          <SecondaryButton testID="edit" outline href={`/reply/${encodeURIComponent(planId)}/edit`}>
            고쳐 쓰기
          </SecondaryButton>
        </>
      }
    >
      <View className="gap-5">
        <ReviewWithPhotos review={review} />
        <DraftBubble text={text} />
        {postNow ? <Note icon="shield">사장님이 누르기 전엔 올라가지 않아요</Note> : <Note icon="clock">{`${relativeDay(exec, now)} ${clockKo(exec)}에 올려요`}</Note>}
      </View>
      <View className="flex-1" />
      {state === "failed" ? <FailNote title={nudge ? "인사를 못 보냈어요" : "답글을 못 올렸어요"} sub={"인터넷이 끊겼어요.\n쓴 답글은 그대로 있어요"} /> : null}
    </SubPage>
  );
}

export function EditReplyScreen() {
  const planId = usePlanId();
  const { data } = useHome();
  const saved = drafts.useValue();
  const [text, setText] = useState<string | null>(null);
  // 도나가 다시 쓰기 바로 전의 글. "되돌리기"로 돌아간다 (다시 쓴 글이 마음에 안 들 때 사장님 글이 사라지지 않게)
  const [before, setBefore] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // "offline": 인터넷이 끊김, "server": 서버가 다시 쓰지 못한다고 답함 (CLOVA 키 없음, 응답 없음 등)
  const [failed, setFailed] = useState<false | "offline" | "server">(false);

  if (!data) return <LoadingSub title="답글 고쳐 쓰기" />;
  const p = data.plan.plan_items.find((x) => x.plan_id === planId);
  const review = findReview(p, data.reviews.reviews);
  const value = text ?? (saved[planId]?.trim() ? saved[planId] : draftFor(p, review));
  // 빈 글이나 공백만 있는 글은 저장하지 않는다.
  const empty = value.trim().length === 0;

  const rewrite = async (style: "short" | "polite") => {
    setBusy(true);
    setFailed(false);
    try {
      const next = await rewriteReply(value, style, planId);
      setBefore(value);
      setText(next);
    } catch (e) {
      setFailed(e instanceof ApiFailure && !e.offline ? "server" : "offline");
    } finally {
      setBusy(false);
    }
  };

  return (
    <SubPage
      title="답글 고쳐 쓰기"
      footer={
        <PrimaryButton
          disabled={empty}
          onPress={() => {
            drafts.write({ [planId]: value.trim() });
            back();
          }}
        >
          다 고쳤어요
        </PrimaryButton>
      }
    >
      <TextInput
        testID="reply-text"
        accessibilityLabel="답글"
        value={value}
        onChangeText={(t) => {
          setText(t);
          setBefore(null);
        }}
        multiline
        editable={!busy}
        textAlignVertical="top"
        className={`min-h-[150px] w-full rounded-2xl border-2 border-brand bg-surface px-4 py-3.5 text-body text-ink ${busy ? "opacity-60" : ""}`}
      />
      <View className="mt-3 flex-row gap-2.5">
        {(["short", "polite"] as const).map((s) => (
          <Pressable
            key={s}
            testID={`rewrite-${s}`}
            accessibilityRole="button"
            disabled={busy || empty}
            accessibilityState={{ disabled: busy || empty }}
            onPress={() => rewrite(s)}
            className={`h-12 flex-1 items-center justify-center rounded-full border border-brand bg-surface active:bg-brand-soft ${busy || empty ? "opacity-50" : ""}`}
          >
            <Text className="text-body font-medium text-ink">{s === "short" ? "더 짧게" : "더 정중하게"}</Text>
          </Pressable>
        ))}
      </View>
      <Text className="mt-2 text-center text-small text-ink-2" accessibilityLiveRegion="polite">
        {busy ? "도나가 다시 쓰고 있어요" : "누르면 도나가 다시 써요"}
      </Text>
      {before !== null && !busy ? (
        <Pressable
          testID="rewrite-undo"
          accessibilityRole="button"
          hitSlop={8}
          onPress={() => {
            setText(before);
            setBefore(null);
          }}
          className="mt-2 h-11 flex-row items-center justify-center gap-1.5 self-center px-3"
        >
          <Icon name="undo" size={20} color={C.brand} />
          <Text className="text-label font-medium text-brand">바로 앞 글로 되돌리기</Text>
        </Pressable>
      ) : null}
      {empty ? (
        <Text className="mt-3 text-center text-label text-urgent" accessibilityLiveRegion="polite">
          답글을 한 글자 이상 적어 주세요
        </Text>
      ) : null}
      {failed === "offline" ? <FailNote title="다시 쓰지 못했어요" sub={"인터넷이 끊겼어요.\n쓴 답글은 그대로 있어요"} /> : null}
      {failed === "server" ? <FailNote icon="refresh" title="다시 쓰지 못했어요" sub={"도나가 지금은 다시 쓸 수 없어요.\n쓴 답글은 그대로 있고, 직접 고칠 수 있어요"} /> : null}
    </SubPage>
  );
}

export function BatchReplyScreen() {
  const planId = usePlanId();
  const { one } = useLocalSearchParams<{ one?: string }>();
  const { data, now } = useHome();
  const saved = drafts.useValue();

  if (!data) return <LoadingSub title="좋은 리뷰" />;
  const first = data.plan.plan_items.find((x) => x.plan_id === planId);
  const group = data.plan.plan_items.filter((x) => x.task_type === "REVISIT_REPLY" && x.revisit_class === "BASIC" && x.execute_at === first?.execute_at);
  const items = group.map((p) => ({ p, r: findReview(p, data.reviews.reviews) })).filter((x): x is { p: PlanItem; r: Review } => !!x.r);
  const exec = first?.execute_at ?? "";
  const when = exec ? `${relativeDay(exec, now)} ${clockKo(exec)}` : "토요일 오전";
  const n = items.length;

  const finish = () => {
    markDone(`BASIC:APPROVAL_REQUEST:${exec}`, { note: `답글 ${n}개를 맡겼어요` });
    prefs.write({ firstDayPending: false });
    flashToast(`답글 ${n}개를 맡겼어요`, `${when}에 함께 올릴게요`);
    goHome();
  };

  if (one !== undefined && one !== "") {
    const i = Number(one);
    const it = items[i];
    if (!it) return <LoadingSub title="리뷰 답글" />;
    return (
      <SubPage
        title="리뷰 답글"
        footer={
          <>
            <PrimaryButton onPress={() => (i + 1 < n ? router.setParams({ one: String(i + 1) }) : finish())}>이대로 좋아요</PrimaryButton>
            <SecondaryButton testID="edit" outline href={`/reply/${encodeURIComponent(it.p.plan_id)}/edit`}>
              고쳐 쓰기
            </SecondaryButton>
          </>
        }
      >
        <View className="gap-5">
          <ReviewWithPhotos key={it.p.plan_id} review={it.r} />
          <DraftBubble text={saved[it.p.plan_id] ?? draftFor(it.p, it.r)} />
          <Note icon="clock">{`주말 주문 전에 손님이 보게\n${when}에 함께 올려요`}</Note>
          <Text className="text-small text-ink-3">
            {n}개 중 {i + 1}번째
          </Text>
        </View>
      </SubPage>
    );
  }

  return (
    <SubPage
      title={`좋은 리뷰 ${n}개`}
      footer={
        <>
          <View className="mb-2">
            <Note icon="clock" center>{`주말 주문 전에 손님이 보게\n${when}에 올려요`}</Note>
          </View>
          <PrimaryButton onPress={finish}>{n}개 모두 올려 주세요</PrimaryButton>
          <SecondaryButton testID="one-by-one" outline href={`/reply/batch/${encodeURIComponent(planId)}?one=0`}>
            하나씩 볼게요
          </SecondaryButton>
        </>
      }
    >
      <View>
        {items.map(({ p, r }) => (
          <View key={p.plan_id} className="flex-row items-start gap-3 border-b border-line py-3.5">
            <View className="flex-1 gap-1">
              <StarRow rating={r.rating} text={PLATFORM_KO[r.platform]} size={20} />
              <Text className="text-body text-ink">{r.text}</Text>
            </View>
            <View className="items-center gap-1 pt-2">
              <View className="h-8 w-8 items-center justify-center rounded-full bg-done-soft">
                <Icon name="check" size={20} color={C.done} />
              </View>
              <Text className="text-small text-done">답글 써 둠</Text>
            </View>
          </View>
        ))}
      </View>
    </SubPage>
  );
}
