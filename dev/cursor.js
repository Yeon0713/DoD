// 시연용 마우스 표시 (개발자 대시보드). 화면을 녹화하거나 원격으로 보여 줄 때 어디를 누르는지 보이게 커서와 누르는 동작을 그린다.
// 주소에 ?cursor=1 을 붙이면 켜지고 ?cursor=0 이면 꺼진다. 켠 상태는 이 브라우저에 기억한다.
// 앱의 mobile/src/components/dev/DemoCursor.tsx 와 모양·움직임이 같다 (휴대폰 틀 속 앱은 그 파일이 그린다).
(function demoCursor() {
  const KEY = "dona-dev-cursor";
  const BRAND = "#6f4220";
  try {
    const q = new URLSearchParams(location.search).get("cursor");
    if (q === "1") localStorage.setItem(KEY, "1");
    if (q === "0") localStorage.removeItem(KEY);
    if (localStorage.getItem(KEY) !== "1") return;
  } catch {
    return;
  }

  const layer = document.createElement("div");
  layer.setAttribute("aria-hidden", "true");
  layer.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:2147483647;overflow:hidden;";
  const cursor = document.createElement("div");
  // 순간 이동하지 않고 미끄러지듯 움직이게 transform 에 전환을 건다
  cursor.style.cssText =
    "position:absolute;left:0;top:0;width:28px;height:34px;opacity:0;" +
    "transform:translate(-100px,-100px);transition:transform 450ms cubic-bezier(.25,.8,.3,1),opacity 200ms;" +
    "filter:drop-shadow(0 2px 3px rgba(0,0,0,.35));will-change:transform;";
  cursor.innerHTML =
    '<svg width="28" height="34" viewBox="0 0 28 34" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M3 2 L3 27 L9.5 21 L14 31.5 L18.5 29.5 L14 19.5 L23 19.5 Z" fill="#ffffff" stroke="#1f140c" stroke-width="2" stroke-linejoin="round"/></svg>';
  const arrow = cursor.firstElementChild;
  arrow.style.cssText = "display:block;transform-origin:3px 2px;transition:transform 120ms ease-out;";
  layer.appendChild(cursor);
  document.body.appendChild(layer);

  let x = -100;
  let y = -100;
  const moveTo = (nx, ny) => {
    x = nx;
    y = ny;
    cursor.style.opacity = "1";
    cursor.style.transform = `translate(${nx - 3}px, ${ny - 2}px)`;
  };

  // 누른 자리에 퍼지는 원 두 겹과 커서가 눌리는 움직임
  const ripple = (cx, cy) => {
    for (const [size, delay] of [[56, 0], [86, 90]]) {
      const ring = document.createElement("div");
      ring.style.cssText =
        `position:absolute;left:${cx - size / 2}px;top:${cy - size / 2}px;width:${size}px;height:${size}px;border-radius:50%;` +
        `border:3px solid ${BRAND};background:rgba(111,66,32,.18);transform:scale(.2);opacity:.95;`;
      layer.insertBefore(ring, cursor);
      ring.animate([{ transform: "scale(.2)", opacity: 0.95 }, { transform: "scale(1)", opacity: 0 }], {
        duration: 650, delay, easing: "cubic-bezier(.2,.7,.3,1)", fill: "forwards",
      }).onfinish = () => ring.remove();
    }
    arrow.style.transform = "scale(.82)";
    setTimeout(() => (arrow.style.transform = "scale(1)"), 160);
  };

  window.addEventListener("pointermove", (e) => moveTo(e.clientX, e.clientY), { capture: true, passive: true });
  window.addEventListener("pointerdown", (e) => {
    // 움직임 없이 바로 누른 경우에도 커서가 그 자리로 간다
    if (Math.abs(e.clientX - x) > 1 || Math.abs(e.clientY - y) > 1) moveTo(e.clientX, e.clientY);
    ripple(e.clientX, e.clientY);
  }, { capture: true, passive: true });
  document.documentElement.addEventListener("pointerleave", () => (cursor.style.opacity = "0"));
})();
