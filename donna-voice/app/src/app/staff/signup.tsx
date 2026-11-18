import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { View } from 'react-native';

import { BigButton, Field, StaffFrame, StaffHeader, useStoreHead } from '@/components/staff';
import { Txt } from '@/components/Txt';
import { api, ApiFailure } from '@/lib/api';
import { staffSession } from '@/lib/staffSession';
import { space } from '@/theme/tokens';

// F-03 가입: 이름은 사장님이 "하린이한테"라고 부르는 이름이다. 다음부터는 같은 주소에서 아이디와 비밀번호로 들어온다.
// 가입하면 서버가 로그인 표시(토큰)를 준다. 아이디가 겹치거나 비밀번호가 짧으면 서버가 까닭을 알려 준다.
export default function StaffSignup() {
  const router = useRouter();
  const store = useStoreHead();
  const [name, setName] = useState('');
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setName(staffSession.get().name ?? '');
  }, []);
  const ok = name.trim().length > 0 && loginId.trim().length > 2 && password.length >= 8;
  const submit = async () => {
    try {
      const r = await api.staff.signup({ code: staffSession.get().code ?? '', name, login_id: loginId, password });
      await staffSession.set({ staffId: r.staff_id, name: r.call, token: r.token });
      router.replace('/staff/welcome');
    } catch (e) {
      setError(e instanceof ApiFailure ? e.message : '지금은 가입하기 어려워요. 조금 뒤에 다시 해 주세요.');
    }
  };
  return (
    <StaffFrame bottom={<BigButton label="가입" onPress={submit} disabled={!ok} />}>
      <StaffHeader store={store} />
      <View style={{ gap: space.s4, marginTop: space.s8 }}>
        <Txt variant="display">가입</Txt>
        <Txt variant="label" color="ink2">
          처음 한 번만 해요
        </Txt>
      </View>
      <Field label="이름" value={name} onChange={(v) => (setError(null), setName(v))} />
      <Field label="아이디" value={loginId} onChange={(v) => (setError(null), setLoginId(v))} />
      <Field label="비밀번호" value={password} onChange={(v) => (setError(null), setPassword(v))} secure hint="8자 이상" />
      {error ? (
        <Txt variant="label" color="urgent" accessibilityRole="alert">
          {error}
        </Txt>
      ) : null}
    </StaffFrame>
  );
}
