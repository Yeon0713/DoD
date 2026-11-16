import { useRouter } from 'expo-router';
import { Image, Pressable, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { Txt } from '@/components/Txt';
import { Button, StartFrame } from '@/components/ui';
import { useLayout } from '@/lib/layout';
import { useSession } from '@/lib/session';
import { space } from '@/theme/tokens';

// E-02 로그인. 지금은 목업이라 어느 것을 눌러도 통과한다 (docs/open-features.md).
export default function LoginScreen() {
  const router = useRouter();
  const { signIn, mic } = useSession();
  const { scale } = useLayout();
  const enter = () => {
    signIn();
    router.replace(mic === 'granted' ? '/' : '/mic');
  };
  return (
    <StartFrame
      top={
        <Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="뒤로" style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}>
          <Icon name="chevronLeft" size={26} color="ink" />
        </Pressable>
      }
      bottom={<View />}
    >
      <Image source={require('@/assets/donna/b2-1.png')} style={{ width: 200 * scale, height: 200 * scale }} resizeMode="contain" />
      <Txt variant="display" center style={{ marginTop: space.s8 }}>
        어떻게 시작할까요?
      </Txt>
      <View style={{ alignSelf: 'stretch', gap: space.s8, marginTop: space.s24 }}>
        <Button
          kind="naver"
          label="네이버로 시작하기"
          onPress={enter}
          left={
            <Txt variant="button" color="brandInk" style={{ fontSize: 16 }}>
              N
            </Txt>
          }
        />
        <Button kind="outline" label="휴대폰 번호로 시작하기" onPress={enter} />
        <Pressable onPress={enter} accessibilityRole="button" style={{ minHeight: 44, flexDirection: 'row', gap: space.s4, alignItems: 'center', justifyContent: 'center' }}>
          <Txt variant="label" color="ink2">
            이미 쓰고 계세요?
          </Txt>
          <Txt variant="label" color="brand" style={{ textDecorationLine: 'underline' }}>
            로그인
          </Txt>
        </Pressable>
      </View>
    </StartFrame>
  );
}
