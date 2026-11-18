// 버튼, 스위치, 시작 화면들의 틀, 서버에서 한 번 읽어 오는 훅.
import { ReactNode, useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useLayout } from '@/lib/layout';
import { colors, radius, space } from '@/theme/tokens';

import { Icon } from './Icon';
import { NaverLogo } from './startArt';
import { Txt } from './Txt';

/** 화면의 주 버튼. 높이 56, 둥글기 14 (Figma 버튼). naver: 네이버 로그인 가이드대로 초록 바탕에 흰 공식 로고와 흰 글자.
 *  chevron: 다음 화면으로 넘어가는 버튼은 글 뒤에 > (Figma 10-s1b). disabled: 흐리게 두고 누르지 않는다 */
export function Button({
  label, onPress, kind = 'primary', left, chevron, disabled,
}: { label: string; onPress: () => void; kind?: 'primary' | 'outline' | 'naver'; left?: ReactNode; chevron?: boolean; disabled?: boolean }) {
  const { scale } = useLayout();
  const bg = kind === 'primary' ? colors.brand : kind === 'naver' ? colors.naver : colors.surface;
  const ink = kind === 'outline' ? colors.brand : kind === 'naver' ? '#FFFFFF' : colors.brandInk;
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      style={({ pressed }) => [
        styles.button,
        { height: Math.round(56 * scale), backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
        kind === 'outline' && { borderWidth: 1.5, borderColor: colors.brand },
        kind === 'naver' && { gap: 10 },
        chevron && { gap: 6 },
      ]}
    >
      {kind === 'naver' && !left ? <NaverLogo size={16} /> : left}
      <Txt variant="button" style={{ color: ink }}>
        {label}
      </Txt>
      {chevron ? <Icon name="chevronRight" size={20} color={kind === 'outline' ? 'brand' : 'brandInk'} /> : null}
    </Pressable>
  );
}

/** 글자만 있는 작은 버튼. 손이 닿는 높이는 44. */
export function LinkButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={styles.link}>
      <Txt variant="label" color="ink2">
        {label}
      </Txt>
    </Pressable>
  );
}

export function Switch({ on, onChange, label }: { on: boolean; onChange: (next: boolean) => void; label: string }) {
  return (
    <Pressable
      onPress={() => onChange(!on)}
      accessibilityRole="switch"
      accessibilityState={{ checked: on }}
      accessibilityLabel={label}
      hitSlop={8}
      style={[styles.switch, { backgroundColor: on ? colors.brand : colors.line, alignItems: on ? 'flex-end' : 'flex-start' }]}
    >
      <View style={styles.knob} />
    </Pressable>
  );
}

/** 시작, 로그인, 마이크 화면의 틀. 내용은 가운데 한 줄기, 버튼은 아래에 붙는다. */
export function StartFrame({ top, children, bottom }: { top?: ReactNode; children: ReactNode; bottom: ReactNode }) {
  const { margin, tablet } = useLayout();
  const insets = useSafeAreaInsets();
  const max = tablet ? 520 : 440;
  return (
    <View style={{ flex: 1, backgroundColor: colors.paper, paddingTop: insets.top, paddingBottom: Math.max(insets.bottom, space.s24) }}>
      <View style={{ minHeight: 44, paddingHorizontal: margin - 10, justifyContent: 'center' }}>{top}</View>
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: margin, paddingVertical: space.s16 }} showsVerticalScrollIndicator={false}>
        <View style={{ width: '100%', maxWidth: max, alignItems: 'center' }}>{children}</View>
      </ScrollView>
      <View style={{ paddingHorizontal: margin, alignItems: 'center' }}>
        <View style={{ width: '100%', maxWidth: max, gap: space.s8 }}>{bottom}</View>
      </View>
    </View>
  );
}

/** 둘 가운데 하나를 고르는 칸 (이번 주 / 이번 달). 손이 닿는 높이는 44. */
export function Segmented<T extends string>({ options, value, onChange }: { options: { key: T; label: string }[]; value: T; onChange: (key: T) => void }) {
  return (
    <View style={styles.segmented} accessibilityRole="tablist">
      {options.map((o) => {
        const on = o.key === value;
        return (
          <Pressable
            key={o.key}
            onPress={() => onChange(o.key)}
            accessibilityRole="tab"
            accessibilityState={{ selected: on }}
            style={[styles.segment, on && { backgroundColor: colors.brand }]}
          >
            <Txt variant="label" color={on ? 'brandInk' : 'ink2'}>
              {o.label}
            </Txt>
          </Pressable>
        );
      })}
    </View>
  );
}

/** 태블릿 가로에서는 두 칸으로 나란히, 그보다 좁으면 위아래로 쌓는다. */
export function Columns({ left, right }: { left: ReactNode; right: ReactNode }) {
  const { wide } = useLayout();
  if (!wide) {
    return (
      <>
        {left}
        {right}
      </>
    );
  }
  return (
    <View style={{ flexDirection: 'row', gap: space.s24, alignItems: 'flex-start' }}>
      <View style={{ flex: 1, gap: space.s16 }}>{left}</View>
      <View style={{ flex: 1, gap: space.s16 }}>{right}</View>
    </View>
  );
}

/** 작은 제목 아래에 카드를 묶는다. 제목과 카드 사이는 8. */
export function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <View style={{ gap: space.s8 }}>
      <Txt variant="small" color="ink3">
        {label}
      </Txt>
      {children}
    </View>
  );
}

/** 탭 화면이 열릴 때 서버에서 한 번 읽어 온다. */
export function useLoad<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);
  const reload = useCallback(() => {
    setFailed(false);
    load()
      .then(setData)
      .catch(() => setFailed(true));
  }, [load]);
  useEffect(reload, [reload]);
  return { data, failed, reload, setData };
}

const styles = StyleSheet.create({
  button: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.s8, borderRadius: radius.button, paddingHorizontal: space.s16 },
  link: { minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.s16 },
  segmented: { flexDirection: 'row', gap: space.s4, padding: space.s4, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line },
  segment: { flex: 1, height: 36, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
  switch: { width: 52, height: 32, borderRadius: 16, padding: 3, justifyContent: 'center' },
  knob: { width: 26, height: 26, borderRadius: 13, backgroundColor: colors.surface },
});
