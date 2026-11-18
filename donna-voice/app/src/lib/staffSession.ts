// 알바생 앱이 이 기기에 기억하는 것: 초대 코드, 알바생 번호, 로그인 표시(토큰). 앱을 깔지 않고 주소로 들어오므로 브라우저에 둔다.
// 토큰은 가입하거나 아이디·비밀번호로 들어오면 서버가 준다. 알바생 요청마다 X-Staff-Token 으로 붙인다 (lib/api.ts).
// 서버가 토큰을 모른다고 하면(not_signed_in: 처음부터 다시, 사장님이 내보냄) clear() 하고 입장 화면으로 간다.
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'donna.staff';
type Saved = { code?: string; staffId?: string; name?: string; token?: string };
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
