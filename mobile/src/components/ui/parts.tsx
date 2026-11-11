// 여러 화면이 같이 쓰는 작은 부품. 크기와 색은 Figma 05, 06 시안(docs/frontend_plan_v4.md 3장)을 따른다.
// 글자에는 늘 text-display / text-title / text-body / text-label / text-button / text-small 중 하나를 준다(폰트가 거기 들어 있다).
import { useEffect, useRef, type ReactNode } from "react";
import { Text } from "./Text";
import { Animated, Image, Pressable, View } from "react-native";
import { Icon, type IconName } from "@/components/icons/Icon";
import type { Donna, Tone } from "@/lib/cards";
import tokens from "@/theme/tokens.json";
import { DONNA_IMG } from "./donna";
import { go } from "./nav";

const C = tokens.colors;

export const TONE_COLOR: Record<Tone, { bg: string; fg: string }> = {
  urgent: { bg: C["urgent-soft"], fg: C.urgent },
  brand: { bg: C["brand-soft"], fg: C.brand },
  calm: { bg: C["calm-soft"], fg: C.calm },
  done: { bg: C["done-soft"], fg: C.done },
};

/** 카드 맨 위 띠. solid면 06 "긴급"처럼 진하게 칠하고 글자를 희게 한다. */
export function StatusPill({ tone, icon, children, solid }: { tone: Tone; icon: IconName; children: ReactNode; solid?: boolean }) {
  const t = TONE_COLOR[tone];
  const bg = solid ? t.fg : t.bg;
  const fg = solid ? C["brand-ink"] : t.fg;
  return (
    <View className="h-8 flex-row items-center gap-1.5 self-start rounded-full pl-2.5 pr-3" style={{ backgroundColor: bg }}>
      <Icon name={icon} size={18} color={fg} />
      <Text className={`text-label ${solid ? "font-bold" : ""}`} style={{ color: fg }}>
        {children}
      </Text>
    </View>
  );
}

export function Stars({ rating, suffix, size = 22 }: { rating: number; suffix?: string; size?: number }) {
  return (
    <View className="flex-row items-center gap-0.5" accessibilityLabel={`별점 ${rating}점`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Icon key={i} name={i <= rating ? "starFill" : "star"} size={size} color={C.busy} />
      ))}
      <Text className="ml-1.5 text-label text-ink-2">
        {rating}점{suffix ? `, ${suffix}` : ""}
      </Text>
    </View>
  );
}

export function DonnaImage({ img, size = 72 }: { img: Donna; size?: number }) {
  return <Image source={DONNA_IMG[img]} style={{ width: size, height: size }} resizeMode="contain" accessibilityIgnoresInvertColors />;
}

export function DonnaSays({ img, size = 72, children }: { img: Donna; size?: number; children: ReactNode }) {
  return (
    <View className="flex-row items-center gap-3">
      <DonnaImage img={img} size={size} />
      <Text className="flex-1 text-body font-medium text-ink">{children}</Text>
    </View>
  );
}

export function ProgressSteps({ total, done, label }: { total: number; done: number; label?: string }) {
  return (
    <View
      className="flex-row gap-1.5"
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: total, now: done }}
      accessibilityLabel={label ?? `오늘 할 일 ${total}개 중 ${done}개 끝냄`}
    >
      {total > 8 ? (
        // 칸이 많으면(목업 한 주 모아 보기) 칸을 나누지 않고 막대 하나로 채운다.
        <View className="h-1.5 flex-1 overflow-hidden rounded-[3px] bg-line">
          <View className="h-full rounded-[3px] bg-brand" style={{ width: `${Math.min(100, (done / total) * 100)}%` }} />
        </View>
      ) : (
        Array.from({ length: Math.max(total, 1) }, (_, i) => <View key={i} className={`h-1.5 flex-1 rounded-[3px] ${i < done ? "bg-brand" : "bg-line"}`} />)
      )}
    </View>
  );
}

/** 빠르게 두 번 눌러도 한 번만 실행한다 (답글이 두 번 올라가거나 화면이 두 번 열리지 않게). */
function useOnce(ms = 500) {
  const at = useRef(0);
  return (run: () => void) => {
    const now = Date.now();
    if (now - at.current < ms) return;
    at.current = now;
    run();
  };
}

type ButtonProps = { children: ReactNode; href?: string; onPress?: () => void; disabled?: boolean; testID?: string };

/** 화면마다 하나뿐인 주 버튼. 높이 56, 둥글기 14. 웹 검증 도구가 찾을 수 있게 testID 기본값은 "primary" */
export function PrimaryButton({ children, href, onPress, disabled, testID = "primary" }: ButtonProps) {
  const once = useOnce();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      disabled={disabled}
      onPress={() =>
        once(() => {
          onPress?.();
          if (href) go(href);
        })
      }
      className={`h-14 w-full items-center justify-center rounded-button bg-brand active:opacity-90 ${disabled ? "opacity-50" : ""}`}
    >
      <Text className="text-button text-brand-ink">{children}</Text>
    </Pressable>
  );
}

/** "나중에 할게요" 같은 보조 버튼. 높이 48, 테두리 없음. outline이면 "고쳐 쓰기"처럼 테두리가 있다. */
export function SecondaryButton({ children, href, onPress, outline, disabled, testID = "secondary" }: ButtonProps & { outline?: boolean }) {
  const once = useOnce();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      disabled={disabled}
      onPress={() =>
        once(() => {
          onPress?.();
          if (href) go(href);
        })
      }
      className={`w-full items-center justify-center rounded-button active:bg-brand-soft ${outline ? "h-14 border border-brand bg-surface" : "h-12"} ${disabled ? "opacity-50" : ""}`}
    >
      <Text className={outline ? "text-button text-brand" : "text-body font-medium text-ink-2"}>{children}</Text>
    </Pressable>
  );
}

/** 글자 링크 ("더 보기", "고치기") */
export function TextLink({ children, href, onPress, className = "" }: { children: ReactNode; href?: string; onPress?: () => void; className?: string }) {
  return (
    <Pressable
      accessibilityRole="link"
      hitSlop={10}
      onPress={() => {
        onPress?.();
        if (href) go(href);
      }}
      className={className}
    >
      <Text className="text-label font-bold text-brand underline">{children}</Text>
    </Pressable>
  );
}

/** 불러오는 중 뼈대 (05-8). 0.3초부터 보이고 밝기가 천천히 오르내린다. */
export function Bone({ className = "", style }: { className?: string; style?: object }) {
  const v = useRef(new Animated.Value(0.55)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(v, { toValue: 1, duration: 800, useNativeDriver: true }),
        Animated.timing(v, { toValue: 0.55, duration: 800, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [v]);
  return <Animated.View className={`rounded-lg bg-skeleton ${className}`} style={[{ opacity: v }, style]} />;
}

/** 빈 사진 칸 (실제 사진이 없을 때. 목업 사진 주소는 "placeholder:무엇") */
export function PhotoBox({ uri, label, size = 64, rounded = 12 }: { uri?: string | null; label?: string; size?: number; rounded?: number }) {
  if (uri && !uri.startsWith("placeholder:")) {
    return <Image source={{ uri }} style={{ width: size, height: size, borderRadius: rounded }} accessibilityLabel={label} />;
  }
  return (
    <View
      className="items-center justify-center bg-brand-soft"
      style={{ width: size, height: size, borderRadius: rounded }}
      accessibilityLabel={label ?? (uri ? uri.slice(12) : "사진")}
    >
      <Icon name="image" size={Math.max(18, Math.round(size * 0.36))} color={C["ink-2"]} />
    </View>
  );
}
