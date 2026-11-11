// 아래에서 올라오는 시트 (05-22 나중에, 05-65 올릴 곳, 06-2e 장사 시간 고치기). 뒤 화면은 어둡게 덮고 누를 수 없다.
import { useRef, type ReactNode } from "react";
import { Modal, Platform, Pressable, ScrollView, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { useSafeAreaInsets } from "react-native-safe-area-context";

/**
 * 시트가 다 닫힌 뒤에 할 일(공유 창 띄우기, 화면 옮기기)을 하게 해 준다.
 * iOS는 시트(Modal)가 열린 채로 그 위에 공유 창을 띄우거나, 열린 시트를 화면째 빼 버리면
 * 보이지 않는 Modal 층이 남아 앱 전체가 눌리지 않는다. 그래서 open을 false로 바꾼 뒤 closed()를 기다린다.
 */
export function useSheetClose() {
  const pending = useRef<(() => void) | null>(null);
  const onDismiss = () => {
    pending.current?.();
    pending.current = null;
  };
  const closed = () =>
    new Promise<void>((resolve) => {
      pending.current = resolve;
      // iOS는 onDismiss가 온다. 다른 곳(웹, 안드로이드)이나 onDismiss가 안 올 때는 닫히는 시간만큼 기다린다.
      setTimeout(() => {
        if (pending.current === resolve) onDismiss();
      }, Platform.OS === "ios" ? 1000 : 350);
    });
  return { onDismiss, closed };
}

export function Sheet({ open, onClose, onDismiss, title, children }: { open: boolean; onClose: () => void; onDismiss?: () => void; title: string; children: ReactNode }) {
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={open} transparent animationType="slide" onRequestClose={onClose} onDismiss={onDismiss} statusBarTranslucent>
      <View className="flex-1 justify-end">
        <Pressable testID="sheet-backdrop" accessibilityLabel="닫기" onPress={onClose} className="absolute inset-0 bg-ink/40" />
        <View
          accessibilityViewIsModal
          className="max-h-[88%] w-full self-center rounded-t-[24px] bg-surface"
          style={{ maxWidth: 480, paddingBottom: Math.max(24, insets.bottom) }}
        >
          <ScrollView contentContainerStyle={{ paddingHorizontal: 24, paddingTop: 12 }} keyboardShouldPersistTaps="handled">
            <View className="mb-5 h-1.5 w-10 self-center rounded-full bg-line" />
            <Text className="mb-4 text-title text-ink" accessibilityRole="header">
              {title}
            </Text>
            {children}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}
