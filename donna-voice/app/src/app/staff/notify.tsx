import { useRouter } from 'expo-router';
import { Platform, StyleSheet, View } from 'react-native';

import { Icon, IconName } from '@/components/Icon';
import { BigButton, StaffFrame, StaffHeader, useStoreHead } from '@/components/staff';
import { Txt } from '@/components/Txt';
import { LinkButton } from '@/components/ui';
import { colors, radius, space } from '@/theme/tokens';

// F-05 처음 한 번: 홈 화면에 추가하고 알림을 허용한다. 문자나 알림톡이 아니라 휴대폰 자체 알림이다.
const STEPS: { icon: IconName; step: string; title: string; how: string }[] = [
  { icon: 'send', step: '1단계', title: '홈 화면에 추가', how: '공유 버튼 › 홈 화면에 추가' },
  { icon: 'bell', step: '2단계', title: '알림 허용', how: '아래 버튼 › 허용' },
];

export default function StaffNotify() {
  const router = useRouter();
  const store = useStoreHead();
  const allow = async () => {
    if (Platform.OS === 'web' && typeof window !== 'undefined' && 'Notification' in window) {
      await (window as any).Notification.requestPermission().catch(() => {});
    }
    router.replace('/staff/today');
  };
  return (
    <StaffFrame bottom={<><BigButton label="알림 허용" onPress={allow} /><LinkButton label="나중에" onPress={() => router.replace('/staff/today')} /></>}>
      <StaffHeader store={store} />
      <View style={{ gap: space.s4, marginTop: space.s8 }}>
        <Txt variant="display">알림 받기</Txt>
        <Txt variant="label" color="ink2">
          새 할 일이 오면 휴대폰이 울려요
        </Txt>
      </View>
      <View style={styles.card}>
        {STEPS.map((s) => (
          <View key={s.step} style={styles.row}>
            <View style={styles.tile}>
              <Icon name={s.icon} size={22} color="brand" />
            </View>
            <View style={{ flex: 1 }}>
              <Txt variant="label" color="ink2">
                {s.step}
              </Txt>
              <Txt variant="bodyStrong">{s.title}</Txt>
              <Txt variant="label" color="ink2">
                {s.how}
              </Txt>
            </View>
          </View>
        ))}
      </View>
    </StaffFrame>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.s16, padding: space.s16, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.s12 },
  tile: { width: 44, height: 44, borderRadius: radius.tile, backgroundColor: colors.brandSoft, alignItems: 'center', justifyContent: 'center' },
});
