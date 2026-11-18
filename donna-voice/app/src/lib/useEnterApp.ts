import { useRouter } from 'expo-router';
import { useCallback } from 'react';

import { join } from './join';
import { useSession } from './session';

/** 가입·로그인을 마치고 그 가게로 앱에 들어간다. 음성 백엔드에 그 가게가 없으면 서버가 메인 데이터로 만든다.
 *  마이크를 아직 허용하지 않았으면 마이크 화면(E-03)을 거친다. 가입 화면으로 뒤로 가지 못하게 바꿔 끼운다. */
export function useEnterApp() {
  const router = useRouter();
  const session = useSession();
  return useCallback(
    async (storeId: string) => {
      const res = await join.enter(storeId);
      session.enter(res.store_id, res.name);
      if (router.canDismiss()) router.dismissAll();
      router.replace(session.mic === 'granted' ? '/' : '/mic');
    },
    [router, session],
  );
}
