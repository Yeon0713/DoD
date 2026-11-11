// 포스터 공통 값. 미리 보기(04-63), 그림 파일 만들기, 오늘 카드 썸네일(05-31n)이 같이 쓴다.
import type { StoreSettings } from "@/types/contract";

export type Theme = "dark" | "light" | "brand";
export const THEMES: Theme[] = ["dark", "light", "brand"];
export const THEME_STYLE: Record<Theme, { bg: string; text: string; sub: string; canvasBg: string; canvasText: string }> = {
  dark: { bg: "bg-ink", text: "text-brand-ink", sub: "text-brand-soft", canvasBg: "#2b1a0f", canvasText: "#fff8f0" },
  light: { bg: "bg-brand-soft", text: "text-ink", sub: "text-ink-2", canvasBg: "#f2e4d4", canvasText: "#2b1a0f" },
  brand: { bg: "bg-brand", text: "text-brand-ink", sub: "text-brand-soft", canvasBg: "#6f4220", canvasText: "#fff8f0" },
};

/** 포스터 큰 글자는 두 줄 안에 들어가게 업종 이름으로 쓴다 (예: "곱창 한 판", "국수 한 그릇"). h는 lib/cards.ts happening() 결과 */
export function defaultHeadline(h: { kind: "GAME" | "EVENT" | null; label: string } | null, s: StoreSettings) {
  const food = s.category.includes("곱창") ? "곱창 한 판" : `${s.category} 한 그릇`;
  if (!h) return `오늘은\n${food}`;
  if (h.kind === "GAME") {
    const sport = h.label.match(/(축구|야구|농구|배구|e스포츠)/)?.[0] ?? "경기";
    const second = `${sport} 보며 ${food}`;
    // 한 줄이 포스터 폭을 넘으면 단어 중간에서 끊기지 않게 줄을 직접 나눈다.
    return second.replace(/\s/g, "").length <= 8 ? `${h.label.split(" ")[0]} 저녁,\n${second}` : `${h.label.split(" ")[0]} 저녁,\n${sport} 보며\n${food}`;
  }
  if (h.kind === "EVENT") return `축제 구경하고\n${food}`;
  return `추운 날엔\n따뜻한 ${food}`;
}

/** 승인 날 만들어 둔 포스터(메뉴, 글자, 색). 서버 PATCH /api/posters가 생기기 전까지 이 기기(drafts)에 둔다. */
export type KeptPoster = { menuIdx: number; headline: string | null; storeLine: string | null; theme: Theme };

export function readKept(saved: Record<string, string>, key: string): KeptPoster | null {
  const raw = saved[key];
  if (!raw) return null;
  try {
    return JSON.parse(raw) as KeptPoster;
  } catch {
    return null;
  }
}
