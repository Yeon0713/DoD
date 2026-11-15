// 포스터 할 일 화면의 도움말: 포스터가 어떻게 만들어지는지 그림으로 넘겨 보는 카드 4장 (사진 → 로고 → 문구 → 완성).
// 글로만 설명하면 읽지 않아서, 우리 화면을 줄여 그린 그림(PosterGuideArt.tsx) + 한 줄 제목으로 보여 준다. 모바일 폭(375) 기준.
// 카드 아래 ‹ › 버튼과 점으로도 좌우로 넘긴다 (웹에서는 손가락으로 넘기기 어렵다).
import { useRef, useState, type ComponentRef } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Icon } from "@/components/icons/Icon";
import { Text } from "@/components/ui/Text";
import tokens from "@/theme/tokens.json";
import { DoneArt, LogoArt, MentArt, PickPhotosArt } from "./PosterGuideArt";

const C = tokens.colors;

const STEPS = [
  { title: "사진을 골라 주세요", sub: "3장까지, 휴대폰 사진도 돼요", Art: PickPhotosArt },
  { title: "로고는 배경을 지워 넣어요", sub: "직접 올린 로고로 바꿀 수 있어요", Art: LogoArt },
  { title: "도나가 문구를 골라 드려요", sub: "그날 행사와 날씨를 보고 3개", Art: MentArt },
  { title: "1분이면 스토리 포스터 완성", sub: "가게 이름과 주소도 넣어요", Art: DoneArt },
];

export function PosterGuide() {
  const [width, setWidth] = useState(0);
  const [page, setPage] = useState(0);
  const scroller = useRef<ComponentRef<typeof ScrollView>>(null);
  // 버튼으로 넘길 때는 미끄러지는 동안 나오는 위치로 쪽 번호를 되돌리지 않는다 (도착하면 다시 손가락 넘김을 따른다)
  const target = useRef<number | null>(null);
  const go = (i: number) => {
    const next = Math.max(0, Math.min(STEPS.length - 1, i));
    target.current = next;
    setPage(next);
    scroller.current?.scrollTo({ x: next * width, animated: true });
  };
  const last = page === STEPS.length - 1;

  return (
    <View testID="poster-guide" onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
      {width > 0 ? (
        <ScrollView
          ref={scroller}
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          scrollEventThrottle={32}
          onScroll={(e) => {
            const x = e.nativeEvent.contentOffset.x;
            if (target.current !== null) {
              if (Math.abs(x - target.current * width) < 2) target.current = null;
              return;
            }
            const i = Math.round(x / width);
            if (i !== page && i >= 0 && i < STEPS.length) setPage(i);
          }}
        >
          {STEPS.map(({ title, sub, Art }, i) => (
            <View key={title} style={{ width }} accessibilityLabel={`${i + 1}번째, ${title}. ${sub}`}>
              <View className="overflow-hidden rounded-2xl bg-brand-soft">
                <View className="items-center pt-3">
                  <View style={{ width: "86%" }}>
                    <Art />
                  </View>
                </View>
                <View className="flex-row items-center gap-2 px-4 pb-3 pt-1.5">
                  <View className="h-6 min-w-6 items-center justify-center rounded-full bg-brand px-1.5">
                    <Text className="text-small font-bold text-brand-ink">{i + 1}</Text>
                  </View>
                  <View className="flex-1">
                    <Text className="text-body font-bold text-ink" numberOfLines={1}>
                      {title}
                    </Text>
                    <Text className="text-small text-ink-2" numberOfLines={1}>
                      {sub}
                    </Text>
                  </View>
                </View>
              </View>
            </View>
          ))}
        </ScrollView>
      ) : null}
      {/* 카드 아래: ‹ 이전 · 점 · 다음 › */}
      <View className="mt-2.5 flex-row items-center justify-between">
        <Pressable testID="poster-guide-prev" accessibilityRole="button" accessibilityLabel="이전" accessibilityState={{ disabled: page === 0 }} disabled={page === 0} hitSlop={8} onPress={() => go(page - 1)} className={`h-9 w-9 items-center justify-center rounded-full border border-brand bg-surface active:bg-brand-soft ${page === 0 ? "opacity-30" : ""}`}>
          <Icon name="chevL" size={18} color={C.brand} />
        </Pressable>
        <View className="flex-row gap-1.5" accessibilityRole="tablist">
          {STEPS.map((s, i) => (
            <Pressable key={s.title} accessibilityRole="tab" accessibilityState={{ selected: i === page }} accessibilityLabel={`${i + 1}번째 도움말`} hitSlop={6} onPress={() => go(i)}>
              <View className={`h-2 rounded-full ${i === page ? "w-5 bg-brand" : "w-2 bg-line"}`} />
            </Pressable>
          ))}
        </View>
        <Pressable testID="poster-guide-next" accessibilityRole="button" accessibilityLabel="다음" accessibilityState={{ disabled: last }} disabled={last} hitSlop={8} onPress={() => go(page + 1)} className={`h-9 w-9 items-center justify-center rounded-full bg-brand active:opacity-80 ${last ? "opacity-30" : ""}`}>
          <Icon name="chevR" size={18} color={C["brand-ink"]} />
        </Pressable>
      </View>
    </View>
  );
}
