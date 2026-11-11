// 탭 안에서 자세히 보기 화면을 쌓는다 (아래 탭은 그대로 보인다).
import { Stack } from 'expo-router';

import tokens from '@/theme/tokens.json';

export default function TabStack() {
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: tokens.colors.paper } }} />;
}
