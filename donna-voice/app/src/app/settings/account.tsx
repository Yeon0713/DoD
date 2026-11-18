import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, View } from 'react-native';

import { Sheet } from '@/components/join';
import { SettingsGroup, SettingsRow, SubPage } from '@/components/settings';
import { Txt } from '@/components/Txt';
import { Button, useLoad } from '@/components/ui';
import { api } from '@/lib/api';
import { formatPhone, join } from '@/lib/join';
import { useSession } from '@/lib/session';
import { space } from '@/theme/tokens';

// 설정 > 계정 (Figma v0.2.1 G-07, 이전 앱 09-s8 계정). 로그아웃과 탈퇴는 여기 안에 둔다 (첫 화면의 큰 버튼이면 잘못 누르기 쉽다).
// 테스트 계정(임시 네이버 로그인)이면 서버 DB 조건대로: 로그아웃은 on_logout(keep 이면 그대로), 탈퇴는 계정과 가게 연결만 끊는다
// (계정과 가게 데이터는 남는다 → 같은 아이디로 다시 로그인하면 가게 찾기부터 다시 가입한다). 진짜 계정 탈퇴 API 는 아직 없다.
export default function AccountScreen() {
  const router = useRouter();
  const session = useSession();
  const { data, failed, reload } = useLoad(api.settings);
  const [leaving, setLeaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const loginId = session.naver?.loginId ?? null;
  const login = session.login === 'naver' ? (session.naver?.test ? `네이버 (테스트 ${loginId})` : '네이버') : session.login === 'phone' && session.phone ? `휴대폰 ${formatPhone(session.phone)}` : null;

  const leave = async (kind: 'logout' | 'withdraw') => {
    setBusy(true);
    if (loginId) await (kind === 'logout' ? join.testLogout(loginId) : join.testWithdraw(loginId)).catch(() => undefined);
    setLeaving(false);
    // 아래 탭 화면까지 닫고 시작 화면으로. 대화 기록은 아래 탭 화면과 함께 사라진다.
    if (router.canDismiss()) router.dismissAll();
    session.signOut();
    router.replace('/start');
  };

  return (
    <SubPage
      title="계정"
      footer={
        <>
          <Button kind="outline" label={busy ? '나가는 중' : '로그아웃'} onPress={() => !busy && void leave('logout')} />
          <Pressable onPress={() => setLeaving(true)} accessibilityRole="button" style={{ minHeight: 44, alignItems: 'center', justifyContent: 'center' }}>
            <Txt variant="label" color="ink2">
              탈퇴하기
            </Txt>
          </Pressable>
        </>
      }
    >
      {data ? (
        <SettingsGroup inset={false}>
          {login ? <SettingsRow title="로그인" value={login} /> : null}
          <SettingsRow title="가게" sub={data.account.address} value={data.account.store_name} />
        </SettingsGroup>
      ) : failed ? (
        <Pressable onPress={reload} accessibilityRole="button">
          <Txt variant="bodyStrong">못 불러왔어요. 여기를 누르면 다시 불러와요.</Txt>
        </Pressable>
      ) : null}
      <Sheet open={leaving} onClose={() => setLeaving(false)} title="정말 탈퇴할까요?">
        <Txt variant="body" color="ink2">
          이 계정과 가게의 연결을 끊고, 이 휴대폰의 로그인 기록을 지워요. 다시 쓰려면 가게 찾기부터 다시 가입해요.
        </Txt>
        <View style={{ gap: space.s8 }}>
          <Button label="계속 쓸게요" onPress={() => setLeaving(false)} />
          <Button kind="outline" label={busy ? '탈퇴하는 중' : '탈퇴하기'} onPress={() => !busy && void leave('withdraw')} />
        </View>
      </Sheet>
    </SubPage>
  );
}
