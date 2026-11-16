import { useRouter } from 'expo-router';
import { ComponentRef, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { BigButton, StaffFrame, StaffHeader, useStoreHead } from '@/components/staff';
import { Txt } from '@/components/Txt';
import { api } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { staffSession } from '@/lib/staffSession';
import { colors, radius, space } from '@/theme/tokens';

// F-02 입장: 여섯 자리 초대 코드. 은행 앱의 인증 번호 칸처럼 한 칸에 한 자리. 붙여 넣으면 여섯 칸이 한 번에 찬다.
export default function StaffEnter() {
  const router = useRouter();
  const store = useStoreHead();
  const { type } = useLayout();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const input = useRef<ComponentRef<typeof TextInput>>(null);

  useEffect(() => {
    staffSession.load().then((s) => s.staffId && router.replace('/staff/today'));
  }, [router]);

  const next = async () => {
    const r = await api.staff.checkCode(code).catch(() => null);
    if (!r?.ok) {
      setError(r?.message ?? '지금은 확인하기 어려워요. 조금 뒤에 다시 해 주세요.');
      return;
    }
    await staffSession.set({ code, name: r.name });
    router.push('/staff/signup');
  };

  return (
    <StaffFrame bottom={<BigButton label="다음" onPress={next} disabled={code.length < 6} />}>
      <StaffHeader store={store} />
      <View style={{ gap: space.s4, marginTop: space.s8 }}>
        <Txt variant="display">알바생 입장</Txt>
        <Txt variant="label" color="ink2">
          사장님이 보낸 초대 코드를 넣어 주세요
        </Txt>
      </View>
      <Pressable onPress={() => input.current?.focus()} style={styles.cells} accessibilityLabel="초대 코드 여섯 칸">
        {Array.from({ length: 6 }, (_, i) => (
          <View key={i} style={[styles.cell, i === Math.min(code.length, 5) && { borderColor: colors.brand, borderWidth: 2 }]}>
            <Txt variant="title">{code[i] ?? ''}</Txt>
          </View>
        ))}
        <TextInput
          ref={input}
          value={code}
          onChangeText={(v) => {
            setError(null);
            setCode(v.replace(/\D/g, '').slice(0, 6));
          }}
          keyboardType="number-pad"
          autoFocus
          style={[StyleSheet.absoluteFill, type.title, { opacity: 0.01 }]}
        />
      </Pressable>
      <Txt variant="label" color={error ? 'urgent' : 'ink2'}>
        {error ?? '코드는 한 사람에게 하나예요. 사장님에게 받은 코드만 들어갈 수 있어요.'}
      </Txt>
    </StaffFrame>
  );
}

const styles = StyleSheet.create({
  cells: { flexDirection: 'row', gap: space.s8 },
  cell: { flex: 1, height: 60, borderRadius: radius.tile, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
});
