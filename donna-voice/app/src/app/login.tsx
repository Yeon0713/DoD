import { useRouter } from 'expo-router';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon } from '@/components/Icon';
import { Button } from '@/components/ui';
import { colors, space } from '@/theme/tokens';

// 시작 방법 고르기 (Figma 10 · 시안 v10 › 10-s2, 이전 앱 ChooseStartScreen).
// 위 줄에 뒤로(26). 위아래 여백이 같이 늘어나 가운데에 [도나 200, "어떻게 시작할까요?"] 와 [네이버, 휴대폰, 이미 쓰고 계세요? 로그인].
export default function ChooseStartScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      <View style={[styles.body, { paddingBottom: Math.max(insets.bottom, 28) }]}>
        <View style={styles.top}>
          <Pressable onPress={() => router.replace('/start')} accessibilityRole="button" accessibilityLabel="뒤로" hitSlop={9} style={styles.back}>
            <Icon name="chevronLeft" size={26} color="ink" />
          </Pressable>
        </View>
        <View style={{ flex: 1 }} />
        <View style={{ gap: space.s24, alignItems: 'center', width: '100%' }}>
          <View style={{ gap: space.s8, alignItems: 'center', width: '100%' }}>
            <Image source={require('@/assets/donna/b2-1.png')} style={{ width: 200, height: 200 }} resizeMode="contain" />
            <Text style={styles.display} accessibilityRole="header">
              어떻게 시작할까요?
            </Text>
          </View>
          <View style={{ gap: space.s8, alignSelf: 'stretch' }}>
            <Button kind="naver" label="네이버로 시작하기" onPress={() => router.push('/join/naver-login')} />
            <Button kind="outline" label="휴대폰 번호로 시작하기" onPress={() => router.push('/join/phone')} />
            <Pressable onPress={() => router.push('/join/login')} accessibilityRole="button" style={[styles.ask, { alignSelf: 'center' }]}>
              <Text style={styles.askText}>이미 쓰고 계세요?</Text>
              <Text style={[styles.askText, styles.askLink]}>로그인</Text>
            </Pressable>
          </View>
        </View>
        <View style={{ flex: 1 }} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.paper },
  body: { flex: 1, paddingHorizontal: space.s24 },
  top: { height: 44, justifyContent: 'center' },
  back: { width: 26, height: 26, alignItems: 'center', justifyContent: 'center' },
  display: { fontFamily: 'NotoSansKR_700Bold', fontSize: 28, lineHeight: 38, letterSpacing: -0.28, color: colors.ink, textAlign: 'center' },
  ask: { flexDirection: 'row', gap: 6, paddingHorizontal: space.s8, paddingVertical: 11 },
  askText: { fontFamily: 'NotoSansKR_500Medium', fontSize: 15, lineHeight: 22, letterSpacing: -0.15, color: colors.ink2 },
  askLink: { fontFamily: 'NotoSansKR_700Bold', color: colors.brand, textDecorationLine: 'underline' },
});
