import { Redirect, useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';

import { CenterMessage, FailNote, JoinPage } from '@/components/join';
import { Button } from '@/components/ui';
import { join, joinState, OwnerCheckResult } from '@/lib/join';
import { useSession } from '@/lib/session';
import { useEnterApp } from '@/lib/useEnterApp';
import { colors, space } from '@/theme/tokens';

// 사장님 확인 심사 (이전 앱 OwnerReviewScreen). 결과가 나올 때까지 1.5초마다 다시 본다.
// 승인: 계정과 가게가 이어졌다 → 음성 백엔드에 가게를 만들고(없으면) 가게 정보 확인으로. 설정에서 왔으면(again) 그 가게로 앱에 들어간다.
// 보류: 까닭과 다시 쓰기, 다른 가게예요.
export default function OwnerReviewScreen() {
  const router = useRouter();
  const session = useSession();
  const enterApp = useEnterApp();
  const again = useLocalSearchParams<{ again?: string }>().again === '1';
  const { checkId, storeId, storeName } = joinState.check;
  const [result, setResult] = useState<OwnerCheckResult | null>(null);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(0);
  const [moving, setMoving] = useState(false);

  useEffect(() => {
    if (!checkId) return;
    let alive = true;
    join
      .ownerResult(checkId)
      .then((r) => {
        if (!alive) return;
        setResult(r);
        if (r.status === 'reviewing') setTimeout(() => alive && setTick((n) => n + 1), 1500);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [checkId, tick]);

  if (!checkId || !storeId) return <Redirect href="/join/owner-check" />;
  const rewrite = () => router.replace(again ? '/join/owner-check?again=1' : '/join/owner-check');

  const next = async () => {
    setMoving(true);
    try {
      if (again) return await enterApp(storeId); // 우리 가게를 바꿨다 → 그 가게로
      await join.enter(storeId); // 음성 백엔드에 가게를 만들어 둔다 (가게 정보 확인에서 장사 시간을 고칠 수 있게)
      session.setAccount({ storeId, storeName });
      router.replace('/join/store-info');
    } catch {
      setMoving(false);
      setFailed(true);
    }
  };

  if (failed) {
    return (
      <JoinPage progress={again ? undefined : 3} onBack={rewrite} footer={<Button label="다시 보기" onPress={() => (setFailed(false), setTick((n) => n + 1))} />}>
        <FailNote title="심사 결과를 읽지 못했어요" />
      </JoinPage>
    );
  }
  if (!result || result.status === 'reviewing') {
    return (
      <JoinPage center progress={again ? undefined : 3} onBack={rewrite}>
        <CenterMessage img="q-clipboard" title="확인하고 있어요" sub="사업자등록증을 보고 있어요. 잠깐만 기다려 주세요">
          <View style={{ marginTop: space.s16 }}>
            <ActivityIndicator color={colors.brand} size="large" />
          </View>
        </CenterMessage>
      </JoinPage>
    );
  }
  if (result.status === 'approved') {
    return (
      <JoinPage center progress={again ? undefined : 3} footer={<Button label={moving ? '여는 중' : '다음'} onPress={() => !moving && void next()} />}>
        <CenterMessage img="b1-2" title="사장님 확인이 끝났어요" sub="이제 이 계정으로 우리 가게를 볼 수 있어요" />
      </JoinPage>
    );
  }
  return (
    <JoinPage
      center
      progress={again ? undefined : 3}
      onBack={rewrite}
      footer={
        <>
          <Button label="다시 쓰기" onPress={rewrite} />
          {result.reason_code === 'OTHER_STORE' || result.reason_code === 'TAKEN' ? (
            <Button kind="outline" label="가게 다시 찾기" onPress={() => router.replace(again ? '/join/store?again=1' : '/join/store')} />
          ) : null}
        </>
      }
    >
      <CenterMessage img="q-shrug" title={result.reason_title ?? '확인하지 못했어요'} sub={result.reason_sub ?? '다시 써 주세요'} />
    </JoinPage>
  );
}
