import { useLocalSearchParams, useRouter } from 'expo-router';
import { ComponentRef, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { JoinPage } from '@/components/join';
import { Txt } from '@/components/Txt';
import { Button } from '@/components/ui';
import { formatPhone, join } from '@/lib/join';
import { useSession } from '@/lib/session';
import { useEnterApp } from '@/lib/useEnterApp';
import { colors, radius, space } from '@/theme/tokens';

// 문자로 온 숫자 6개 (이전 앱 08-1o). 6칸을 다 적으면 바로 확인한다. 목업이라 000000 만 틀린 것으로 본다.
// 확인되면: 이 번호로 사장님 확인까지 마친 가게가 있으면 바로 앱으로, 없으면 가게 찾기부터.
const CODE_SECONDS = 180;
const RESEND_AFTER = 30;
const WRONG_CODE = '000000';

export default function CodeScreen() {
  const router = useRouter();
  const session = useSession();
  const enterApp = useEnterApp();
  const params = useLocalSearchParams<{ phone?: string; mode?: string }>();
  const phone = params.phone ?? '';
  const [code, setCode] = useState('');
  const [left, setLeft] = useState(CODE_SECONDS);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<ComponentRef<typeof TextInput>>(null);
  useEffect(() => {
    const h = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(h);
  }, []);
  const expired = left === 0;

  const verify = async (value: string) => {
    setChecking(true);
    setError(null);
    await new Promise((r) => setTimeout(r, 700));
    if (value === WRONG_CODE) {
      setError('숫자가 맞지 않아요. 다시 적어 주세요');
      setCode('');
      setChecking(false);
      input.current?.focus();
      return;
    }
    session.setAccount({ login: 'phone', phone, naver: null, storeId: null, storeName: null });
    try {
      const found = await join.ownerStore(`phone:${phone}`);
      if (found.store_id) return await enterApp(found.store_id);
    } catch {
      /* 서버에 닿지 않으면 가게 찾기부터 */
    }
    setChecking(false);
    router.replace('/join/store');
  };
  const onChange = (v: string) => {
    const next = v.replace(/\D/g, '').slice(0, 6);
    setCode(next);
    if (next.length > 0) setError(null);
    if (next.length === 6 && !expired) void verify(next);
  };
  const mm = Math.floor(left / 60);
  const ss = String(left % 60).padStart(2, '0');
  const canResend = left <= CODE_SECONDS - RESEND_AFTER;

  return (
    <JoinPage
      onBack={() => router.replace(`/join/phone?mode=${params.mode ?? 'signup'}`)}
      footer={<Button label={checking ? '확인하는 중' : '확인'} disabled={code.length < 6 || checking || expired} onPress={() => void verify(code)} />}
    >
      <Txt variant="display" style={{ paddingTop: space.s16 }} accessibilityRole="header">
        문자로 온 숫자 6자리를 적어 주세요
      </Txt>
      <Txt variant="body" color="ink2" style={{ marginTop: space.s8 }}>
        {`${formatPhone(phone)}로 보냈어요`}
      </Txt>
      <View style={styles.boxes}>
        {Array.from({ length: 6 }, (_, i) => {
          const on = i === Math.min(code.length, 5) && !expired;
          return (
            <View key={i} style={[styles.box, on ? { borderWidth: 2, borderColor: colors.brand } : { borderWidth: 1.5, borderColor: colors.line }]}>
              <Txt variant="title">{code[i] ?? ''}</Txt>
            </View>
          );
        })}
        {/* 실제 입력 칸은 6칸 위에 투명하게 덮는다 (문자 자동 채우기도 받는다) */}
        <TextInput
          ref={input}
          accessibilityLabel="문자로 온 숫자 6개"
          value={code}
          onChangeText={onChange}
          keyboardType="number-pad"
          textContentType="oneTimeCode"
          autoComplete="sms-otp"
          maxLength={6}
          autoFocus
          caretHidden
          style={styles.hidden}
        />
      </View>
      <View style={styles.row}>
        <Txt variant="label" color={expired ? 'urgent' : 'ink2'}>
          {expired ? '시간이 지났어요. 다시 받아 주세요' : `${mm}분 ${ss}초 남았어요`}
        </Txt>
        <Pressable
          onPress={() => {
            setLeft(CODE_SECONDS);
            setCode('');
            setError(null);
          }}
          disabled={!canResend}
          accessibilityRole="button"
          hitSlop={10}
          style={{ minHeight: 44, justifyContent: 'center' }}
        >
          <Txt variant="label" color={canResend ? 'brand' : 'ink3'} style={{ textDecorationLine: 'underline', fontFamily: 'NotoSansKR_700Bold' }}>
            다시 받기
          </Txt>
        </Pressable>
      </View>
      {error ? (
        <Txt variant="label" color="urgent" accessibilityRole="alert">
          {error}
        </Txt>
      ) : null}
    </JoinPage>
  );
}

const styles = StyleSheet.create({
  boxes: { marginTop: space.s24, flexDirection: 'row', gap: space.s8 },
  box: { flex: 1, height: 60, alignItems: 'center', justifyContent: 'center', borderRadius: radius.tile, backgroundColor: colors.surface },
  hidden: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, opacity: 0, color: 'transparent' },
  row: { marginTop: space.s12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
});
