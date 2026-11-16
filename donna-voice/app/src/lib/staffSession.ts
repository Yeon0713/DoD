// 알바생 앱이 이 기기에 기억하는 것: 초대 코드와 알바생 번호. 앱을 깔지 않고 주소로 들어오므로 브라우저에 둔다.
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'donna.staff';
type Saved = { code?: string; staffId?: string; name?: string };
let cache: Saved = {};

export const staffSession = {
  async load(): Promise<Saved> {
    try {
      cache = JSON.parse((await AsyncStorage.getItem(KEY)) ?? '{}');
    } catch {
      cache = {};
    }
    return cache;
  },
  get: () => cache,
  async set(patch: Saved) {
    cache = { ...cache, ...patch };
    await AsyncStorage.setItem(KEY, JSON.stringify(cache)).catch(() => {});
  },
  async clear() {
    cache = {};
    await AsyncStorage.removeItem(KEY).catch(() => {});
  },
};
