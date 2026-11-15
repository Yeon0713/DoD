// AI 포스터를 그리는 동안 보이는 화면. 그림 하나에 50초 안팎(길면 2분) 걸린다.
// 도나가 천천히 흔들리고, 걸린 시간으로 단계를 차례로 채운다 (서버가 단계를 알려 주지 않아 시간으로 짐작한다. 끝은 서버가 다 됐다고 할 때만).
import { useEffect, useState } from "react";
import { Animated, Easing, Platform, View } from "react-native";
import { Icon } from "@/components/icons/Icon";
import { DonnaImage } from "@/components/ui/parts";
import { Text } from "@/components/ui/Text";

const EXPECTED = 60; // 보통 걸리는 초
const STAGES: { label: string; from: number }[] = [
  { label: "고른 사진과 로고를 살펴보고 있어요", from: 0 },
  { label: "문구 넣을 자리를 잡고 있어요", from: 6 },
  { label: "포스터를 그리고 있어요", from: 15 },
  { label: "인스타 스토리 크기로 맞추고 있어요", from: 50 },
];

/** 서버가 알려 준 초에서 1초씩 센다 (3초마다 묻는 사이에도 숫자가 오르게) */
function useSeconds(serverSeconds: number) {
  const [base] = useState(serverSeconds);
  const [ticks, setTicks] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTicks((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return Math.max(serverSeconds, base + ticks);
}

function Bobbing({ children }: { children: React.ReactNode }) {
  const [v] = useState(() => new Animated.Value(0));
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(v, { toValue: 1, duration: 900, easing: Easing.inOut(Easing.quad), useNativeDriver: Platform.OS !== "web" }),
        Animated.timing(v, { toValue: 0, duration: 900, easing: Easing.inOut(Easing.quad), useNativeDriver: Platform.OS !== "web" }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [v]);
  const translateY = v.interpolate({ inputRange: [0, 1], outputRange: [0, -10] });
  const rotate = v.interpolate({ inputRange: [0, 1], outputRange: ["-3deg", "3deg"] });
  return <Animated.View style={{ transform: [{ translateY }, { rotate }] }}>{children}</Animated.View>;
}

export function PosterMaking({ seconds: serverSeconds, headline }: { seconds: number; headline: string }) {
  const seconds = useSeconds(serverSeconds);
  // 끝나기 전에는 95%를 넘기지 않는다 (예상보다 오래 걸려도 다 된 것처럼 보이지 않게)
  const progress = Math.min(0.95, seconds / EXPECTED);
  const current = STAGES.reduce((at, s, i) => (seconds >= s.from ? i : at), 0);
  const long = seconds > 90;
  return (
    <View className="flex-1 items-center pt-6" accessibilityRole="progressbar" accessibilityLabel="포스터를 그리고 있어요" accessibilityValue={{ min: 0, max: 100, now: Math.round(progress * 100) }}>
      <Bobbing>
        <DonnaImage img="b3-2" size={150} />
      </Bobbing>
      <Text className="mt-3 text-center text-title text-ink">{"도나가 포스터를\n그리고 있어요"}</Text>
      {headline ? (
        <View className="mt-3 rounded-full bg-brand-soft px-4 py-1.5">
          <Text className="text-small font-bold text-brand" numberOfLines={1}>{`"${headline.replace(/\n/g, " ")}"`}</Text>
        </View>
      ) : null}

      <View className="mt-6 w-full">
        <View className="h-3 w-full overflow-hidden rounded-full bg-line">
          <View testID="poster-progress" className="h-full rounded-full bg-brand" style={{ width: `${Math.round(progress * 100)}%` }} />
        </View>
        <View className="mt-1.5 flex-row justify-between">
          <Text testID="poster-seconds" className="text-small text-ink-2">{`${seconds}초째`}</Text>
          <Text className="text-small text-ink-2">{long ? "조금만 더 기다려 주세요" : "1분쯤 걸려요"}</Text>
        </View>
      </View>

      <View className="mt-5 w-full gap-3 rounded-2xl border border-line bg-surface px-4 py-4">
        {STAGES.map((s, i) => {
          const done = i < current;
          const now = i === current;
          return (
            <View key={s.label} className="flex-row items-center gap-3" accessibilityState={{ selected: now }}>
              <View className={`h-6 w-6 items-center justify-center rounded-full ${done ? "bg-done" : now ? "bg-brand" : "border-2 border-line"}`}>
                {done ? <Icon name="check" size={14} color="#fff" /> : now ? <View className="h-2 w-2 rounded-full bg-brand-ink" /> : null}
              </View>
              <Text className={`flex-1 text-body ${done ? "text-ink-2" : now ? "font-bold text-ink" : "text-ink-3"}`}>{s.label}</Text>
            </View>
          );
        })}
      </View>
      <Text className="mt-4 text-center text-small text-ink-2">다른 화면에 다녀와도 계속 그려요</Text>
    </View>
  );
}
