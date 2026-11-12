import '../global.css';

import { NotoSansKR_400Regular } from '@expo-google-fonts/noto-sans-kr/400Regular';
import { NotoSansKR_500Medium } from '@expo-google-fonts/noto-sans-kr/500Medium';
import { NotoSansKR_700Bold } from '@expo-google-fonts/noto-sans-kr/700Bold';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { DemoCursor } from '@/components/dev/DemoCursor';
import { ToastHost } from '@/components/ui/Toast';
import { hydrateStorage } from '@/lib/storage';
import tokens from '@/theme/tokens.json';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  // 키 이름이 곧 fontFamily 이름이다. tokens.json 의 fonts 값과 맞춰야 한다.
  const [loaded, error] = useFonts({
    NotoSansKR_400Regular,
    NotoSansKR_500Medium,
    NotoSansKR_700Bold,
  });
  // 이 기기에 저장한 값(처음 설정, 카드 상태, 고쳐 쓴 답글, 개발 스위치)을 먼저 읽어 둔다. 화면은 그 뒤에 그린다.
  const [hydrated, setHydrated] = useState(false);
  const [queryClient] = useState(() => new QueryClient());

  useEffect(() => {
    hydrateStorage().finally(() => setHydrated(true));
  }, []);

  const ready = (loaded || !!error) && hydrated;
  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  if (!ready) return null;

  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <StatusBar style="dark" />
        <View style={{ flex: 1, backgroundColor: tokens.colors.paper }}>
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: tokens.colors.paper },
            }}
          />
          <ToastHost />
          {/* 시연용 마우스 표시. 웹 개발 빌드에서 주소에 ?cursor=1 을 붙였을 때만 보인다 */}
          <DemoCursor />
        </View>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
