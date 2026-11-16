import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

// 이 기기에 기억해 두는 것: 로그인했는지, 마이크를 허용했는지, 소리를 켰는지.
export type MicState = 'unknown' | 'granted' | 'denied' | 'later' | 'unsupported';
type Saved = { signedIn: boolean; mic: MicState; sound: boolean };
const KEY = 'donna.voice.session.v1';
const INITIAL: Saved = { signedIn: false, mic: 'unknown', sound: true };

type Session = Saved & {
  ready: boolean;
  signIn: () => void;
  signOut: () => void;
  setMic: (m: MicState) => void;
  setSound: (on: boolean) => void;
};

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [saved, setSaved] = useState<Saved>(INITIAL);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((raw) => raw && setSaved({ ...INITIAL, ...JSON.parse(raw) }))
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);

  const update = useCallback((patch: Partial<Saved>) => {
    setSaved((prev) => {
      const next = { ...prev, ...patch };
      AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);

  const value = useMemo<Session>(
    () => ({
      ...saved,
      ready,
      signIn: () => update({ signedIn: true }),
      signOut: () => update({ signedIn: false, mic: 'unknown' }),
      setMic: (mic) => update({ mic }),
      setSound: (sound) => update({ sound }),
    }),
    [saved, ready, update],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const v = useContext(Ctx);
  if (!v) throw new Error('SessionProvider가 없습니다');
  return v;
}
