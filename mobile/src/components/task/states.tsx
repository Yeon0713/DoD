// 홈(07-1)과 지금 할 일(07-3)이 같이 쓰는 부품: 불러오는 중(06-8 계열), 인터넷 끊김(06-9), 알림 꺼짐 띠(06-4n).
import { useEffect, useState, type ReactElement, type ReactNode } from "react";
import { Animated, Easing, Platform, Pressable, ScrollView, View, type RefreshControlProps } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon, type IconName } from "@/components/icons/Icon";
import { Bone, DonnaImage, DonnaSays, PrimaryButton } from "@/components/ui/parts";
import { flashToast, prefs } from "@/lib/localStore";
import tokens from "@/theme/tokens.json";
import type { Slot } from "@/types/contract";
import { askNotify } from "./askNotify";

const C = tokens.colors;

export const NEXT_ICON: Record<Slot, IconName> = { OPENING: "sunrise", AFTERNOON: "sun", CLOSING: "moon" };

/** 불러오기 시작 후 지난 시간 단계: 0 = 0.3초 전, 1 = 뼈대, 2 = 3초 넘음, 3 = 10초 넘음 */
export function useWaitStage(waiting: boolean) {
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

/** "새 할 일 확인 중" 옆에서 천천히 도는 아이콘 */
function Spinner() {
  const [v] = useState(() => new Animated.Value(0));
  useEffect(() => {
    const loop = Animated.loop(Animated.timing(v, { toValue: 1, duration: 2000, easing: Easing.linear, useNativeDriver: Platform.OS !== "web" }));
    loop.start();
    return () => loop.stop();
  }, [v]);
  const rotate = v.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "360deg"] });
  return (
    <Animated.View style={{ transform: [{ rotate }] }}>
      <Icon name="refresh" size={16} color={C["ink-2"]} />
    </Animated.View>
  );
}

/** 06-8b: 다시 열 때 지난 할 일을 먼저 보여 주고 옆에 띄우는 표시 */
export function Checking() {
  return (
    <View className="h-7 flex-row items-center gap-1 rounded-full bg-brand-soft px-2.5" accessibilityLiveRegion="polite">
      <Spinner />
      <Text className="text-small text-ink-2">새 할 일 확인 중</Text>
    </View>
  );
}

function SkeletonCard() {
  return (
    <View className="gap-4 rounded-card border border-line bg-surface p-5" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <Bone className="h-8 w-[110px] rounded-full" />
      <Bone className="h-4 w-[160px]" />
      <Bone className="h-4 w-[136px]" />
      <Bone className="mt-2 h-4 w-[130px]" />
      <Bone className="mt-2 h-3.5 w-full" />
      <Bone className="h-3.5 w-[155px]" />
    </View>
  );
}

/** 06-8 (0.3초부터), 06-8c (3초 넘음), 06-8d (10초 넘음). header는 화면마다 다르다. */
export function Loading({ stage, onRetry, header }: { stage: number; onRetry: () => void; header: ReactNode }) {
  if (stage === 0) return <>{header}</>;
  const say = stage === 1 ? "새 할 일을\n확인하고 있어요" : stage === 2 ? "조금만 기다려 주세요\n하나도 빠짐없이 모을게요" : "생각보다 오래 걸려요\n다시 불러와 볼까요?";
  return (
    <>
      {header}
      <View className="flex-1" accessibilityLiveRegion="polite">
        <SkeletonCard />
        <View className="h-5" />
        <DonnaSays img="b1-1">{say}</DonnaSays>
        <View className="min-h-6 flex-1" />
        {stage === 3 ? (
          <Pressable
            testID="retry"
            accessibilityRole="button"
            onPress={onRetry}
            className="h-14 w-full flex-row items-center justify-center gap-1.5 rounded-button border border-brand bg-surface active:bg-brand-soft"
          >
            <Icon name="refresh" size={22} color={C.brand} />
            <Text className="text-button text-brand">다시 불러오기</Text>
          </Pressable>
        ) : (
          <Bone className="h-14 w-full rounded-button" />
        )}
      </View>
    </>
  );
}

/** 06-9 인터넷이 끊겼을 때 */
export function Offline({ onRetry, header }: { onRetry: () => void; header: ReactNode }) {
  return (
    <>
      {header}
      <View className="flex-1 items-center justify-center">
        <DonnaImage img="question" size={196} />
        <Text className="mt-3 text-center text-display text-ink">{"인터넷이\n잠시 끊겼어요"}</Text>
        <Text className="mt-2 text-center text-body text-ink-2">할 일은 그대로 있어요</Text>
      </View>
      <PrimaryButton onPress={onRetry}>다시 불러오기</PrimaryButton>
    </>
  );
}

/** 06-4n: 알림을 켜지 않고 들어왔을 때 위에 뜨는 띠 */
export function NotifyOffBanner() {
  const turnOn = async () => {
    // 띠는 누르자마자 닫는다. 권한 창이 답을 안 주면 기다리다 띠가 남기 때문이다.
    prefs.write({ notifyOff: false });
    if (await askNotify()) flashToast("알림을 켰어요", "고른 시간에만 알려 드려요");
    else flashToast("휴대폰 설정에서 알림을 허용해 주세요", "허용하면 고른 시간에 알려 드려요");
  };
  return (
    <View className="mb-2 flex-row items-center gap-2 rounded-2xl bg-urgent-soft py-2 pl-3.5 pr-2">
      <Icon name="bellOff" size={22} color={C.urgent} />
      <Text className="flex-1 text-label text-urgent">알림이 꺼져 있어요</Text>
      <Pressable testID="notify-on" accessibilityRole="button" accessibilityLabel="알림 켜기" hitSlop={8} onPress={turnOn} className="h-9 justify-center rounded-xl bg-brand px-3.5 active:opacity-90">
        <Text className="text-small font-bold text-brand-ink">켜기</Text>
      </Pressable>
    </View>
  );
}

/** 내용만 스크롤한다. 아래로 당기면 새 할 일을 다시 받는다. */
export function Scroll({ refresh, children }: { refresh?: ReactElement<RefreshControlProps>; children: ReactNode }) {
  return (
    <ScrollView className="flex-1" contentContainerStyle={{ flexGrow: 1 }} refreshControl={refresh} showsVerticalScrollIndicator={false}>
      {children}
    </ScrollView>
  );
}
