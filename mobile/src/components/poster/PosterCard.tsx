// 포스터 한 장 (Figma 05-63 게시물 4:5, 300 × 375). 미리 보기 화면과 오늘 카드(06-31 큰 포스터)가 같이 쓴다.
// 그림 파일로 저장할 때는 이 화면을 그대로 찍는다 (react-native-view-shot).
// 아래 띠: 날짜, 큰 글자, 가게 이름과 주소. 오른쪽 아래는 가게 로고(있으면, 바탕을 지운 그림), 없으면 도나.
import { Image, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon, type IconName } from "@/components/icons/Icon";
import { DONNA_IMG } from "@/components/ui/donna";
import { LOGO_CHIP, THEME_STYLE, type Theme } from "@/lib/poster";
import tokens from "@/theme/tokens.json";

export type PosterProps = { photo?: string; menu: string; dateLine: string; icon: IconName; headline: string; store: string; theme: Theme; logo?: string; address?: string; image?: string };

export const POSTER_W = 300;
export const POSTER_H = 375;

export function PosterCard({ photo, menu, dateLine, icon, headline, store, theme, logo, address }: PosterProps) {
  const t = THEME_STYLE[theme];
  return (
    <View
      className="overflow-hidden rounded-2xl border border-line"
      style={{ width: POSTER_W, height: POSTER_H }}
      accessible
      accessibilityLabel={`포스터: ${headline.replace(/\n/g, " ")}`}
    >
      <View className="flex-1 items-center justify-center bg-brand-soft" style={{ minHeight: 170 }}>
        {photo ? (
          <Image source={{ uri: photo }} style={{ width: "100%", height: "100%" }} resizeMode="cover" accessibilityLabel={menu} />
        ) : (
          <View className="items-center gap-1">
            <Icon name="image" size={44} color={tokens.colors["ink-2"]} />
            <Text className="text-small text-ink-2">{menu} 사진</Text>
          </View>
        )}
      </View>
      {/* 글자가 세 줄이 되면 사진 칸이 줄어든다 (포스터 크기는 300 × 375 그대로) */}
      <View className="flex-row items-end justify-between gap-2 px-4 py-4" style={{ backgroundColor: t.canvasBg, minHeight: 150 }}>
        <View className="flex-1 gap-1">
          <View className="flex-row items-center gap-1">
            <Icon name={icon} size={16} color={t.canvasSub} />
            <Text className="text-small" style={{ color: t.canvasSub }}>
              {dateLine}
            </Text>
          </View>
          <Text className="text-title" style={{ color: t.canvasText }}>
            {headline}
          </Text>
          <Text className="text-small font-bold" style={{ color: t.canvasSub }} numberOfLines={1}>
            {store}
          </Text>
          {address ? (
            <Text style={{ color: t.canvasSub, fontSize: 11, lineHeight: 15 }} numberOfLines={2}>
              {address}
            </Text>
          ) : null}
        </View>
        {logo ? (
          // 바탕을 지운 로고. 어두운 띠에서는 밝은 둥근 판 위에 얹는다
          <View style={{ width: 62, height: 62, borderRadius: 12, padding: 4, backgroundColor: LOGO_CHIP[theme] ?? "transparent" }}>
            <Image testID="poster-logo" source={{ uri: logo }} style={{ width: "100%", height: "100%" }} resizeMode="contain" accessibilityLabel={`${store} 로고`} />
          </View>
        ) : (
          <Image source={DONNA_IMG["b3-0"]} style={{ width: 64, height: 64 }} />
        )}
      </View>
    </View>
  );
}

/** 줄인 포스터. 06-31 카드는 폭 210 (0.7배), 예전 썸네일은 132 (0.44배) */
export function PosterScaled({ width = 210, ...p }: PosterProps & { width?: number }) {
  // AI 포스터를 만들어 뒀으면 그 그림(인스타 스토리 9:16)을 그대로 보인다
  if (p.image) {
    return (
      <View style={{ width, height: (width * 16) / 9, overflow: "hidden" }} className="rounded-xl">
        <Image source={{ uri: p.image }} style={{ width: "100%", height: "100%" }} resizeMode="cover" accessibilityLabel={`포스터: ${p.headline.replace(/\n/g, " ")}`} />
      </View>
    );
  }
  const s = width / POSTER_W;
  return (
    <View style={{ width, height: POSTER_H * s, overflow: "hidden" }} className="rounded-xl">
      <View style={{ width: POSTER_W, height: POSTER_H, transform: [{ translateX: -(POSTER_W * (1 - s)) / 2 }, { translateY: -(POSTER_H * (1 - s)) / 2 }, { scale: s }] }}>
        <PosterCard {...p} />
      </View>
    </View>
  );
}
