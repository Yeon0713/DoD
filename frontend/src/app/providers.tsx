"use client";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

let browserQueryClient: QueryClient | undefined;

function getQueryClient() {
  // 서버 렌더마다 새로 만들고, 브라우저에서는 하나를 계속 쓴다 (Next 16 TanStack Query 안내).
  if (typeof window === "undefined") return new QueryClient();
  browserQueryClient ??= new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: true } } });
  return browserQueryClient;
}

export function Providers({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={getQueryClient()}>{children}</QueryClientProvider>;
}
