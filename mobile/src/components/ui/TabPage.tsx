// 아래 탭이 있는 화면의 틀. 본문 좌우 여백 24, 위 12, 아래 20 (Figma 05-4 본문). 아래 탭은 (tabs)/_layout.tsx가 그린다.
import type { ReactElement, ReactNode } from "react";
import { ScrollView, View, type RefreshControlProps } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import tokens from "@/theme/tokens.json";

/** bg: 홈(07)만 home 색을 쓴다. 나머지 탭은 paper */
export function TabPage({ children, scroll = true, refresh, bg = tokens.colors.paper }: { children: ReactNode; scroll?: boolean; refresh?: ReactElement<RefreshControlProps>; bg?: string }) {
  return (
    <SafeAreaView edges={["top"]} style={{ flex: 1, backgroundColor: bg }}>
      {scroll ? (
        <ScrollView contentContainerStyle={{ flexGrow: 1, paddingHorizontal: 24, paddingTop: 12, paddingBottom: 20 }} refreshControl={refresh}>
          {children}
        </ScrollView>
      ) : (
        <View className="flex-1 px-6 pb-5 pt-3">{children}</View>
      )}
    </SafeAreaView>
  );
}
