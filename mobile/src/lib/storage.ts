// 이 기기에 저장하는 값. 웹의 localStorage 대신 AsyncStorage를 쓴다.
// AsyncStorage는 비동기라서, 앱을 열 때(_layout.tsx) 한 번 모두 읽어 메모리에 올려 두고
// 화면 코드에서는 동기로 읽는다. 쓰기는 메모리에 바로 반영하고 뒤에서 저장한다.
import AsyncStorage from "@react-native-async-storage/async-storage";

const PREFIX = "dona.";
const mem = new Map<string, string>();
let ready = false;

export async function hydrateStorage(): Promise<void> {
  if (ready) return;
  try {
    const keys = (await AsyncStorage.getAllKeys()).filter((k) => k.startsWith(PREFIX));
    const pairs = await AsyncStorage.multiGet(keys);
    for (const [k, v] of pairs) if (v !== null) mem.set(k, v);
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
  /** 개발 화면의 "처음부터 다시": 도나가 저장한 값을 모두 지운다. */
  clearAll() {
    const keys = [...mem.keys()];
    mem.clear();
    AsyncStorage.multiRemove(keys).catch(() => {});
  },
};

/** 앱이 켜져 있는 동안만 두는 값 (웹의 sessionStorage 자리) */
export const session = new Map<string, string>();
