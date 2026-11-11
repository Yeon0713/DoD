// 서버에 아직 없는 동작(답글 올리기, 다시 쓰기, 메뉴 순서 바꾸기, 포스터 만들기)의 목업.
// 실제 API가 생기면 이 함수 안만 바꾼다. 화면 코드는 그대로 둔다.
import { mockRewrite } from "@/mocks/extras";
import { ApiFailure, isOffline } from "./api";
import { devFlags } from "./dev";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function failIfOffline() {
  if (isOffline()) throw new ApiFailure("OFFLINE", "인터넷이 끊겼어요.", true);
  // 개발 화면(/dev)에서 "동작 실패"를 켜면 실패 화면(05-5f)을 볼 수 있다.
  if (devFlags.read().fail) throw new ApiFailure("OFFLINE", "인터넷이 끊겼어요.", true);
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

/** 08-1n 네이버로 시작하기, 로그인, 계정 연결. 제안: 네이버 로그인(OAuth) 뒤 POST /api/auth/naver { code } */
export async function naverLogin() {
  await wait(1500);
  failIfOffline();
}

/** 08-1p 숫자 받기. 제안: POST /api/auth/phone/code { phone } */
export async function sendPhoneCode() {
  await wait(700);
  failIfOffline();
}

/** 목업에서 틀린 숫자로 보는 값 (검토용) */
export const WRONG_CODE = "000000";

/** 08-1o 숫자 확인. 제안: POST /api/auth/phone/verify { phone, code }. 목업은 000000만 틀린 것으로 본다. */
export async function verifyPhoneCode(code: string) {
  await wait(700);
  failIfOffline();
  if (code === WRONG_CODE) throw new Error("WRONG_CODE");
}

/** 제안: POST /api/posters */
export async function makePoster() {
  await wait(1600);
  failIfOffline();
}
