// 설정 화면들의 부품 (Figma v0.2.1 G-05 ~ G-08).
// 갤럭시 설정 앱처럼 묶음마다 작은 이름과 둥근 카드, 카드 안에는 줄(아이콘, 이름, 설명, 오른쪽 값, >).
import { useRouter } from 'expo-router';
import { ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon, IconName } from '@/components/Icon';
import { Txt } from '@/components/Txt';
import { Settings } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { colors, radius, space } from '@/theme/tokens';

/** 설정 줄의 '브리핑 알림' 설명. 기본(문 열기 1시간 전)인지, 고른 시각이 문 열기 몇 분 전인지. */
export function notifySub(n: Settings['briefing_notify']): string {
  if (!n.on) return '알림을 받지 않아요';
  if (n.is_default) return '문 열기 1시간 전'; // 휴대폰 한 줄 (값과 > 를 빼면 127px). '기본'은 G-08 에 적는다
  return n.options.find((o) => o.time === n.time)?.sub ?? '사장님이 고른 시각';
}

/** 묶음: 이름(15, ink-2) 아래 카드 하나. 줄 사이 선은 글이 시작하는 곳부터 (아이콘이 있으면 48 들여서). */
export function SettingsGroup({ title, children, inset = true }: { title?: string; children: ReactNode[] | ReactNode; inset?: boolean }) {
  const items = (Array.isArray(children) ? children : [children]).filter(Boolean);
  return (
    <View style={{ gap: space.s8 }}>
      {title ? (
        <Txt variant="label" color="ink2" accessibilityRole="header">
          {title}
        </Txt>
      ) : null}
      <View style={styles.card}>
        {items.map((child, i) => (
          <View key={i}>
            {i > 0 ? <View style={[styles.rule, { marginLeft: inset ? 48 : space.s12 }]} /> : null}
            {child}
          </View>
        ))}
      </View>
    </View>
  );
}

/** 설정 한 줄. onPress 가 있으면 줄 전체가 누르는 곳이고 오른쪽 끝에 > 가 붙는다. 높이는 56 이상. */
export function SettingsRow({
  icon,
  title,
  sub,
  value,
  right,
  onPress,
  dim,
}: {
  icon?: IconName;
  title: string;
  sub?: string | null;
  value?: string | null;
  right?: ReactNode;
  onPress?: () => void;
  dim?: boolean;
}) {
  const { scale } = useLayout();
  const body = (
    <View style={[styles.row, dim && { opacity: 0.45 }]}>
      {icon ? <Icon name={icon} size={Math.round(24 * scale)} color="ink2" /> : null}
      <View style={{ flex: 1 }}>
        <Txt variant="bodyStrong">{title}</Txt>
        {sub ? (
          <Txt variant="label" color="ink2">
            {sub}
          </Txt>
        ) : null}
      </View>
      {value ? (
        <Txt variant="label" color="ink2">
          {value}
        </Txt>
      ) : null}
      {right}
      {onPress ? <Icon name="chevronRight" size={Math.round(20 * scale)} color="ink2" /> : null}
    </View>
  );
  if (!onPress) return body;
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={[title, value].filter(Boolean).join(', ')} disabled={dim}>
      {({ pressed }) => <View style={pressed && { backgroundColor: colors.brandSoft, borderRadius: radius.row }}>{body}</View>}
    </Pressable>
  );
}

/** 설정 안쪽 화면의 틀 (이전 앱의 SubPage): 뒤로와 제목, 밀리는 내용, 아래에 붙는 버튼. 아래 탭은 없다. */
export function SubPage({ title, children, footer }: { title: string; children: ReactNode; footer?: ReactNode }) {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { margin, contentMax, scale } = useLayout();
  const back = () => (router.canGoBack() ? router.back() : router.replace('/settings'));
  const column = { width: '100%' as const, maxWidth: contentMax };
  return (
    <View style={{ flex: 1, backgroundColor: colors.home, paddingTop: insets.top }}>
      {/* 뒤로 아이콘(24)의 왼쪽 끝이 여백 선에 오도록 손이 닿는 칸(44)을 10만큼 밖으로 뺀다 */}
      <View style={[styles.head, { paddingHorizontal: margin - 10 }]}>
        <Pressable onPress={back} accessibilityRole="button" accessibilityLabel="뒤로" style={styles.back}>
          <Icon name="chevronLeft" size={Math.round(24 * scale)} color="ink" />
        </Pressable>
        <Txt variant="title" accessibilityRole="header">
          {title}
        </Txt>
      </View>
      <ScrollView contentContainerStyle={{ paddingHorizontal: margin, paddingTop: space.s8, paddingBottom: space.s16, alignItems: 'center' }}>
        <View style={[column, { gap: space.s16 }]}>{children}</View>
      </ScrollView>
      {footer ? (
        <View style={{ paddingHorizontal: margin, paddingTop: space.s16, paddingBottom: Math.max(insets.bottom, space.s24), alignItems: 'center' }}>
          <View style={[column, { gap: space.s8 }]}>{footer}</View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, padding: space.s4 },
  rule: { height: 1, backgroundColor: colors.line, marginRight: space.s12 },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.s12, padding: space.s12, minHeight: 56 },
  head: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: space.s4 },
  back: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
});
