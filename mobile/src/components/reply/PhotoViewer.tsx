// 손님 리뷰 사진을 크게 보기 (06-39r 사진 칸을 눌렀을 때). 화면 전체를 덮고 아래 닫기 버튼으로 닫는다.
import { Modal, Pressable, View, useWindowDimensions } from "react-native";
import { Text } from "@/components/ui/Text";
import { SafeAreaView } from "react-native-safe-area-context";
import { PhotoBox } from "@/components/ui/parts";

export function PhotoViewer({ photos, index, onClose }: { photos: string[]; index: number | null; onClose: () => void }) {
  const { width } = useWindowDimensions();
  const size = Math.min(width - 48, 432);
  const uri = index === null ? null : photos[index];
  return (
    <Modal visible={index !== null} transparent animationType="fade" onRequestClose={onClose} statusBarTranslucent>
      <SafeAreaView style={{ flex: 1, backgroundColor: "rgba(43,26,15,0.92)" }}>
        <View className="h-14 justify-center px-6">
          <Text className="text-label text-brand-ink">{index === null ? "" : `사진 ${index + 1} / ${photos.length}`}</Text>
        </View>
        <View className="flex-1 items-center justify-center">{uri ? <PhotoBox uri={uri} size={size} rounded={16} /> : null}</View>
        <View className="px-6 pb-6">
          <Pressable
            testID="photo-close"
            accessibilityRole="button"
            onPress={onClose}
            className="h-14 items-center justify-center rounded-button border border-brand-ink active:opacity-80"
          >
            <Text className="text-button text-brand-ink">닫기</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    </Modal>
  );
}
