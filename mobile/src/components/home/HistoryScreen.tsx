// 지난 기록 (홈 오른쪽 아래 "지난 기록"). 날짜마다 도나와 함께 한 일(답글, 점검, 메뉴판, 포스터) 수를 "오늘 함께 한 일" 카드 모양으로 보여 준다.
import { View } from "react-native";
import { DonnaImage } from "@/components/ui/parts";
import { back } from "@/components/ui/nav";
import { SubPage } from "@/components/ui/sub";
import { Text } from "@/components/ui/Text";
import { useCardState } from "@/lib/cardState";
import { doneByDate, useDonePlans } from "@/lib/doneHistory";
import { dateOnly, monthDay, weekdayName } from "@/lib/time";
import { DoneTiles } from "./HomeScreen";

export function HistoryScreen() {
  const cards = useCardState();
  const plans = useDonePlans();
  const days = doneByDate(cards, plans);
  return (
    <SubPage title="지난 기록" onBack={() => back("/")}>
      {days.length === 0 ? (
        <View testID="history-empty" className="flex-1 items-center justify-center gap-3">
          <DonnaImage img="b4-2" size={120} />
          <Text className="text-center text-title text-ink">아직 함께 한 일이 없어요</Text>
          <Text className="text-center text-body text-ink-2">도나가 준비한 것을 확인하면 여기에 날짜별로 모여요</Text>
        </View>
      ) : (
        <View testID="history-days" className="gap-3">
          {days.map((d) => {
            const day = dateOnly(d.date);
            return (
              <View key={d.date} testID={`history-${d.date}`} className="rounded-card bg-surface px-[22px] py-5">
                <DoneTiles counts={d.counts} title={`${monthDay(day)} ${weekdayName(day)} 함께 한 일`} />
              </View>
            );
          })}
        </View>
      )}
    </SubPage>
  );
}
