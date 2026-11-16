// 알바생 앱 부품: 머리(사장님 앱과 같은 틀), 출퇴근 줄, 화면 틀, 입력 칸, 큰 버튼.
import { ReactNode, useEffect, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api, media } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { colors, radius, space } from '@/theme/tokens';

import { Txt } from './Txt';

type StoreHead = { name: string; logo_url: string | null; date_label: string };
let storeCache: StoreHead | null = null;

/** 가게 이름과 로고, 날짜. 알바생은 가게 주소로 들어오므로 가게는 처음부터 안다. */
export function useStoreHead() {
  const [head, setHead] = useState<StoreHead | null>(storeCache);
  useEffect(() => {
    if (storeCache) return;
    api
      .home()
      .then((h) => {
        storeCache = { name: h.store.name, logo_url: h.store.logo_url, date_label: h.date_label };
        setHead(storeCache);
      })
      .catch(() => {});
  }, []);
  return head;
}

/** 머리: 가게 로고와 이름, 그 아래 날짜, 오른쪽에 내 이름 꼬리표 (사장님 앱의 소리 버튼 자리). */
export function StaffHeader({ store, me }: { store: StoreHead | null; me?: string }) {
  const { scale } = useLayout();
  const box = Math.round(48 * scale);
  const logo = media(store?.logo_url);
  return (
    <View style={styles.head}>
      <View style={[styles.logo, { width: box, height: box }]}>
        {logo ? <Image source={{ uri: logo }} style={{ width: box, height: box }} /> : null}
      </View>
      <View style={{ flex: 1 }}>
        <Txt variant="title" numberOfLines={1}>
          {store?.name ?? ' '}
        </Txt>
        <Txt variant="label" color="ink2">
          {store?.date_label ?? ' '}
        </Txt>
      </View>
      {me ? (
        <View style={styles.me}>
          <Txt variant="label" color="brand">
            {me}
          </Txt>
        </View>
      ) : null}
    </View>
  );
}

/** 출퇴근 줄: 사장님 앱의 가게 상태 줄 자리. 출근은 그날 처음 화면을 연 시각이다. */
export function AttendanceStrip({ state, label, detail, onCheckout }: { state: 'in' | 'out'; label: string; detail: string; onCheckout: () => void }) {
  return (
    <View style={styles.strip}>
      <View style={[styles.dot, state === 'in' ? { backgroundColor: colors.brand } : { borderWidth: 2, borderColor: colors.ink3 }]} />
      <Txt variant="label" color={state === 'in' ? 'brand' : 'ink'} style={{ fontFamily: 'NotoSansKR_700Bold' }}>
        {label}
      </Txt>
      <Txt variant="label" color="ink2" style={{ flex: 1 }} numberOfLines={1}>
        {detail}
      </Txt>
      {state === 'in' ? (
        <Pressable onPress={onCheckout} accessibilityRole="button" style={styles.checkout}>
          <Txt variant="label" color="brand" style={{ fontFamily: 'NotoSansKR_700Bold' }}>
            퇴근하기
          </Txt>
        </Pressable>
      ) : null}
    </View>
  );
}

/** 알바생 화면의 틀: 위에서부터 쌓고, 큰 버튼은 아래에 붙는다. */
export function StaffFrame({ children, bottom }: { children: ReactNode; bottom?: ReactNode }) {
  const insets = useSafeAreaInsets();
  const { margin } = useLayout();
  return (
    <View style={{ flex: 1, backgroundColor: colors.paper }}>
      <ScrollView contentContainerStyle={{ paddingTop: Math.max(insets.top, space.s16) + space.s8, paddingHorizontal: margin, paddingBottom: space.s24, alignItems: 'center' }}>
        <View style={{ width: '100%', maxWidth: 600, gap: space.s16 }}>{children}</View>
      </ScrollView>
      {bottom ? (
        <View style={{ paddingHorizontal: margin, paddingBottom: Math.max(insets.bottom, space.s16) + space.s8, alignItems: 'center' }}>
          <View style={{ width: '100%', maxWidth: 600, gap: space.s8 }}>{bottom}</View>
        </View>
      ) : null}
    </View>
  );
}

export function BigButton({ label, onPress, disabled }: { label: string; onPress: () => void; disabled?: boolean }) {
  const { scale } = useLayout();
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      style={({ pressed }) => [styles.big, { height: Math.round(52 * scale), opacity: disabled ? 0.4 : pressed ? 0.85 : 1 }]}
    >
      <Txt variant="button" color="brandInk">
        {label}
      </Txt>
    </Pressable>
  );
}

export function Field({ label, value, onChange, secure, hint }: { label: string; value: string; onChange: (v: string) => void; secure?: boolean; hint?: string }) {
  const [focus, setFocus] = useState(false);
  const { type } = useLayout();
  return (
    <View style={{ gap: space.s4 }}>
      <Txt variant="label" color="ink2">
        {label}
      </Txt>
      <TextInput
        value={value}
        onChangeText={onChange}
        secureTextEntry={secure}
        autoCapitalize="none"
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={[styles.input, type.bodyStrong, { color: colors.ink }, focus && { borderColor: colors.brand, borderWidth: 2 }]}
      />
      {hint ? (
        <Txt variant="label" color="ink2">
          {hint}
        </Txt>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', gap: space.s12 },
  logo: { borderRadius: radius.tile, borderWidth: 1, borderColor: colors.line, overflow: 'hidden', backgroundColor: colors.surface },
  me: { paddingVertical: space.s4, paddingHorizontal: space.s12, borderRadius: radius.pill, backgroundColor: colors.brandSoft },
  strip: { flexDirection: 'row', alignItems: 'center', gap: space.s8, paddingVertical: 4, paddingLeft: space.s16, paddingRight: 4, borderRadius: radius.tile, backgroundColor: colors.brandSoft },
  dot: { width: 10, height: 10, borderRadius: 5 },
  checkout: { height: 44, paddingHorizontal: 14, borderRadius: 10, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  big: { borderRadius: radius.button, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  input: { height: 52, borderRadius: radius.tile, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface, paddingHorizontal: space.s16 },
});
