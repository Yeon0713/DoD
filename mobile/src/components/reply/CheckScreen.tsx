// 06-24 같은 불만 점검, 06-24o 펼침. 가르치지 않고 손님 말과 도나가 찾은 사실만 보여 준다 (06 B). 판단은 사장님이 한다.
import { useState } from "react";
import { Pressable, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon } from "@/components/icons/Icon";
import { goToday } from "@/components/today/goToday";
import { Bone, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { SubPage } from "@/components/ui/sub";
import { markDone } from "@/lib/cardState";
import { checkData, OTHER_STORES } from "@/lib/check";
import { COMPLAINT_REPEAT, PLATFORM_KO } from "@/lib/labels";
import { flashToast } from "@/lib/localStore";
import { useHome } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";
import type { ComplaintType, Review } from "@/types/contract";
import { usePlanId } from "./ReplyScreens";

const C = tokens.colors;

/** 위 제목 줄 ("배달 리뷰") */
const TOPIC: Record<ComplaintType, string> = {
  DELIVERY_DELAY: "배달 리뷰",
  TASTE: "맛 리뷰",
  PORTION: "양 리뷰",
  HYGIENE: "위생 리뷰",
  PHOTO_MISMATCH: "사진 리뷰",
  SERVICE: "응대 리뷰",
};

/** 손님 리뷰 말풍선 + 위에 작은 줄 "쿠팡이츠 손님, 별 2개, 12일" */
function ReviewBubble({ r }: { r: Review }) {
  return (
    <View
      className="border border-line bg-surface px-4 py-3"
      style={{ borderTopLeftRadius: 4, borderTopRightRadius: 18, borderBottomLeftRadius: 18, borderBottomRightRadius: 18 }}
    >
      <Text className="text-small text-ink-2">
        {PLATFORM_KO[r.platform]} 손님, 별 {r.rating}개, {Number(r.written_at.slice(8, 10))}일
      </Text>
      <Text className="text-body text-ink">{r.text}</Text>
    </View>
  );
}

export function CheckScreen() {
  const planId = usePlanId();
  const { data } = useHome();
  const [open, setOpen] = useState(false);

  if (!data) {
    return (
      <SubPage title="리뷰">
        <View className="gap-4">
          <Bone className="h-16 w-full rounded-2xl" />
          <Bone className="h-24 w-full rounded-2xl" />
        </View>
      </SubPage>
    );
  }
  const p = data.plan.plan_items.find((x) => x.plan_id === planId);
  if (!p) {
    return (
      <SubPage title="리뷰" backHref="/">
        <Text className="text-body text-ink-2">이 일은 이미 끝났거나 찾을 수 없어요.</Text>
      </SubPage>
    );
  }
  const { type, reviews, facts } = checkData(p, data.reviews.reviews, data.settings.settings);

  // 무엇을 고르든 일주일 뒤 결과 알림(06-44)은 그대로 온다.
  const finish = (title: string) => {
    markDone(`APPROVAL_REQUEST:${planId}`, { note: "점검했어요" });
    flashToast(title, "일주일 뒤에 줄었는지 알려 드릴게요");
    goToday();
  };

  return (
    <SubPage
      title={TOPIC[type]}
      footer={
        <>
          <Text className="mb-1 text-center text-small text-ink-2">일주일 뒤에 줄었는지 알려 드릴게요</Text>
          <PrimaryButton onPress={() => finish("확인했어요")}>확인했어요</PrimaryButton>
          <SecondaryButton testID="already-know" onPress={() => finish("알겠어요")}>
            이미 알고 있어요
          </SecondaryButton>
        </>
      }
    >
      <Text className="text-display text-ink" accessibilityRole="header">
        {`${COMPLAINT_REPEAT[type]} 말이\n${reviews.length}번 나왔어요`}
      </Text>

      <View className="mt-3 gap-2">
        {reviews.map((r) => (
          <ReviewBubble key={r.review_id} r={r} />
        ))}
      </View>

      {facts.length ? (
        <View className="mt-3 gap-2 rounded-2xl bg-brand-soft px-4 py-3.5">
          <Text className="text-small text-brand">도나가 찾은 것</Text>
          {facts.map((f) => (
            <View key={f} className="flex-row items-center gap-2">
              <Icon name="clock" size={20} color={C.done} />
              <Text className="flex-1 text-body font-medium text-ink">{f}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <Pressable
        testID="fold-others"
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen(!open)}
        className="mt-4 min-h-12 flex-row items-center"
      >
        <Text className="flex-1 text-body text-ink-2">다른 가게는 이렇게 하기도 해요</Text>
        <Text className="text-label font-bold text-brand">{open ? "접기" : "펼치기"}</Text>
      </Pressable>
      {open ? (
        <View className="gap-2 pb-2">
          {OTHER_STORES[type].map((t) => (
            <Text key={t} className="text-body text-ink-2">
              • {t}
            </Text>
          ))}
        </View>
      ) : null}
    </SubPage>
  );
}
