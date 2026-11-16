import { Redirect, useRouter } from 'expo-router';
import { Image, StyleSheet, View } from 'react-native';

import { Icon, IconName } from '@/components/Icon';
import { Txt } from '@/components/Txt';
import { Button, StartFrame } from '@/components/ui';
import { useLayout } from '@/lib/layout';
import { useSession } from '@/lib/session';
import { colors, radius, space } from '@/theme/tokens';

// E-01 시작. 도나가 해 주는 일을 한 번만 알려 주고 시작하게 한다.
const DOES: { icon: IconName; title: string; text: string }[] = [
  { icon: 'calendar', title: '오늘 일정 브리핑', text: '행사, 경기, 예약을 말로 알려 드려요' },
  { icon: 'message', title: '아쉬운 리뷰에 바로 답글', text: '30분 안에 사과 답글을 달아요' },
  { icon: 'clock', title: '좋은 리뷰 답글 예약', text: '가장 잘 보일 때 올려요' },
];

export default function StartScreen() {
  const router = useRouter();
  const { signedIn } = useSession();
  const { scale } = useLayout();
  if (signedIn) return <Redirect href="/" />;
  const tile = Math.round(48 * scale);
  return (
    <StartFrame bottom={<Button label="도나를 비서로 영입하러 가기" onPress={() => router.push('/login')} />}>
      <Image source={require('@/assets/images/donna-logo.png')} style={{ width: 132 * scale, height: 44 * scale }} resizeMode="contain" accessibilityLabel="도나" />
      <View style={styles.tagline}>
        <View style={styles.rule} />
        <Txt variant="small" color="ink3">
          사장님을 위한 AI 비서
        </Txt>
        <View style={styles.rule} />
      </View>
      <Image source={require('@/assets/donna/b4-0.png')} style={{ width: 168 * scale, height: 168 * scale, marginTop: space.s24 }} resizeMode="contain" />
      <Txt variant="title" center style={{ marginTop: space.s4 }}>
        매장 운영, 도나가 먼저 챙겨요
      </Txt>
      <View style={{ alignSelf: 'stretch', marginTop: space.s24 }}>
        {DOES.map((d, i) => (
          <View key={d.title} style={[styles.row, i > 0 && { borderTopWidth: 1, borderTopColor: colors.line }]}>
            <View style={[styles.tile, { width: tile, height: tile }]}>
              <Icon name={d.icon} size={Math.round(26 * scale)} color="brand" />
            </View>
            <View style={{ flex: 1 }}>
              <Txt variant="bodyStrong">{d.title}</Txt>
              <Txt variant="label" color="ink2">
                {d.text}
              </Txt>
            </View>
          </View>
        ))}
      </View>
    </StartFrame>
  );
}

const styles = StyleSheet.create({
  tagline: { flexDirection: 'row', alignItems: 'center', gap: space.s8, marginTop: space.s4 },
  rule: { width: 20, height: 1.5, borderRadius: 1, backgroundColor: colors.line },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.s16, paddingVertical: space.s12 },
  tile: { borderRadius: radius.tile, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' },
});
