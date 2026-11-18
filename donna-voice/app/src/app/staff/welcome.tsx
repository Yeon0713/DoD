import { useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { BigButton, StaffFrame, StaffHeader, useStoreHead } from '@/components/staff';
import { Txt } from '@/components/Txt';
import { api } from '@/lib/api';
import { staffSession } from '@/lib/staffSession';
import { colors, radius, space } from '@/theme/tokens';

// F-04 입장 완료: "시작"을 누르면 사장님에게 "하린 씨가 알바생 화면에 들어왔어요" 알림이 간다 (D-05).
export default function StaffWelcome() {
  const router = useRouter();
  const store = useStoreHead();
  const me = staffSession.get();
  const start = async () => {
    if (me.token) await api.staff.start().catch(() => {});
    router.replace('/staff/notify');
  };
  return (
    <StaffFrame bottom={<BigButton label="시작" onPress={start} />}>
      <StaffHeader store={store} />
      <View style={{ gap: space.s4, marginTop: space.s8 }}>
        <Txt variant="display">입장 완료</Txt>
        <Txt variant="label" color="ink2">
          이 가게의 할 일을 받아요
        </Txt>
      </View>
      <View style={styles.card}>
        <View style={styles.icon}>
          <Icon name="users" size={24} color="brandInk" />
        </View>
        <Txt variant="title">{me.name ?? ''}</Txt>
      </View>
      <Txt variant="label" color="ink2">{`사장님이 "${me.name ?? ''}이한테"라고 하면 이 화면에 와요.`}</Txt>
    </StaffFrame>
  );
}

const styles = StyleSheet.create({
  card: { alignItems: 'center', gap: space.s12, padding: space.s24, borderRadius: radius.card, borderWidth: 2, borderColor: colors.brand, backgroundColor: colors.brandSoft },
  icon: { width: 44, height: 44, borderRadius: radius.tile, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
});
