// 앱: 보이는 포스터를 그대로 찍어(기본 1080 × 1350, AI 포스터는 1080 × 1920) 공유 창을 띄운다. 웹은 shareView.ts (react-native-view-shot이 웹에서 묶이지 않아 나눴다).
import * as Sharing from "expo-sharing";
import type { ComponentRef } from "react";
import type { View } from "react-native";
import { captureRef } from "react-native-view-shot";

export async function shareView(target: ComponentRef<typeof View> | null, title: string, size = { width: 1080, height: 1350 }) {
  if (!target) throw new Error("no poster");
  const uri = await captureRef(target, { format: "png", quality: 1, ...size });
  if (!(await Sharing.isAvailableAsync())) throw new Error("no share");
  await Sharing.shareAsync(uri, { mimeType: "image/png", UTI: "public.png", dialogTitle: title });
}
