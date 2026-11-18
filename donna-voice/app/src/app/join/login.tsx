import { useRouter } from 'expo-router';
import { Pressable, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { DemoMenuBar, DonnaPic } from '@/components/join';
import { Txt } from '@/components/Txt';
import { Button, StartFrame } from '@/components/ui';
import { useLayout } from '@/lib/layout';
import { space } from '@/theme/tokens';

// 다시 왔을 때 로그인 (이전 앱 08-1L). 처음 가입한 방법으로 들어온다. 위 줄에 데모 테스트 모드 메뉴.
export default function ReturningLoginScreen() {
  const router = useRouter();
  const { scale } = useLayout();
  return (
    <StartFrame
      top={
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Pressable onPress={() => router.replace('/login')} accessibilityRole="button" accessibilityLabel="뒤로" style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="chevronLeft" size={26} color="ink" />
          </Pressable>
          <View style={{ flex: 1 }}>
            <DemoMenuBar />
          </View>
        </View>
      }
      bottom={
        <>
          <Button
            kind="naver"
            label="네이버로 로그인"
            onPress={() => router.push('/join/naver-login?mode=login')}
          />
          <Button kind="outline" label="휴대폰 번호로 로그인" onPress={() => router.push('/join/phone?mode=login')} />
          <Pressable onPress={() => router.replace('/start')} accessibilityRole="button" style={{ minHeight: 44, flexDirection: 'row', gap: space.s4, alignItems: 'center', justifyContent: 'center' }}>
            <Txt variant="label" color="ink2">
              처음이세요?
            </Txt>
            <Txt variant="label" color="brand" style={{ textDecorationLine: 'underline' }}>
              새로 시작하기
            </Txt>
          </Pressable>
        </>
      }
    >
      <DonnaPic img="b4-0" size={Math.round(160 * scale)} />
      <Txt variant="display" center style={{ marginTop: space.s8 }} accessibilityRole="header">
        다시 오셨네요
      </Txt>
      <Txt variant="body" color="ink2" center style={{ marginTop: space.s4 }}>
        처음 가입한 방법으로 들어와 주세요
      </Txt>
    </StartFrame>
  );
}
