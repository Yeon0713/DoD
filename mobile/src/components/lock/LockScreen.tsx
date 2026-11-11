// 06-23 잠금 화면에서 시작. 휴대폰 잠금 화면에 도나 알림이 온 모습이다.
// 실제 푸시 발송은 2차(알림톡 포함)라, 지금은 이 화면으로 "알림을 눌러 앱이 열리는" 흐름을 본다.
// 알림 내용은 그 시각 오늘 화면의 맨 앞 카드에서 만든다.
import { useMemo } from "react";
import { Image, Pressable, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { SafeAreaView } from "react-native-safe-area-context";
import { goTask } from "@/components/today/goToday";
import { DONNA_IMG } from "@/components/ui/donna";
import { useCardState } from "@/lib/cardState";
import { devFlags } from "@/lib/dev";
import { buildTodayCards } from "@/lib/todayCards";
import { hhmm, monthDay, weekdayName } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";

export function LockScreen() {
  const { data, now, prefs } = useHome();
  const store = useCardState();
  const view = useMemo(() => (data ? buildTodayCards(data, now, prefs, store) : null), [data, now, prefs, store]);
  const card = view?.open[0];
  const time = card ? hhmm(view!.slotOf[card.id] ?? now.toISOString()) : hhmm(now.toISOString());
  const title = card?.title.replace(/\n/g, " ") ?? "";

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: tokens.colors.ink }}>
      <View className="flex-1 items-center px-4 pt-16">
        <Text className="text-body font-medium text-brand-ink">{`${monthDay(now)} ${weekdayName(now)}`}</Text>
        <Text className="mt-1 text-display font-bold text-brand-ink" style={{ fontSize: 72, lineHeight: 84 }} accessibilityLabel={`지금 ${time}`}>
          {time}
        </Text>
        {card ? (
          <Pressable
            testID="lock-notice"
            accessibilityRole="button"
            accessibilityLabel={`도나 알림: ${title}. 눌러서 열기`}
            onPress={() => {
              // 알림을 누르면 그 카드를 맨 앞에 두고 지금 할 일(07-3)을 연다.
              devFlags.write({ card: card.id });
              goTask(card.id);
            }}
            className="mt-10 w-full gap-1 rounded-2xl bg-surface px-4 py-3.5 active:opacity-90"
          >
            <View className="flex-row items-center gap-2">
              <Image source={DONNA_IMG["b3-2"]} style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: tokens.colors["brand-soft"] }} />
              <Text className="flex-1 text-small text-ink">도나</Text>
              <Text className="text-small text-ink-2">지금</Text>
            </View>
            <Text className="text-body font-bold text-ink">{title}</Text>
            <Text className="text-small text-ink-2">{card.donna.text.replace(/\n/g, " ")}. 눌러서 확인해요</Text>
          </Pressable>
        ) : (
          <Text className="mt-10 text-body text-brand-soft">{data ? "지금은 도나 알림이 없어요" : ""}</Text>
        )}
        <View className="flex-1" />
        <Text className="mb-10 text-small text-brand-soft">알림을 누르면 도나가 열려요</Text>
      </View>
    </SafeAreaView>
  );
}
