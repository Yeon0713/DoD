import { NotoSansKR_400Regular } from '@expo-google-fonts/noto-sans-kr/400Regular';
import { NotoSansKR_500Medium } from '@expo-google-fonts/noto-sans-kr/500Medium';
import { NotoSansKR_700Bold } from '@expo-google-fonts/noto-sans-kr/700Bold';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { LaunchLoading } from '@/components/motion';
import { LayoutProvider } from '@/lib/layout';
import { SessionProvider, useSession } from '@/lib/session';
import { colors } from '@/theme/tokens';

SplashScreen.preventAutoHideAsync().catch(() => {});

function Screens({ fontsReady }: { fontsReady: boolean }) {
  const { ready } = useSession();
  const show = ready && fontsReady;
  useEffect(() => {
    SplashScreen.hideAsync().catch(() => {});
  }, []);
  // 첫 화면은 아래에서 미리 그려 두고, 그 위에 타이핑하는 도나(Figma 10-m2)를 한 바퀴 덮었다가 흐리게 걷는다
  return (
    <View style={{ flex: 1, backgroundColor: colors.paper }}>
      {show ? <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.paper }, animation: 'none' }} /> : null}
      <LaunchLoading ready={show} />
    </View>
  );
}

export default function RootLayout() {
  // 키 이름이 곧 fontFamily 이름이다. theme/tokens.ts 의 fonts 값과 맞춰야 한다.
  const [loaded, error] = useFonts({ NotoSansKR_400Regular, NotoSansKR_500Medium, NotoSansKR_700Bold });
  return (
    <SafeAreaProvider>
      <LayoutProvider>
        <SessionProvider>
          <StatusBar style="dark" />
          <Screens fontsReady={loaded || !!error} />
        </SessionProvider>
      </LayoutProvider>
    </SafeAreaProvider>
  );
}
