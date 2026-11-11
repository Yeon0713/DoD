// "답글을 올렸어요" 띠 (05-5s). 앱 맨 위(_layout.tsx)에 하나만 둔다. 2.2초 동안 위에 떠 있다.
import { useEffect, useState } from "react";
import { Pressable, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Icon } from "@/components/icons/Icon";
import { clearToast, useToast, type Toast } from "@/lib/localStore";
import tokens from "@/theme/tokens.json";

export function ToastHost() {
  const t = useToast();
  const [shown, setShown] = useState<Toast | null>(null);
  const insets = useSafeAreaInsets();
  useEffect(() => {
    if (!t) return;
    setShown(t);
    clearToast();
  }, [t]);
  useEffect(() => {
    if (!shown) return;
    const h = setTimeout(() => setShown(null), 2200);
    return () => clearTimeout(h);
  }, [shown]);
  if (!shown) return null;
  return (
    <View pointerEvents="box-none" className="absolute inset-x-0 z-50 items-center px-4" style={{ top: Math.max(12, insets.top + 8) }}>
      <Pressable
        testID="toast"
        accessibilityRole="alert"
        accessibilityLabel={`${shown.title}. 눌러서 닫기`}
        onPress={() => setShown(null)}
        className="w-full max-w-[343px] flex-row items-center gap-3 rounded-2xl border-2 bg-surface px-4 py-3"
        style={{ borderColor: `${tokens.colors.done}80`, shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 6 }}
      >
        <View className="h-9 w-9 items-center justify-center rounded-full bg-done-soft">
          <Icon name="check" size={22} color={tokens.colors.done} />
        </View>
        <View className="flex-1">
          <Text className="text-body font-bold text-ink">{shown.title}</Text>
          {shown.sub ? <Text className="text-small text-ink-2">{shown.sub}</Text> : null}
        </View>
      </Pressable>
    </View>
  );
}
