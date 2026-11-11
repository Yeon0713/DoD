// 끝낸 일 다시 보기 (Figma 07-4). 홈 "오늘 끝낸 일"에서 한 줄을 누르면 열린다.
// 끝낸 시각과 한 일, 그때 카드, 올린 답글을 보여 준다. 되돌리는 버튼은 두지 않는다.
import { useLocalSearchParams } from "expo-router";
import { View } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon } from "@/components/icons/Icon";
import { DraftBubble, SubPage } from "@/components/ui/sub";
import { TaskCard } from "@/components/task/TaskCard";
import { hhmm, weekdayName, ymd } from "@/lib/time";
import { useTodayCards } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";

const C = tokens.colors;

export function DoneScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data, view, store, now } = useTodayCards();
  const card = view?.cards.find((c) => c.id === id);
  const s = id ? store[id] : undefined;

  if (!card || s?.kind !== "done") {
    return (
      <SubPage title="끝낸 일" backHref="/">
        <View className="flex-1 items-center justify-center">
          <Text className="text-center text-body text-ink-2">{data ? "이 일은 오늘 끝낸 일에 없어요" : ""}</Text>
        </View>
      </SubPage>
    );
  }

  const when = s.at ? `${ymd(new Date(s.at)) === ymd(now) ? "오늘" : weekdayName(s.at)} ${hhmm(s.at)}에 ` : "";
  return (
    <SubPage title="끝낸 일">
      <View className="gap-4">
        <View testID="done-banner" className="flex-row items-center gap-2.5 rounded-2xl bg-done-soft px-3.5 py-3">
          <Icon name="check" size={22} color={C.done} />
          <Text className="flex-1 text-label text-done">{`${when}${s.note ?? "끝냈어요"}`}</Text>
        </View>
        <TaskCard card={card} finished />
        {s.reply ? (
          <View className="gap-2.5">
            <Text className="text-body font-bold text-ink">{s.note?.startsWith("인사") ? "보낸 인사" : "올린 답글"}</Text>
            <DraftBubble img="b3-2" text={s.reply} />
          </View>
        ) : null}
      </View>
    </SubPage>
  );
}
