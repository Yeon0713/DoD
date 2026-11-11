// 서버에 아직 없는 동작(답글 올리기, 다시 쓰기, 메뉴 순서 바꾸기, 포스터 만들기)의 목업.
// 실제 API가 생기면 이 함수 안만 바꾼다. 화면 코드는 그대로 둔다.
import { mockRewrite } from "@/mocks/extras";
import { ApiFailure } from "./api";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function failIfOffline() {
  if (typeof navigator !== "undefined" && navigator.onLine === false) throw new ApiFailure("OFFLINE", "인터넷이 끊겼어요.", true);
  // 주소에 ?fail=1을 붙이면 실패 화면(04-5f)을 볼 수 있다.
  if (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("fail") === "1") {
    throw new ApiFailure("OFFLINE", "인터넷이 끊겼어요.", true);
  }
}

/** 제안: POST /api/replies/{plan_id}/publish. text가 없으면 서버가 가진 초안을 올린다. */
export async function publishReply(_planId: string, _text?: string) {
  await wait(700);
  failIfOffline();
}

/** 제안: POST /api/replies/{plan_id}/rewrite */
export async function rewriteReply(text: string, style: "short" | "polite") {
  await wait(800);
  failIfOffline();
  return mockRewrite(text, style);
}

/** 제안: POST /api/menu-order/{plan_id} */
export async function applyMenuOrder(_planId: string) {
  await wait(1500);
  failIfOffline();
}

/** 제안: POST /api/naver/connect */
export async function connectNaver() {
  await wait(1200);
  failIfOffline();
}

/** 제안: POST /api/posters */
export async function makePoster() {
  await wait(1600);
  failIfOffline();
}
