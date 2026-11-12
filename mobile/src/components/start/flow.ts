// 처음 쓰는 날(06-1 ~ 06-3b)과 설정 화면이 같이 쓰는 작은 도우미.
import { router, type Href } from "expo-router";
import { ApiFailure } from "@/lib/api";
import type { Platform } from "@/types/contract";

/** 진행 막대 5칸: 가게 찾기, 연결, 확인, 알림 시간, 알림 켜기 */
export const STEPS = 7; // 가게 찾기, 가게 확인, 가게 정보, 리뷰 불러오기, 출근·퇴근, 알림 시간, 알림 켜기

/** 네이버 플레이스 불러오기 응답을 화면끼리 나눠 쓰는 캐시 키 */
export const NAVER_PLACE_KEY = ["naver-place"] as const;

export const PLATFORM_SHORT: Record<Platform, string> = { BAEMIN: "배민", COUPANG: "쿠팡이츠", YOGIYO: "요기요", NAVER: "네이버" };
export const PLATFORM_ORDER: Platform[] = ["BAEMIN", "COUPANG", "YOGIYO", "NAVER"];

/** "도나네 곱창 (역삼점)" 같은 괄호를 뺀 가게 이름 */
export function storeName(name: string) {
  return name.replace(/\s*\(.*\)\s*/g, "").trim();
}

/** 처음 설정을 마치고 앱으로 들어간다. 처음 설정 화면으로 뒤로 가지 못하게 바꿔 끼운다. */
export function enterApp() {
  if (router.canDismiss()) router.dismissAll();
  router.replace("/" as Href);
}

/** 설정 저장(PATCH) 실패를 사장님 말로 바꾼다. */
export function errorText(e: unknown): string {
  if (!(e instanceof ApiFailure)) return "잠시 뒤 다시 해 주세요.";
  if (e.offline) return "인터넷이 끊겨서 저장하지 못했어요.";
  if (e.code === "SLOT_IN_BUSY_DAYPART") return "바쁜 장사 시간에 걸려요. 다른 시간을 골라 주세요.";
  if (e.code === "SLOT_OUTSIDE_OPEN_HOURS") return "장사 시간 안으로 골라 주세요.";
  return e.message;
}

/** 주소 값 하나 꺼내기 (?step=share) */
export function param(v: string | string[] | undefined): string | null {
  if (Array.isArray(v)) return v[0] ?? null;
  return v ?? null;
}
