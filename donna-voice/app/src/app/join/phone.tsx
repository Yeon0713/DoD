import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { JoinPage, Note } from '@/components/join';
import { Txt } from '@/components/Txt';
import { Button } from '@/components/ui';
import { formatPhone, isPhone } from '@/lib/join';
import { colors, radius, space } from '@/theme/tokens';

// 휴대폰 번호 적기 (이전 앱 08-1p). 문자 보내기는 아직 목업이다 (숫자 000000 만 틀린 것으로 본다).
export default function PhoneScreen() {
  const router = useRouter();
  const mode = useLocalSearchParams<{ mode?: string }>().mode === 'login' ? 'login' : 'signup';
  const [digits, setDigits] = useState('');
  const [sending, setSending] = useState(false);
  const ok = isPhone(digits);
  const send = async () => {
    setSending(true);
    await new Promise((r) => setTimeout(r, 700)); // 목업: 문자를 보내는 동안
    setSending(false);
    router.push(`/join/code?phone=${digits}&mode=${mode}`);
  };
  return (
    <JoinPage
      onBack={() => router.replace(mode === 'login' ? '/join/login' : '/login')}
      footer={<Button label={sending ? '보내는 중' : '숫자 받기'} disabled={!ok || sending} onPress={() => void send()} />}
    >
      <Txt variant="display" style={{ paddingTop: space.s16 }} accessibilityRole="header">
        휴대폰 번호를 적어 주세요
      </Txt>
      <Txt variant="body" color="ink2" style={{ marginTop: space.s8 }}>
        문자로 숫자 6개를 보내 드려요
      </Txt>
      <TextInput
        accessibilityLabel="휴대폰 번호"
        value={formatPhone(digits)}
        onChangeText={(v) => setDigits(v.replace(/\D/g, '').slice(0, 11))}
        keyboardType="phone-pad"
        autoComplete="tel"
        placeholder="010-0000-0000"
        placeholderTextColor={colors.ink3}
        autoFocus
        onSubmitEditing={() => ok && void send()}
        style={styles.input}
      />
      <View style={{ marginTop: space.s12 }}>
        <Note>가입과 로그인에만 써요. 광고 문자는 보내지 않아요</Note>
      </View>
    </JoinPage>
  );
}

const styles = StyleSheet.create({
  input: {
    marginTop: space.s24, height: 64, borderRadius: radius.button, borderWidth: 2, borderColor: colors.brand, backgroundColor: colors.surface,
    paddingHorizontal: space.s16, fontSize: 22, fontFamily: 'NotoSansKR_700Bold', color: colors.ink,
  },
});
