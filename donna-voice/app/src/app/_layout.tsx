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

import { LayoutProvider } from '@/lib/layout';
import { SessionProvider, useSession } from '@/lib/session';
import { colors } from '@/theme/tokens';

SplashScreen.preventAutoHideAsync().catch(() => {});

function Screens({ fontsReady }: { fontsReady: boolean }) {
  const { ready } = useSession();
  const show = ready && fontsReady;
  useEffect(() => {
    if (show) SplashScreen.hideAsync().catch(() => {});
  }, [show]);
  if (!show) return <View style={{ flex: 1, backgroundColor: colors.paper }} />;
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.paper }, animation: 'none' }} />;
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
