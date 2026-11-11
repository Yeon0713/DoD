import type { Metadata, Viewport } from "next";
import { Noto_Sans_KR } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const noto = Noto_Sans_KR({
  weight: ["400", "500", "700"],
  display: "swap",
  preload: false,
  variable: "--font-noto-kr",
});

export const metadata: Metadata = {
  title: "도나",
  description: "사장님이 오늘 할 일을 하나씩 챙겨 드려요",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#fbf7f2",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" className={noto.variable}>
      <body>
        <Providers>
          {/* 기준 폭 375px. 넓은 화면에서는 가운데에 휴대폰 폭으로 보인다. */}
          <div className="mx-auto flex min-h-dvh w-full max-w-[375px] flex-col bg-paper sm:border-x sm:border-line">{children}</div>
        </Providers>
      </body>
    </html>
  );
}
