import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { setStoreId } from './api';

// 이 기기에 기억해 두는 것: 로그인했는지(무엇으로, 어느 가게로), 마이크를 허용했는지, 소리를 켰는지.
// 가입 흐름(이전 앱 mobile/ 에서 옮김)은 가게 등록과 사장님 확인을 마친 뒤에 signedIn 을 켠다. 그 전까지는 계정 칸만 채운다.
export type MicState = 'unknown' | 'granted' | 'denied' | 'later' | 'unsupported';
/** 무엇으로 로그인했는지 (설정 > 계정, G-07) */
export type LoginMethod = 'naver' | 'phone';
/** 네이버 로그인으로 받은 것 (임시 네이버 로그인이면 테스트 계정 조건도) */
export type NaverAccount = { id: string | null; name: string | null; test: boolean; loginId: string | null; onLogout: 'reset' | 'keep' | null };

type Saved = {
  signedIn: boolean;
  mic: MicState;
  sound: boolean;
  login: LoginMethod | null;
  phone: string | null;
  naver: NaverAccount | null;
  /** 이 계정의 가게 (가입하면 등록한 가게, 데모 계정 dona_demo 는 초옹장 s005) */
  storeId: string | null;
  storeName: string | null;
};
const KEY = 'donna.voice.session.v1';
// 데모 테스트 모드는 로그아웃, 탈퇴, 처음 상태로 돌리기에도 남긴다 (시험하는 사람의 스위치)
const DEMO_KEY = 'donna.voice.demo.v1';
const INITIAL: Saved = { signedIn: false, mic: 'unknown', sound: true, login: null, phone: null, naver: null, storeId: null, storeName: null };

type Session = Saved & {
  ready: boolean;
  demo: boolean;
  setDemo: (on: boolean) => void;
  /** 가입하는 동안 계정 칸을 채운다 (아직 앱에 들어가지 않음) */
  setAccount: (patch: Partial<Pick<Saved, 'login' | 'phone' | 'naver' | 'storeId' | 'storeName'>>) => void;
  /** 가입·로그인을 마치고 그 가게로 앱에 들어간다 */
  enter: (storeId: string, storeName: string | null) => void;
  /** 로그아웃·탈퇴: 계정과 가게를 지운다. 마이크는 다시 묻는다 */
  signOut: () => void;
  /** 이 기기를 처음 상태로 (시작 화면 메뉴) */
  resetDevice: () => void;
  setMic: (m: MicState) => void;
  setSound: (on: boolean) => void;
};

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [saved, setSaved] = useState<Saved>(INITIAL);
  const [demo, setDemoState] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    Promise.all([AsyncStorage.getItem(KEY), AsyncStorage.getItem(DEMO_KEY)])
      .then(([raw, demoRaw]) => {
        if (raw) {
          const next = { ...INITIAL, ...JSON.parse(raw) } as Saved;
          setStoreId(next.storeId);
          setSaved(next);
        }
        if (demoRaw) setDemoState(JSON.parse(demoRaw).on === true);
      })
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);

  const update = useCallback((patch: Partial<Saved>) => {
    setSaved((prev) => {
      const next = { ...prev, ...patch };
      // 앱이 부르는 가게는 이 계정의 가게다 (가입 중에도 사장님 확인을 마치면 그 가게). 없으면 시연 가게
      setStoreId(next.storeId);
      AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);

  const value = useMemo<Session>(
    () => ({
      ...saved,
      ready,
      demo,
      setDemo: (on) => {
        setDemoState(on);
        AsyncStorage.setItem(DEMO_KEY, JSON.stringify({ on })).catch(() => {});
      },
      setAccount: (patch) => update(patch),
      enter: (storeId, storeName) => update({ signedIn: true, storeId, storeName }),
      signOut: () => update({ signedIn: false, mic: 'unknown', login: null, phone: null, naver: null, storeId: null, storeName: null }),
      resetDevice: () => update({ ...INITIAL }),
      setMic: (mic) => update({ mic }),
      setSound: (sound) => update({ sound }),
    }),
    [saved, ready, demo, update],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const v = useContext(Ctx);
  if (!v) throw new Error('SessionProvider가 없습니다');
  return v;
}
