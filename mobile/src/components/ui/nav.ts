// 화면 이동 도우미. 카드와 버튼은 "/reply/abc?step=share" 같은 글자 주소를 쓴다 (Next.js 판과 같은 주소).
import { router, type Href } from "expo-router";

let last = { href: "", at: 0 };

/** 같은 곳을 연달아 두 번 누르면 화면이 두 장 쌓이지 않게 한 번만 연다. */
export function go(href: string) {
  const now = Date.now();
  if (last.href === href && now - last.at < 800) return;
  last = { href, at: now };
  router.push(href as Href);
}

export function replace(href: string) {
  router.replace(href as Href);
}

/** 일을 마치고 홈으로 돌아간다. 위에 쌓인 화면(지금 할 일, 답글, 점검, 포스터, 잠금)을 닫고 홈 탭을 연다. */
export function goHome() {
  if (router.canDismiss()) {
    router.dismissAll();
    router.navigate("/" as Href);
  } else {
    // 주소로 바로 연 화면(쌓인 화면 없음)은 홈으로 바꿔 끼운다. 그래야 뒤로 가기로 끝낸 화면에 돌아오지 않는다.
    router.replace("/" as Href);
  }
}

/** 홈을 깔고 그 카드의 "지금 할 일"(07-3)을 연다. 뒤로 가면 홈이다 (잠금 화면 알림). */
export function goTask(cardId: string) {
  goHome();
  router.push(`/task?id=${encodeURIComponent(cardId)}` as Href);
}

/** 뒤로. 쌓인 화면이 없으면(앱을 주소로 바로 연 경우) fallback으로 간다. */
export function back(fallback = "/") {
  if (router.canGoBack()) router.back();
  else router.replace(fallback as Href);
}
