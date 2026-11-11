// 아래 탭이 없는 화면(답글, 점검, 포스터, 처음 쓰는 날)이 같이 쓰는 부품.
import type { ReactNode } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { SafeAreaView } from "react-native-safe-area-context";
import { Icon, type IconName } from "@/components/icons/Icon";
import type { Donna } from "@/lib/cards";
import { PLATFORM_KO } from "@/lib/labels";
import tokens from "@/theme/tokens.json";
import type { Review } from "@/types/contract";
import { DonnaImage, PhotoBox, ProgressSteps, Stars } from "./parts";
import { back, go } from "./nav";

const C = tokens.colors;

/** 뒤로 버튼 + 제목 (05-5 "리뷰 답글"). 처음 쓰는 날 화면은 제목 대신 진행 막대를 둔다. footer는 화면 아래에 붙는다. */
export function SubPage({
  title,
  backHref,
  onBack,
  progress,
  children,
  footer,
  scroll = true,
}: {
  title?: string;
  backHref?: string;
  onBack?: () => void;
  progress?: { total: number; done: number };
  children: ReactNode;
  footer?: ReactNode;
  scroll?: boolean;
}) {
  const body = <View className="flex-1 pt-3">{children}</View>;
  return (
    <SafeAreaView edges={["top", "bottom"]} style={{ flex: 1, backgroundColor: C.paper }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View className="h-11 flex-row items-center gap-2 px-6 mt-3">
          <Pressable
            testID="back"
            accessibilityRole="button"
            accessibilityLabel="뒤로"
            onPress={() => (onBack ? onBack() : backHref ? go(backHref) : back())}
            className="-ml-2.5 h-11 w-11 items-center justify-center rounded-full active:bg-brand-soft"
          >
            <Icon name="chevL" size={26} />
          </Pressable>
          {title ? (
            <Text className="text-title text-ink" accessibilityRole="header">
              {title}
            </Text>
          ) : null}
          {progress && (
            <View className="flex-1 pr-1">
              <ProgressSteps total={progress.total} done={progress.done} label={`처음 설정 ${progress.total}단계 중 ${progress.done}단계`} />
            </View>
          )}
        </View>
        {scroll ? (
          <ScrollView className="flex-1" contentContainerStyle={{ flexGrow: 1, paddingHorizontal: 24, paddingBottom: 12 }} keyboardShouldPersistTaps="handled">
            {body}
          </ScrollView>
        ) : (
          <View className="flex-1 px-6">{body}</View>
        )}
        {footer ? <View className="gap-2 px-6 pb-5 pt-3">{footer}</View> : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

/** 06 A2: 손님 리뷰 말풍선 (왼쪽, 왼쪽 위 모서리만 4). onCard면 카드 안이라 종이색, 아니면 흰 바탕 + 테두리.
 *  lines를 주면 그 줄 수까지만 보이고 끝이 "…"이 된다 (카드 2줄, 답글 화면 6줄). */
export function CustomerBubble({ text, onCard, lines }: { text: string; onCard?: boolean; lines?: number }) {
  return (
    <View
      className={`self-start px-4 py-3 ${onCard ? "bg-paper" : "border border-line bg-surface"}`}
      style={{ borderTopLeftRadius: 4, borderTopRightRadius: 18, borderBottomLeftRadius: 18, borderBottomRightRadius: 18, maxWidth: "100%" }}
    >
      <Text className="text-body text-ink-2" numberOfLines={lines}>
        {text}
      </Text>
    </View>
  );
}

/** 별점, 플랫폼, 리뷰 말풍선, 사진 (05-5 위쪽, 06-39r) */
export function ReviewBox({ review, showPlatform = true, lines, onPhoto }: { review: Review; showPlatform?: boolean; lines?: number; onPhoto?: (i: number) => void }) {
  const photos = review.photos ?? [];
  return (
    <View className="gap-2">
      <Stars rating={review.rating} suffix={showPlatform ? PLATFORM_KO[review.platform] : undefined} />
      <CustomerBubble text={review.text} lines={lines} />
      {photos.length > 0 && (
        <View className="flex-row gap-2">
          {photos.slice(0, 3).map((p, i) => (
            <Pressable key={p + i} accessibilityRole="imagebutton" accessibilityLabel={`손님 사진 ${i + 1}, 눌러서 크게 보기`} onPress={() => onPhoto?.(i)}>
              <PhotoBox uri={p} size={64} />
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

/** 06 A2: 도나가 써 둔 답글 (오른쪽 말풍선, 도나 얼굴은 오른쪽) */
export function DraftBubble({ img = "b3-2", text, busy, onCard }: { img?: Donna; text: string; busy?: boolean; onCard?: boolean }) {
  return (
    <View className="flex-row items-start justify-end gap-3">
      <View
        className="flex-1 bg-brand-soft px-4 py-3.5"
        style={{ borderTopLeftRadius: 18, borderTopRightRadius: 4, borderBottomLeftRadius: 18, borderBottomRightRadius: 18, opacity: busy ? 0.6 : 1 }}
        accessibilityState={{ busy }}
      >
        <Text className="text-body text-ink">{text}</Text>
      </View>
      <View className={onCard ? "mt-0.5" : "mt-1"}>
        <DonnaImage img={img} size={48} />
      </View>
    </View>
  );
}

/** 작은 안내 한 줄 (방패, 시계 아이콘) */
export function Note({ icon, children, center }: { icon: IconName; children: ReactNode; center?: boolean }) {
  return (
    <View className={`flex-row items-center gap-2 ${center ? "justify-center" : ""}`}>
      <Icon name={icon} size={20} color={icon === "shield" ? C.done : C["ink-2"]} />
      <Text className={`text-small text-ink-2 ${center ? "text-center" : ""}`}>{children}</Text>
    </View>
  );
}

/** 켜고 끄는 스위치 (05-20, 05-55, 05-58, 06-2i) */
export function Toggle({ checked, onChange, label, testID }: { checked: boolean; onChange: (v: boolean) => void; label: string; testID?: string }) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="switch"
      accessibilityState={{ checked }}
      accessibilityLabel={label}
      // 보이는 크기는 56 × 32, 누르는 영역은 위아래로 넓혀 44 이상
      hitSlop={{ top: 8, bottom: 8, left: 6, right: 6 }}
      onPress={() => onChange(!checked)}
      className={`h-8 w-14 rounded-full border ${checked ? "border-brand bg-brand" : "border-ink-3 bg-line"}`}
    >
      <View className={`absolute top-[3px] h-6 w-6 rounded-full ${checked ? "left-[27px] bg-brand-ink" : "left-[3px] bg-white"}`} />
    </Pressable>
  );
}

/** 목록 한 줄 (설정, 같이 하면 좋은 일) */
export function ListRow({
  icon,
  title,
  sub,
  right,
  href,
  onPress,
  testID,
}: {
  icon: IconName;
  title: string;
  sub?: string;
  right?: ReactNode;
  href?: string;
  onPress?: () => void;
  testID?: string;
}) {
  const inner = (
    <>
      <Icon name={icon} size={26} color={C["ink-2"]} />
      <View className="flex-1">
        <Text className="text-body text-ink">{title}</Text>
        {sub ? <Text className="text-small text-ink-2">{sub}</Text> : null}
      </View>
      {right}
      {href || onPress ? <Icon name="chevR" size={20} color={C["ink-2"]} /> : null}
    </>
  );
  const cls = "min-h-14 flex-row items-center gap-3 border-b border-line py-3";
  if (href || onPress)
    return (
      <Pressable
        testID={testID}
        accessibilityRole="button"
        onPress={() => {
          onPress?.();
          if (href) go(href);
        }}
        className={`${cls} active:bg-brand-soft`}
      >
        {inner}
      </Pressable>
    );
  return <View className={cls}>{inner}</View>;
}

/** 가운데 큰 그림 + 제목 + 설명 (05-52, 05-55, 05-57, 05-66) */
export function CenterMessage({ img, icon, title, sub, children }: { img?: Donna; icon?: IconName; title: string; sub?: string; children?: ReactNode }) {
  return (
    <View className="flex-1 items-center justify-center">
      {img ? <DonnaImage img={img} size={200} /> : null}
      {icon ? (
        <View className="h-24 w-24 items-center justify-center rounded-full bg-brand-soft">
          <Icon name={icon} size={48} color={C.brand} />
        </View>
      ) : null}
      <Text className="mt-4 text-center text-display text-ink">{title}</Text>
      {sub ? <Text className="mt-2 text-center text-body text-ink-2">{sub}</Text> : null}
      {children}
    </View>
  );
}

/** 목업(나중에 실제 API) 동작이 실패했을 때 화면 아래에 보여 주는 안내 (05-5f 모양). 쓴 내용은 그대로 둔다. */
export function FailNote({ title, sub = "인터넷이 끊겼어요.\n다시 눌러 주세요" }: { title: string; sub?: string }) {
  return (
    <View accessibilityRole="alert" className="mt-6 flex-row items-start gap-3 rounded-2xl bg-urgent-soft px-4 py-3.5">
      <Icon name="wifiOff" size={26} color={C.urgent} />
      <View className="flex-1">
        <Text className="text-body font-bold text-urgent">{title}</Text>
        <Text className="text-small text-ink-2">{sub}</Text>
      </View>
    </View>
  );
}
