import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { BigButton, Field, StaffFrame, StaffHeader, useStoreHead } from '@/components/staff';
import { Txt } from '@/components/Txt';
import { LinkButton } from '@/components/ui';
import { api, ApiFailure } from '@/lib/api';
import { staffSession } from '@/lib/staffSession';
import { space } from '@/theme/tokens';

// 다시 들어오기: 가입한 알바생이 다른 휴대폰이나 브라우저에서 아이디와 비밀번호로 들어온다 (F-03 "다음부터는 아이디와 비밀번호로").
// 들어오면 로그인 표시(토큰)를 받아 바로 오늘 할 일로 간다. 사장님이 내보낸 사람은 들어올 수 없다.
export default function StaffLogin() {
  const router = useRouter();
  const store = useStoreHead();
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    try {
      const r = await api.staff.login(loginId, password);
      await staffSession.clear();
      await staffSession.set({ staffId: r.staff_id, name: r.call, token: r.token });
      router.replace('/staff/today');
    } catch (e) {
      setError(e instanceof ApiFailure ? e.message : '지금은 들어가기 어려워요. 조금 뒤에 다시 해 주세요.');
    }
  };
  return (
    <StaffFrame
      bottom={
        <>
          <BigButton label="들어가기" onPress={submit} disabled={loginId.trim().length < 3 || password.length < 1} />
          <LinkButton label="처음이에요 (초대 코드 넣기)" onPress={() => router.replace('/staff')} />
        </>
      }
    >
      <StaffHeader store={store} />
      <View style={{ gap: space.s4, marginTop: space.s8 }}>
        <Txt variant="display">다시 들어오기</Txt>
        <Txt variant="label" color="ink2">
          가입할 때 정한 아이디와 비밀번호를 넣어 주세요
        </Txt>
      </View>
      <Field label="아이디" value={loginId} onChange={(v) => (setError(null), setLoginId(v))} />
      <Field label="비밀번호" value={password} onChange={(v) => (setError(null), setPassword(v))} secure />
      {error ? (
        <Txt variant="label" color="urgent" accessibilityRole="alert">
          {error}
        </Txt>
      ) : null}
    </StaffFrame>
  );
}
