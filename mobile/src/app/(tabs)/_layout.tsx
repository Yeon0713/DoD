// 아래 탭 4개 (홈, 이번 주, 매출, 설정). 07: 첫 칸 이름을 "오늘"에서 "홈"으로 바꿨다. Figma 05, 06: 아이콘과 글자를 위아래 가운데에 둔다 (위아래 여백 10).
import { Redirect } from 'expo-router';
import { Tabs } from 'expo-router/js-tabs';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon, type IconName } from '@/components/icons/Icon';
import { account } from '@/lib/account';
import { prefs } from '@/lib/localStore';
import tokens from '@/theme/tokens.json';

const icon = (name: IconName) =>
  function TabIcon({ color }: { color: unknown }) {
    return <Icon name={name} size={28} color={String(color)} />;
  };

export default function TabLayout() {
  const insets = useSafeAreaInsets();
  // 처음 쓰는 사람은 처음 설정(가게 찾기 → 장사 시간 → 알림)부터 한다.
  const onboarded = prefs.useValue().onboarded;
  const signedIn = account.useValue().method !== null;
  // 08-1: 로그인 안 했으면 첫 화면(처음) 또는 로그인(다시 왔을 때)으로
  if (!signedIn) return <Redirect href={onboarded ? "/login" : "/start"} />;
  if (!onboarded) return <Redirect href="/start" />;
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: tokens.colors.brand,
        tabBarInactiveTintColor: tokens.colors['ink-3'],
        tabBarStyle: {
          backgroundColor: tokens.colors.surface,
          borderTopColor: tokens.colors.line,
          // 아이콘 28 + 간격 4 + 글자 20, 위아래 여백 8. 아래 여백이 없는 기기(웹, 버튼식 안드로이드)에서도 글자가 잘리지 않는 높이
          height: 86 + insets.bottom,
          paddingTop: 8,
          paddingBottom: 8 + insets.bottom,
        },
        tabBarLabelStyle: {
          fontFamily: tokens.fonts.medium,
          fontSize: tokens.typography.small.size,
          lineHeight: tokens.typography.small.lineHeight,
          marginTop: 4,
        },
        sceneStyle: { backgroundColor: tokens.colors.paper },
      }}>
      <Tabs.Screen name="index" options={{ title: '홈', tabBarIcon: icon('home'), tabBarButtonTestID: 'tab-home' }} />
      <Tabs.Screen name="week" options={{ title: '이번 주', tabBarIcon: icon('calendar'), tabBarButtonTestID: 'tab-week' }} />
      <Tabs.Screen name="sales" options={{ title: '매출', tabBarIcon: icon('chart'), tabBarButtonTestID: 'tab-sales' }} />
      <Tabs.Screen name="settings" options={{ title: '설정', tabBarIcon: icon('sliders'), tabBarButtonTestID: 'tab-settings' }} />
    </Tabs>
  );
}
