// 서버 주소를 정하는 한 곳. api.ts, storage.ts, naverDemo.ts, 시작 화면 메뉴가 모두 여기서 읽는다.
// 다른 파일을 가져오지 않는다 (storage.ts 가 앱을 열 때 가장 먼저 쓰기 때문에 순환 참조가 생기면 안 된다).
const RAW = (process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
const THIS_COMPUTER = new Set(["127.0.0.1", "localhost", "[::1]"]);

/** 웹에서는 앱을 연 주소와 같은 이름으로 서버를 부른다.
 *
 * 설정이 `http://127.0.0.1:8000` 인데 앱을 `http://localhost:8082` 로 열었다면 서버도 `http://localhost:8000` 으로 부른다.
 * 컴퓨터에 따라 localhost 는 되는데 127.0.0.1 은 안 닿는 경우가 있어서(WSL, 도커, IPv6), 브라우저에서 이미 열린 이름을 따라간다.
 * 설정이 내 컴퓨터가 아닌 주소(배포 서버, 같은 와이파이 IP)면 그대로 쓴다. 휴대폰 앱(네이티브)도 그대로 쓴다.
 */
function sameHostAsPage(raw: string): string {
  const page = typeof window !== "undefined" ? window.location?.hostname : undefined;
  if (!page) return raw;
  try {
    const url = new URL(raw);
    if (!THIS_COMPUTER.has(url.hostname) || url.hostname === page) return raw;
    url.hostname = page;
    return url.origin;
  } catch {
    return raw;
  }
}

export const BASE_URL = sameHostAsPage(RAW);

export type ServerHealth = {
  boot_id?: string;
  /** 서버를 시험용(DEV_CLOCK_ENABLED=true, python run_dev.py)으로 켰는지. 초기화와 시계 앞당기기가 열린다 */
  dev_mode?: boolean;
  clock_shift_minutes?: number;
};

/** 서버가 살아 있는지 본다. 닿지 않거나 timeoutMs 안에 답이 없으면 null */
export async function serverHealth(timeoutMs = 2000): Promise<ServerHealth | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE_URL}/health`, { signal: controller.signal });
    return res.ok ? ((await res.json()) as ServerHealth) : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
