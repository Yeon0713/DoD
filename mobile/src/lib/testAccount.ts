// 임시 네이버 로그인의 테스트 계정(dona_test1~3)마다 이 기기 기록을 어떻게 다룰지. 조건은 서버 DB(server/db/test_accounts.db)에 있다.
// - on_logout = reset: 로그인할 때와 로그아웃할 때 이 기기 기록(처음 설정, 끝낸 카드, 고쳐 쓴 답글, 홈 저장본)을 지운다 → 늘 처음부터
// - on_logout = keep:  로그아웃할 때 이 기기 기록을 계정별로 보관하고(dona.keep.testAccount.<아이디>), 다시 로그인하면 되살린다.
//                       다른 테스트 계정이 이 기기에서 처음부터 시험해도(reset) 이 계정 기록은 남는다.
// 서버 쪽(그 가게의 고친 설정, 서버 시계)은 서버가 로그인·로그아웃 때 처리한다 (server/app/modules/auth/router.py).
import { cardStateSnapshot, resetCardState, restoreCardState, type CardStatus } from "./cardState";
import { drafts, prefs, type Prefs } from "./localStore";
import { naverProfile, type TestAccount } from "./naverDemo";
import { BASE_URL } from "./server";
import { refreshServerClock, storage } from "./storage";

const HOME_CACHE = "dona.home.v3"; // 홈 저장본 (lib/useHomeData.ts). 다른 가게·시각의 홈이 잠깐 보이지 않게 지운다
const savedKey = (loginId: string) => `dona.keep.testAccount.${loginId}`;

type Saved = { prefs: Prefs; drafts: Record<string, string>; cards: Record<string, CardStatus> };

/** 이 기기 기록을 지운다 (처음 설정 전 상태) */
function clearDevice() {
  prefs.reset();
  drafts.reset();
  resetCardState();
  storage.removeItem(HOME_CACHE);
}

/** 이 기기 기록을 그 계정 몫으로 보관한다 */
function saveDevice(loginId: string) {
  const saved: Saved = { prefs: prefs.read(), drafts: drafts.read(), cards: cardStateSnapshot() };
  storage.setItem(savedKey(loginId), JSON.stringify(saved));
}

/** 보관해 둔 그 계정 기록을 되살린다. 없으면 처음 상태로 둔다 */
function restoreDevice(loginId: string) {
  clearDevice();
  const raw = storage.getItem(savedKey(loginId));
  if (!raw) return;
  try {
    const saved = JSON.parse(raw) as Saved;
    prefs.replace(saved.prefs);
    drafts.replace(saved.drafts);
    restoreCardState(saved.cards);
  } catch {
    /* 망가진 보관본이면 처음 상태로 시작한다 */
  }
}

/** 테스트 계정으로 로그인했을 때 (네이버 로그인 결과를 받은 직후, 처음 설정을 마쳤는지 보기 전에 부른다).
 * 기기 기록을 지우거나(reset) 되살리고(keep), 서버가 옮긴 시계를 앱도 다시 읽는다. */
export async function onTestLogin(test: TestAccount): Promise<void> {
  if (test.onLogout === "reset") clearDevice();
  else restoreDevice(test.loginId);
  await refreshServerClock();
}

/** 테스트 계정으로 로그아웃할 때 (계정 정보를 지우기 전에 부른다). 서버에 알리고 조건대로 기기 기록을 지우거나 보관한다 */
export async function onTestLogout(): Promise<void> {
  const test = naverProfile.read().value?.testAccount;
  if (!test) return;
  if (test.onLogout === "keep") saveDevice(test.loginId);
  try {
    await fetch(`${BASE_URL}/api/auth/test/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login_id: test.loginId }),
    });
  } catch {
    /* 서버에 닿지 않아도 이 기기 쪽은 처리한다 */
  }
  // reset: 처음부터 다시 하게 지운다 → 시작 화면. keep: 그대로 둔다 → "다시 오셨네요" 로그인 화면
  if (test.onLogout === "reset") clearDevice();
  await refreshServerClock();
}
