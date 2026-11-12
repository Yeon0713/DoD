// 이 기기에 저장하는 값. 웹의 localStorage 대신 AsyncStorage를 쓴다.
// AsyncStorage는 비동기라서, 앱을 열 때(_layout.tsx) 한 번 모두 읽어 메모리에 올려 두고
// 화면 코드에서는 동기로 읽는다. 쓰기는 메모리에 바로 반영하고 뒤에서 저장한다.
import AsyncStorage from "@react-native-async-storage/async-storage";

const PREFIX = "dona.";
const mem = new Map<string, string>();
let ready = false;

// 실제 서버에 붙었을 때(EXPO_PUBLIC_USE_MOCK=false): 서버를 다시 켜면 앱도 처음 상태로 시작한다.
// 서버 /health 의 boot_id 는 서버가 켜질 때마다 바뀐다. 지난번에 본 값과 다르면 이 기기에 저장한 값(가입, 처음 쓰는 날,
// 끝낸 카드, 고쳐 쓴 답글 등)을 모두 지운다. 같은 서버가 켜져 있는 동안에는 새로 고침해도 지우지 않는다.
// api.ts 를 가져오면 순환 참조가 생겨서 환경 변수를 여기서 직접 읽는다.
const USE_SERVER = process.env.EXPO_PUBLIC_USE_MOCK === "false";
const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const BOOT_KEY = `${PREFIX}serverBoot`;
// 서버를 다시 켜거나 "처음 상태로"를 눌러도 남기는 값 (시험용 스위치: 데모 테스트 모드, 시연용 마우스 표시)
const KEEP_PREFIX = `${PREFIX}keep.`;
const wiped = (k: string) => !k.startsWith(KEEP_PREFIX);

// 로컬 시험용 시계 앞당김(분). 서버를 DEV_CLOCK_ENABLED=true 로 켜고 /dev/clock 으로 옮기면 /health 가 알려 준다.
// "다음 날 다시 열기"를 시험할 때 앱도 서버와 같은 날을 보게 한다 (time.ts nowFrom).
let clockShiftMinutes = 0;
export function serverClockShiftMs(): number {
  return clockShiftMinutes * 60 * 1000;
}

async function serverBootId(): Promise<string | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 2000);
  try {
    const res = await fetch(`${BASE_URL}/health`, { signal: controller.signal });
    const body = (await res.json()) as { boot_id?: string; clock_shift_minutes?: number };
    clockShiftMinutes = body.clock_shift_minutes ?? 0;
    return body.boot_id ?? null;
  } catch {
    return null; // 서버가 꺼져 있으면 지우지 않는다
  } finally {
    clearTimeout(timer);
  }
}

export async function hydrateStorage(): Promise<void> {
  if (ready) return;
  try {
    const keys = (await AsyncStorage.getAllKeys()).filter((k) => k.startsWith(PREFIX));
    const pairs = await AsyncStorage.multiGet(keys);
    for (const [k, v] of pairs) if (v !== null) mem.set(k, v);
    if (USE_SERVER) {
      const boot = await serverBootId();
      if (boot && mem.get(BOOT_KEY) !== boot) {
        await AsyncStorage.multiRemove(keys.filter(wiped));
        for (const k of [...mem.keys()]) if (wiped(k)) mem.delete(k);
        mem.set(BOOT_KEY, boot);
        await AsyncStorage.setItem(BOOT_KEY, boot);
      }
    }
  } catch {
    /* 읽지 못하면 빈 상태로 시작한다 */
  }
  ready = true;
}

export const storage = {
  getItem(key: string): string | null {
    return mem.get(key) ?? null;
  },
  setItem(key: string, value: string) {
    mem.set(key, value);
    AsyncStorage.setItem(key, value).catch(() => {});
  },
  removeItem(key: string) {
    mem.delete(key);
    AsyncStorage.removeItem(key).catch(() => {});
  },
  /** 개발 화면의 "처음부터 다시": 도나가 저장한 값을 모두 지운다 (시험용 스위치 dona.keep.* 는 남긴다). */
  clearAll() {
    const keys = [...mem.keys()].filter(wiped);
    for (const k of keys) mem.delete(k);
    AsyncStorage.multiRemove(keys).catch(() => {});
  },
};

/** 앱이 켜져 있는 동안만 두는 값 (웹의 sessionStorage 자리) */
export const session = new Map<string, string>();
