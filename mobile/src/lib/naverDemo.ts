// 데모 테스트 모드: 켜면 "네이버로 시작하기"가 서버의 네이버 로그인으로 간다 (웹에서만).
// 서버에 네이버 앱 키가 없으면(도메인을 받아 등록하기 전) 임시 네이버 로그인 화면이 나오고, 테스트 아이디마다 정해 둔 가게로 쓴다.
// 시작 화면 위 메뉴에서 켜고 끈다. 서버 /api/auth/naver/* (server/app/modules/auth/router.py) 를 쓴다.
// 로그인 창으로 이 탭을 옮겼다가, 로그인과 동의를 마치면 서버가 /start/naver-login?ticket= 으로 돌려보낸다.
import { Platform } from "react-native";
import type { Donna } from "./cards";
import { BASE_URL, serverHealth } from "./server";
import { createStore } from "./store";

// 로그아웃, 서버 재시작, "처음 상태로"에도 지워지지 않게 dona.keep. 에 둔다 (lib/storage.ts)
export const demoMode = createStore<{ on: boolean }>("dona.keep.demoMode.v1", { on: false });

/** 네이버 로그인으로 받은 정보 (사장님이 동의한 것만) */
export type NaverProfile = {
  received: Record<string, string>;
  missing: string[];
  at: string;
  /** 임시 네이버 로그인의 테스트 계정인지 */
  test: boolean;
  /** 테스트 계정에 정해 둔 가게. 진짜 네이버 로그인이면 없다 (가게는 따로 찾는다) */
  storeId: string | null;
  storeName: string | null;
};
export const naverProfile = createStore<{ value: NaverProfile | null }>("dona.naverProfile.v1", { value: null });

/** 네이버 회원 프로필 항목 이름 */
export const NAVER_FIELD_LABEL: Record<string, string> = {
  name: "이름",
  nickname: "별명",
  email: "이메일",
  mobile: "휴대폰 번호",
  mobile_e164: "휴대폰 번호 (국제 표기)",
  gender: "성별",
  age: "나이대",
  birthday: "생일",
  birthyear: "태어난 해",
  profile_image: "프로필 사진",
  id: "네이버 회원 번호 (도나 전용)",
};
const GENDER: Record<string, string> = { M: "남성", F: "여성", U: "밝히지 않음" };

export function naverFieldText(key: string, value: string): string {
  return key === "gender" ? (GENDER[value] ?? value) : value;
}

/** 서버의 네이버 로그인을 쓸지: 데모 테스트 모드가 켜져 있고 웹일 때 */
export function useRealNaver(): boolean {
  return demoMode.useValue().on && Platform.OS === "web";
}

/** 이 탭을 네이버 로그인 창으로 옮긴다. 마치면 backPath(이 앱 주소)로 돌아온다.
 *
 * 서버가 꺼져 있으면 탭이 열리지 않는 주소로 가 버려 앱으로 돌아올 수 없다. 그래서 먼저 서버가 살아 있는지 보고,
 * 닿지 않으면 옮기지 않고 SERVER_UNREACHABLE 로 알린다 (앱 화면에서 "다시 하기"를 누를 수 있게).
 */
export async function goToNaverLogin(backPath: string, stillWanted: () => boolean = () => true): Promise<void> {
  if (!(await serverHealth(3000))) throw new Error("SERVER_UNREACHABLE");
  if (!stillWanted()) return;
  const back = `${window.location.origin}${backPath}`;
  window.location.assign(`${BASE_URL}/api/auth/naver/start?back=${encodeURIComponent(back)}`);
}

/** 돌아온 표(ticket)로 네이버에서 받은 정보와 이 계정의 가게를 읽는다 */
export async function readNaverResult(ticket: string): Promise<NaverProfile> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}/api/auth/naver/result/${encodeURIComponent(ticket)}`);
  } catch {
    throw new Error("NAVER_UNREACHABLE");
  }
  if (!res.ok) throw new Error("TICKET_EXPIRED");
  const body = (await res.json()) as {
    received: Record<string, string>;
    missing: string[];
    received_at: string;
    test: boolean;
    store_id: string | null;
    store_name: string | null;
  };
  return { received: body.received, missing: body.missing, at: body.received_at, test: body.test, storeId: body.store_id, storeName: body.store_name };
}

/** 서버가 돌려보낸 오류 코드 → 사장님이 읽을 말 (코드는 보여 주지 않는다) */
export function naverErrorText(code: string): { title: string; sub: string; img: Donna } {
  if (code === "access_denied") return { title: "네이버 동의를 취소했어요", sub: "도나를 쓰려면 네이버 동의가 필요해요.\n다시 하기를 누르면\n네이버 화면이 다시 열려요", img: "q-scratch" };
  if (code === "TICKET_EXPIRED") return { title: "시간이 지나서\n다시 해야 해요", sub: "다시 하기를 눌러 주세요", img: "q-scratch" };
  if (code === "SERVER_UNREACHABLE") return { title: "도나 서버에\n닿지 않아요", sub: "서버가 켜져 있는지 확인하고\n다시 하기를 눌러 주세요", img: "q-laptop" };
  if (code === "NAVER_UNREACHABLE") return { title: "네이버에 연결되지 않아요", sub: "인터넷을 확인하고 다시 해 주세요", img: "q-laptop" };
  return { title: "네이버 로그인을\n마치지 못했어요", sub: "잠시 뒤 다시 해 주세요", img: "q-arms" };
}
