import { View } from 'react-native';
import { Text } from '@/components/ui/Text';
import { SafeAreaView } from 'react-native-safe-area-context';

type Props = { title: string; description: string };

export function PlaceholderScreen({ title, description }: Props) {
  return (
    <SafeAreaView edges={['top']} style={{ flex: 1 }}>
      <View className="flex-1 bg-paper px-5 pt-6">
        <Text className="text-display text-ink">{title}</Text>
        <View className="mt-4 rounded-card border border-line bg-surface p-5">
          <Text className="text-title text-ink">준비 중이에요</Text>
          <Text className="mt-2 text-body text-ink-2">{description}</Text>
          <Text className="mt-3 text-small text-ink-3">토큰 · 폰트 · 탭 확인용 화면</Text>
        </View>
        <View className="mt-4 rounded-button bg-brand px-5 py-4">
          <Text className="text-center text-button text-brand-ink">버튼 글자 18/24 굵게</Text>
        </View>
      </View>
    </SafeAreaView>
  );
}
