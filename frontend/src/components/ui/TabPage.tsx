// 아래 탭이 있는 화면의 틀. 본문 좌우 여백 24, 위 12, 아래 20 (Figma 04-4 본문).
import type { ReactNode } from "react";
import { BottomTabs } from "./BottomTabs";
import { ToastHost } from "./sub";

export function TabPage({ children }: { children: ReactNode }) {
  return (
    <>
      <ToastHost />
      <main className="flex flex-1 flex-col px-6 pt-[max(12px,env(safe-area-inset-top))] pb-5">{children}</main>
      <BottomTabs />
    </>
  );
}
