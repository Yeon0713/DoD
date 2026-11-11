// 서버 코드값을 화면 문구로 바꾸는 사전. 화면 문구는 Figma 04 시안을 따른다.
import type { ComplaintGroup, ComplaintType, Platform } from "@/types/contract";
import type { IconName } from "@/components/icons/Icon";

export const PLATFORM_KO: Record<Platform, string> = {
  NAVER: "네이버",
  BAEMIN: "배달의민족",
  YOGIYO: "요기요",
  COUPANG: "쿠팡이츠",
};

/** 불만 리뷰 카드 제목. 06부터 한 줄로 쓴다 (Figma 06-4, 06-39). */
export const COMPLAINT_TITLE: Record<ComplaintType, string> = {
  DELIVERY_DELAY: "배달이 늦었다는 리뷰예요",
  TASTE: "맛이 달랐다는 리뷰예요",
  PORTION: "양이 적었다는 리뷰예요",
  HYGIENE: "위생이 걱정된다는 리뷰예요",
  PHOTO_MISMATCH: "사진과 달랐다는 리뷰예요",
  SERVICE: "응대가 아쉬웠다는 리뷰예요",
};

/** 같은 불만 카드(06-10)에서 도나가 정리해 둔 것 */
export const COMPLAINT_FOUND: Record<ComplaintType, string> = {
  DELIVERY_DELAY: "언제 늦었는지 정리해 뒀어요",
  TASTE: "어떤 메뉴였는지 정리해 뒀어요",
  PORTION: "어떤 메뉴였는지 정리해 뒀어요",
  HYGIENE: "어떤 말이 나왔는지 정리해 뒀어요",
  PHOTO_MISMATCH: "어떤 메뉴였는지 정리해 뒀어요",
  SERVICE: "언제 그랬는지 정리해 뒀어요",
};

/** 같은 불만이 쌓였을 때 카드 제목에 쓰는 말 */
export const COMPLAINT_REPEAT: Record<ComplaintType, string> = {
  DELIVERY_DELAY: "배달이 늦다는",
  TASTE: "맛이 달라졌다는",
  PORTION: "양이 적다는",
  HYGIENE: "위생이 걱정된다는",
  PHOTO_MISMATCH: "사진과 다르다는",
  SERVICE: "응대가 아쉽다는",
};

export const COMPLAINT_SHORT: Record<ComplaintType, string> = {
  DELIVERY_DELAY: "배달 지연",
  TASTE: "맛",
  PORTION: "양",
  HYGIENE: "위생",
  PHOTO_MISMATCH: "사진과 다름",
  SERVICE: "응대",
};

export const COMPLAINT_ICON: Record<ComplaintGroup, IconName> = {
  DELIVERY: "scooter",
  FOOD: "soup",
  SERVICE: "message",
};

/** 받침에 맞춰 을/를을 붙인다. "칼국수" → "칼국수를", "곱창전골" → "곱창전골을" */
export function withObject(word: string): string {
  const hangul = [...word].reverse().find((ch) => ch >= "가" && ch <= "힣");
  if (!hangul) return `${word}을`;
  const hasFinal = (hangul.charCodeAt(0) - 0xac00) % 28 !== 0;
  return `${word}${hasFinal ? "을" : "를"}`;
}

/** "잔치국수가", "저녁이" (받침에 따라 이/가) */
export function withSubject(word: string): string {
  const hangul = [...word].reverse().find((ch) => ch >= "가" && ch <= "힣");
  if (!hangul) return `${word}이`;
  return `${word}${(hangul.charCodeAt(0) - 0xac00) % 28 !== 0 ? "이" : "가"}`;
}
