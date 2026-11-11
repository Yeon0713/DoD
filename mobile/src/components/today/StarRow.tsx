// 별 다섯 개 + 옆 작은 글씨 ("2점, 배달의민족", "네이버"). 06-39 카드, 06-25 묶음 목록.
import { View } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon } from "@/components/icons/Icon";
import tokens from "@/theme/tokens.json";

export function StarRow({ rating, text, size = 22 }: { rating: number; text?: string; size?: number }) {
  return (
    <View className="flex-row items-center gap-0.5" accessible accessibilityLabel={`별점 ${rating}점${text ? `, ${text}` : ""}`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Icon key={i} name={i <= rating ? "starFill" : "star"} size={size} color={tokens.colors.brand} />
      ))}
      {text ? <Text className="ml-1.5 text-small text-ink-2">{text}</Text> : null}
    </View>
  );
}
