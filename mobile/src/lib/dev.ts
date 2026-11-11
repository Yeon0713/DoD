// 검토용 스위치. Next.js 판에서는 주소 뒤에 ?now=, ?fail=1, ?offline=1, ?delay=, ?card= 를 붙였다.
// 앱에는 주소창이 없어서 개발 화면(/dev)에서 고르고 이 기기에 저장한다.
import { createStore } from "./store";

export interface DevFlags {
  /** 가상 시각 "2026-11-18T10:05" (서울). 비우면 데모 기준 시각 */
  now: string | null;
  /** 올리기, 바꾸기 같은 동작을 일부러 실패시킨다 (05-5f) */
  fail: boolean;
  /** 인터넷이 끊긴 화면 (05-9, 05-7E) */
  offline: boolean;
  /** 목업 응답을 늦추는 시간(ms). null이면 기본 600 */
  delay: number | null;
  /** 오늘 화면에서 이 카드를 맨 앞으로 */
  card: string | null;
  /** 저장해 둔 홈 데이터를 쓰지 않는다 */
  fresh: boolean;
  /** 데모 한 주(월~다음 주 수)의 할 일 카드를 모두 홈에 모아 보여 준다. Figma 06의 카드를 한곳에서 다 볼 수 있다. 끄면 가상 시각까지 온 카드만 */
  allWeek: boolean;
  /** 모아 보기에서 카드 하나를 열면 그 카드가 온 시각. 그 카드의 화면(답글, 메뉴판, 포스터)은 이 시각을 지금으로 본다. 홈으로 돌아오면 비운다 */
  scene: string | null;
}

export const devFlags = createStore<DevFlags>("dona.dev.v1", {
  now: null,
  fail: false,
  offline: false,
  delay: null,
  card: null,
  fresh: false,
  allWeek: true,
  scene: null,
});
