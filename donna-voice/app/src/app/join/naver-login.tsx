import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';

import { CenterMessage, JoinPage } from '@/components/join';
import { Button } from '@/components/ui';
import { goToNaverLogin, join, naverErrorText, serverUp } from '@/lib/join';
import { useSession } from '@/lib/session';
import { useEnterApp } from '@/lib/useEnterApp';

// 네이버 로그인 (이전 앱 08-1n NaverLoginScreen).
// 이 탭을 서버의 네이버 로그인으로 옮겼다가(/api/auth/naver/start), 로그인과 동의를 마치면 서버가 ?ticket= 을 달고 여기로 돌려보낸다.
// 서버에 네이버 앱 키가 없으면 서버가 그리는 임시 네이버 로그인 화면이 나오고, DB 테스트 계정(server/db/test_accounts.db)으로 들어간다.
// 키가 없을 때는 데모 테스트 모드에서만 연다 (이전 앱과 같다). 이 계정에 등록해 둔 가게가 있으면 바로 앱으로, 없으면 가게 찾기부터.
export default function NaverLoginScreen() {
  const router = useRouter();
  const session = useSession();
  const enterApp = useEnterApp();
  const params = useLocalSearchParams<{ ticket?: string; error?: string; mode?: string }>();
  const [tries, setTries] = useState(0);
  const [fail, setFail] = useState<{ title: string; sub: string } | null>(null);
  const ran = useRef(-1);
  const ticket = tries === 0 ? params.ticket : undefined;
  const error = tries === 0 ? params.error : undefined;

  useEffect(() => {
    if (ran.current === tries) return; // 개발 모드에서 효과가 두 번 돌아도 한 번만
    ran.current = tries;
    (async () => {
      if (error) throw new Error(error);
      if (ticket) {
        const r = await join.naverResult(ticket).catch(() => {
          throw new Error('TICKET_EXPIRED');
        });
        const t = r.test_account;
        session.setAccount({
          login: 'naver',
          phone: null,
          naver: { id: r.received.id ?? null, name: r.received.name ?? null, test: r.test, loginId: t?.login_id ?? null, onLogout: t?.on_logout ?? null },
          storeId: null,
          storeName: null,
        });
        // 이 네이버 계정으로 가게 등록과 사장님 확인을 마쳤으면(다시 온 사장님) 처음 설정 없이 바로 앱으로
        if (r.store_id) await enterApp(r.store_id);
        else router.replace('/join/store');
        return;
      }
      const config = await join.config().catch(() => null);
      if (!config || !(await serverUp())) throw new Error('SERVER_UNREACHABLE');
      if (!config.naver_real && !session.demo) throw new Error('NOT_DEMO');
      goToNaverLogin(`/join/naver-login${params.mode === 'login' ? '?mode=login' : ''}`);
    })().catch((e: unknown) => setFail(naverErrorText(e instanceof Error ? e.message : 'UNKNOWN')));
  }, [tries, ticket, error, params.mode, router, session, enterApp]);

  const leave = () => router.replace(params.mode === 'login' ? '/join/login' : '/login');
  if (fail) {
    return (
      <JoinPage
        center
        onBack={leave}
        footer={
          <>
            <Button
              label="다시 하기"
              onPress={() => {
                setFail(null);
                setTries((n) => n + 1);
              }}
            />
            <Button kind="outline" label="휴대폰 번호로 시작하기" onPress={() => router.replace('/join/phone')} />
          </>
        }
      >
        <CenterMessage img="q-scratch" title={fail.title} sub={fail.sub} />
      </JoinPage>
    );
  }
  return (
    <JoinPage center onBack={leave}>
      <CenterMessage img="b4-0" title={ticket ? '네이버에서 정보를 받고 있어요' : '네이버 로그인 화면을 열고 있어요'} sub="잠깐만 기다려 주세요" />
    </JoinPage>
  );
}
