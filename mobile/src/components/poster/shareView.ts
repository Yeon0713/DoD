// 웹에서는 쓰지 않는다. 웹 포스터는 PosterScreens.tsx의 캔버스 그리기로 공유하거나 내려받는다.
import type { ComponentRef } from "react";
import type { View } from "react-native";

export async function shareView(_target: ComponentRef<typeof View> | null, _title: string): Promise<void> {
  throw new Error("web uses canvas");
}
