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

/** 뒤로. 쌓인 화면이 없으면(앱을 주소로 바로 연 경우) fallback으로 간다. */
export function back(fallback = "/") {
  if (router.canGoBack()) router.back();
  else router.replace(fallback as Href);
}
