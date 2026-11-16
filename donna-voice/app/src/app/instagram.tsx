import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon, IconName } from '@/components/Icon';
import { Txt } from '@/components/Txt';
import { api, media } from '@/lib/api';
import { bus } from '@/lib/bus';
import { useLayout } from '@/lib/layout';
import { colors, radius, space } from '@/theme/tokens';

// D-02. 도나 화면이 아니라 인스타가 보여 주는 허용 화면이다 (모양은 예시, 목업).
// 비밀번호는 여기서만 넣는다. 피드 올리기와 손님이 태그한 스토리 받기를 허락받는다.
const ASKS: { icon: IconName; text: string }[] = [
  { icon: 'user', text: '프로필과 게시물 보기' },
  { icon: 'image', text: '게시물 올리기' },
  { icon: 'message', text: '내 계정을 태그한 스토리 받기' },
];

export default function InstagramConsent() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { margin } = useLayout();
  const [busy, setBusy] = useState(false);
  const allow = async () => {
    setBusy(true);
    try {
      const r = await api.instagramConnect();
      router.back();
      setTimeout(() => bus.emit('instagram_connected', r.say), 300);
    } finally {
      setBusy(false);
    }
  };
  return (
    <View style={[styles.page, { paddingTop: Math.max(insets.top, space.s16), paddingHorizontal: margin, paddingBottom: Math.max(insets.bottom, space.s16) }]}>
      <View style={styles.address}>
        <Icon name="lock" size={14} color="ink2" />
        <Txt variant="label" color="ink2">
          instagram.com
        </Txt>
      </View>
      <View style={styles.body}>
        <View style={styles.apps}>
          <Image source={{ uri: media('/static/logos/s005.png') ?? undefined }} style={styles.avatar} />
          <Icon name="link" size={20} color="ink2" />
          <View style={[styles.avatar, { backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' }]}>
            <Txt variant="title" color="brandInk">
              D
            </Txt>
          </View>
        </View>
        <Txt variant="title" center>
          도나에 이 권한을 허용할까요?
        </Txt>
        <Txt variant="label" color="ink2" center>
          choongjang_namyang 계정으로 로그인됨
        </Txt>
        <View style={{ gap: space.s16, marginTop: space.s16 }}>
          {ASKS.map((a) => (
            <View key={a.text} style={styles.ask}>
              <Icon name={a.icon} size={22} color="ink" />
              <Txt variant="bodyStrong">{a.text}</Txt>
            </View>
          ))}
        </View>
      </View>
      <Pressable onPress={allow} disabled={busy} accessibilityRole="button" style={({ pressed }) => [styles.allow, { opacity: pressed || busy ? 0.8 : 1 }]}>
        <Txt variant="button" color="brandInk">
          허용
        </Txt>
      </Pressable>
      <Pressable onPress={() => router.back()} accessibilityRole="button" style={styles.cancel}>
        <Txt variant="label" color="ink2">
          취소
        </Txt>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: '#ffffff' },
  address: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.s4, height: 36, borderRadius: radius.tile, backgroundColor: '#efefef' },
  body: { flex: 1, paddingTop: space.s24, gap: space.s8 },
  apps: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.s12, marginBottom: space.s8 },
  avatar: { width: 56, height: 56, borderRadius: 28, overflow: 'hidden' },
  ask: { flexDirection: 'row', alignItems: 'center', gap: space.s12 },
  allow: { height: 56, borderRadius: radius.button, backgroundColor: '#2b1a0f', alignItems: 'center', justifyContent: 'center' },
  cancel: { height: 44, alignItems: 'center', justifyContent: 'center' },
});
