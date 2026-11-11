// 오늘 화면의 할 일 카드 한 장 (Figma 06-4 할 일 카드). 내용은 lib/cards.ts가 만든다.
import { View } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon } from "@/components/icons/Icon";
import { PosterScaled } from "@/components/poster/PosterCard";
import { StatusPill, TextLink } from "@/components/ui/parts";
import type { CardBlock, CardView } from "@/lib/cards";
import tokens from "@/theme/tokens.json";
import { StarRow } from "./StarRow";

const C = tokens.colors;
const WEEK_ORDER = [1, 2, 3, 4, 5, 6, 0];
const WEEK_NAMES = ["일", "월", "화", "수", "목", "금", "토"];
/** 카드 말풍선 2줄에 들어가는 글자 수 어림값. 넘으면 "더 보기"를 단다. */
const TWO_LINES = 30;

/** 06-4, 06-39: 손님 리뷰 말풍선. 2줄까지 보이고, 길면 "더 보기", 사진이 있으면 "사진 N장" */
function ReviewBlock({ b }: { b: Extract<CardBlock, { type: "review" }> }) {
  const long = b.text.length > TWO_LINES;
  const photos = b.photos.length;
  return (
    <View className="gap-2">
      <StarRow rating={b.rating} text={b.meta} />
      <View
        className="bg-paper px-4 py-3"
        style={{ borderTopLeftRadius: 4, borderTopRightRadius: 18, borderBottomLeftRadius: 18, borderBottomRightRadius: 18 }}
      >
        <Text className="text-body text-ink-2" numberOfLines={2}>
          {b.text}
        </Text>
        {long || photos > 0 ? (
          <View className="mt-1.5 flex-row items-center">
            {long ? (
              <TextLink href={b.href} className="py-1">
                더 보기
              </TextLink>
            ) : null}
            <View className="flex-1" />
            {photos > 0 ? (
              <View className="flex-row items-center gap-1" accessible accessibilityLabel={`손님 사진 ${photos}장`}>
                <Icon name="image" size={20} color={C["ink-2"]} />
                <Text className="text-small text-ink-2">사진 {photos}장</Text>
              </View>
            ) : null}
          </View>
        ) : null}
      </View>
    </View>
  );
}

function Block({ b }: { b: CardBlock }) {
  switch (b.type) {
    case "stars":
      return <StarRow rating={b.rating} text={`${b.rating}점`} />;
    case "quote":
      return <Text className="text-body text-ink-2">“{b.text}”</Text>;
    case "text":
      return <Text className="text-body text-ink-2">{b.text}</Text>;
    case "review":
      return <ReviewBlock b={b} />;
    case "iconLine":
      return (
        <View className="flex-row items-center gap-2.5">
          <View className="flex-row gap-1">
            {b.icons.map((i, k) => (
              <Icon key={i + k} name={i} size={28} color={C.brand} />
            ))}
          </View>
          <Text className="flex-1 text-body font-medium text-ink">{b.text}</Text>
        </View>
      );
    case "iconRow":
      return (
        <View className="flex-row gap-2" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          {Array.from({ length: b.count }, (_, i) => (
            <Icon key={i} name={b.icon} size={28} color={C.brand} />
          ))}
        </View>
      );
    case "weekStrip":
      // 월~일 순서. day는 0=일요일
      return (
        <View className="flex-row gap-1.5" accessible accessibilityLabel={`매주 ${WEEK_NAMES[b.day]}요일`}>
          {WEEK_ORDER.map((d) => (
            <View key={d} className={`h-9 flex-1 items-center justify-center rounded-lg ${d === b.day ? "bg-brand" : "bg-paper"}`}>
              <Text className={`text-label ${d === b.day ? "font-bold text-brand-ink" : "text-ink-3"}`}>{WEEK_NAMES[d]}</Text>
            </View>
          ))}
        </View>
      );
    case "menuPreview":
      return (
        <View className="gap-1 rounded-button border border-line bg-paper p-3">
          <Text className="text-small text-ink-2">{b.header}</Text>
          {b.rows.map((r, i) => (
            <View key={r.name} className={`h-10 flex-row items-center gap-2.5 rounded-[10px] px-2.5 ${r.from ? "bg-brand-soft" : ""}`}>
              <Text className={`w-4 text-title ${r.from ? "text-brand" : "text-ink-3"}`}>{i + 1}</Text>
              <Text className={`flex-1 text-body ${r.from ? "font-medium text-ink" : "text-ink-2"}`} numberOfLines={1}>
                {r.name}
              </Text>
              {r.from ? (
                <View className="flex-row items-center gap-1">
                  <Icon name="arrowUp" size={18} color={C.brand} />
                  <Text className="text-small text-brand">{r.from}번째에서</Text>
                </View>
              ) : null}
            </View>
          ))}
        </View>
      );
    case "bars":
      return (
        <View className="gap-2">
          {b.rows.map((r) => (
            <View key={r.label} className="gap-1.5">
              <View className="flex-row items-baseline justify-between">
                <Text className="text-label text-ink-2">{r.label}</Text>
                <Text className={`text-body font-bold ${r.accent ? "text-calm" : "text-ink-2"}`}>{r.value}</Text>
              </View>
              <View className="h-3 overflow-hidden rounded-full bg-line">
                <View className={`h-full rounded-full ${r.accent ? "bg-calm" : "bg-ink-3"}`} style={{ width: `${Math.max(3, Math.min(100, r.percent))}%` }} />
              </View>
            </View>
          ))}
        </View>
      );
    case "poster":
      // 06-31: 포스터가 주인공. 카드 가운데에 폭 210으로 크게
      return (
        <View className="items-center">
          <PosterScaled width={210} {...b.poster} />
        </View>
      );
  }
}

/** finished: 끝낸 일 다시 보기(07-4). 이미 끝난 일이 급해 보이지 않게 빨간 테두리를 뺀다. */
export function TaskCard({ card, finished }: { card: CardView; finished?: boolean }) {
  return (
    <View
      testID="task-card"
      className={`gap-3.5 rounded-card bg-surface px-5 pt-5 pb-[22px] ${card.urgent && !finished ? "border-2 border-urgent" : "border border-line"}`}
    >
      {card.pill ? (
        <StatusPill tone={card.tone} icon={card.pill.icon} solid={card.urgent}>
          {card.pill.text}
        </StatusPill>
      ) : null}
      <View className="gap-1">
        <View className="flex-row items-center gap-2">
          {card.titleIcon ? <Icon name={card.titleIcon} size={28} color={C.brand} /> : null}
          <Text className="flex-1 text-title text-ink" accessibilityRole="header">
            {card.title}
          </Text>
        </View>
        {card.sub ? <Text className="text-label text-ink-2">{card.sub}</Text> : null}
      </View>
      {card.blocks.map((b, i) => (
        <Block key={i} b={b} />
      ))}
    </View>
  );
}
