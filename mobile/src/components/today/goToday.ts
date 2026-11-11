// 일을 마치고 홈으로 돌아간다. 위에 쌓인 화면(지금 할 일, 답글, 점검, 잠금)을 닫고 홈 탭을 연다.
import { router, type Href } from "expo-router";

export function goToday() {
  if (router.canDismiss()) router.dismissAll();
  router.navigate("/");
}

/** 알림을 누르면 홈을 깔고 그 카드의 "지금 할 일"(07-3)을 연다. 뒤로 가면 홈이다. */
export function goTask(cardId: string) {
  goToday();
  router.push(`/task?id=${encodeURIComponent(cardId)}` as Href);
}
