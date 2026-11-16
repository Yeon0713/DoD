import { Stack } from 'expo-router';

import { colors } from '@/theme/tokens';

// 알바생 앱 (Figma v0.2.1 F-02 ~ F-09). 말로 쓰지 않는다. 손으로 보고 누른다.
export default function StaffLayout() {
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.paper }, animation: 'none' }} />;
}
