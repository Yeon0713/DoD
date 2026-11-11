// 로그인 계정 (Figma 08-1 가입과 로그인, 08-19 계정). 서버에 계정 API가 생기기 전까지 이 기기에만 저장한다.
// 네이버 계정 연결 여부는 prefs.naverConnected를 쓴다 (네이버 플레이스 연결과 같은 연결이다).
import { createStore } from "./store";

export type LoginMethod = "naver" | "phone";

export interface Account {
  /** 가입한 방법. null이면 로그인 안 함 */
  method: LoginMethod | null;
  /** 휴대폰으로 가입했으면 번호 ("01012345678") */
  phone: string | null;
}

export const account = createStore<Account>("dona.account.v1", { method: null, phone: null });

/** "01012345678" → "010-1234-5678" (쓰는 중에도 하이픈을 넣는다) */
export function formatPhone(digits: string): string {
  const d = digits.replace(/\D/g, "").slice(0, 11);
  if (d.length < 4) return d;
  if (d.length < 8) return `${d.slice(0, 3)}-${d.slice(3)}`;
  const mid = d.length === 10 ? 3 : 4;
  return `${d.slice(0, 3)}-${d.slice(3, 3 + mid)}-${d.slice(3 + mid)}`;
}

/** 08-19: 가운데를 가린다 "010-****-5678" */
export function maskPhone(digits: string): string {
  const f = formatPhone(digits).split("-");
  return f.length === 3 ? `${f[0]}-${"*".repeat(f[1].length)}-${f[2]}` : formatPhone(digits);
}

/** 010, 011 등으로 시작하는 10~11자리 */
export function isPhone(digits: string): boolean {
  return /^01\d{8,9}$/.test(digits.replace(/\D/g, ""));
}
