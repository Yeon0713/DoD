// 개발자 모드(/dev) 탭과 시연 화면(/demo)·사장님 앱 사이의 통로. 같은 주소(8090)의 탭끼리만 오간다 (BroadcastChannel).
// 웹 개발 모드에서만 연다. 앱(iOS, 안드로이드)이나 배포한 웹에서는 아무것도 하지 않는다.
//
//   /dev → 사장님 앱   say    사장님 말 (마이크 대신). 마이크로 들은 말과 같은 길을 탄다 ("도나야"를 붙여야 부른 말)
//   /dev → /demo       view   시연 화면에 보일 것 (전체, 사장님, 리뷰 플랫폼, 알바생)
//   /dev → /demo       reload 데이터를 처음부터 다시 넣었으니 휴대폰 화면을 다시 연다
//   사장님 앱 → /dev    heard  들은 말을 어떻게 했는지 (보냄, 부르지 않아 흘려들음 …)
//   사장님 앱 → /dev    turn   도나가 한 답 (머리글, 뜻, 말)
import { Platform } from 'react-native';

export type DemoView = 'all' | 'owner' | 'platform' | 'staff';
export const DEMO_VIEWS: { key: DemoView; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'owner', label: '사장님' },
  { key: 'platform', label: '리뷰 플랫폼' },
  { key: 'staff', label: '알바생' },
];

export type DevMessage =
  | { type: 'say'; text: string }
  | { type: 'view'; view: DemoView }
  | { type: 'reload' }
  | { type: 'staff_session'; token: string; staffId: string; name: string }
  | { type: 'heard'; text: string; result: 'sent' | 'uncalled' | 'too_short' }
  | { type: 'turn'; said: string | null; headline: string | null; kind: string; intent: string; say: string[] };

const NAME = 'donna-dev';
const usable = () => Platform.OS === 'web' && __DEV__ && typeof BroadcastChannel !== 'undefined';

export function sendDev(message: DevMessage) {
  if (!usable()) return;
  const channel = new BroadcastChannel(NAME);
  channel.postMessage(message);
  channel.close();
}

/** 받기. 돌려준 함수로 끊는다. */
export function onDev(handler: (message: DevMessage) => void): () => void {
  if (!usable()) return () => {};
  const channel = new BroadcastChannel(NAME);
  channel.onmessage = (event) => handler(event.data as DevMessage);
  return () => channel.close();
}
