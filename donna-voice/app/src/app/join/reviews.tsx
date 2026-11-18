import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { Icon, IconName } from '@/components/Icon';
import { JoinPage, Note, Sheet, TitleWithDonna } from '@/components/join';
import { Txt } from '@/components/Txt';
import { Button } from '@/components/ui';
import { join, ReviewSource } from '@/lib/join';
import { useSession } from '@/lib/session';
import { colors, radius, space } from '@/theme/tokens';

// 리뷰를 불러와 주세요 (이전 앱 06-2r). 배민, 네이버, 쿠팡이츠를 하나씩. 안 불러오고 넘어가려 하면 한 번 묻는다.
// 서버는 시험용으로 3초 기다린 뒤 가게 파일의 리뷰를 플랫폼별로 나눠 표시한다 (목업 가게는 있는 리뷰, 새로 등록한 가게는 목업 리뷰).
const SOURCES: { key: ReviewSource; name: string; icon: IconName }[] = [
  { key: 'BAEMIN', name: '배달의민족', icon: 'scooter' },
  { key: 'NAVER', name: '네이버', icon: 'store' },
  { key: 'COUPANG', name: '쿠팡이츠', icon: 'truck' },
];
type Load = { kind: 'idle' } | { kind: 'loading' } | { kind: 'done'; count: number } | { kind: 'failed' };
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function ReviewImportScreen() {
  const router = useRouter();
  const { storeId } = useSession();
  const [states, setStates] = useState<Partial<Record<ReviewSource, Load>>>({});
  const [asking, setAsking] = useState(false);
  // 이미 불러온 곳은 처음부터 "불러왔어요" (다시 들어와도 같은 리뷰를 또 넣지 않는다)
  useEffect(() => {
    if (!storeId) return;
    join
      .importedReviews(storeId)
      .then((r) => setStates((s) => {
        const next = { ...s };
        for (const src of SOURCES) if (!next[src.key] && (r.imported[src.key] ?? 0) > 0) next[src.key] = { kind: 'done', count: r.imported[src.key] };
        return next;
      }))
      .catch(() => {});
  }, [storeId]);

  const stateOf = (k: ReviewSource): Load => states[k] ?? { kind: 'idle' };
  const load = async (k: ReviewSource) => {
    setStates((s) => ({ ...s, [k]: { kind: 'loading' } }));
    try {
      if (!storeId) throw new Error('NO_STORE');
      const [res] = await Promise.all([join.importReviews(storeId, k), wait(3000)]);
      setStates((s) => ({ ...s, [k]: { kind: 'done', count: res.imported } }));
    } catch {
      setStates((s) => ({ ...s, [k]: { kind: 'failed' } }));
    }
  };
  const missing = SOURCES.filter((s) => stateOf(s.key).kind !== 'done');
  const anyLoading = SOURCES.some((s) => stateOf(s.key).kind === 'loading');
  const proceed = () => {
    setAsking(false);
    router.push('/join/notify');
  };

  return (
    <>
      <JoinPage
        progress={5}
        onBack={() => router.replace('/join/store-info')}
        footer={<Button label="다음" disabled={anyLoading} onPress={() => (missing.length ? setAsking(true) : proceed())} />}
      >
        <TitleWithDonna title="리뷰를 불러와 주세요" img="b3-1" sub="답글을 쓰고 단골 손님을 찾을 때 써요" />
        <View style={styles.list}>
          {SOURCES.map((src, i) => {
            const st = stateOf(src.key);
            const done = st.kind === 'done';
            return (
              <View key={src.key} style={[styles.row, i > 0 && styles.rule]}>
                <View style={[styles.tile, { backgroundColor: done ? colors.doneSoft : colors.brandSoft }]}>
                  <Icon name={src.icon} size={24} color={done ? 'done' : 'brand'} />
                </View>
                <View style={{ flex: 1 }}>
                  <Txt variant="bodyStrong" style={styles.bold}>
                    {src.name}
                  </Txt>
                  <Txt variant="label" color={done ? 'done' : st.kind === 'failed' ? 'urgent' : 'ink2'}>
                    {done ? `리뷰 ${st.count}개를 불러왔어요` : st.kind === 'loading' ? '불러오는 중이에요' : st.kind === 'failed' ? '불러오지 못했어요' : '아직 안 불러왔어요'}
                  </Txt>
                </View>
                {st.kind === 'loading' ? (
                  <ActivityIndicator color={colors.brand} />
                ) : done ? (
                  <View style={[styles.check, { backgroundColor: colors.doneSoft }]}>
                    <Icon name="check" size={18} color="done" />
                  </View>
                ) : (
                  <Pressable onPress={() => void load(src.key)} accessibilityRole="button" accessibilityLabel={`${src.name} 리뷰 불러오기`} style={styles.loadBtn}>
                    <Txt variant="label" color="brand" style={styles.bold}>
                      {st.kind === 'failed' ? '다시' : '불러오기'}
                    </Txt>
                  </Pressable>
                )}
              </View>
            );
          })}
        </View>
        <View style={{ marginTop: space.s16 }}>
          <Note>사장님 계정으로 리뷰만 읽어 와요. 답글은 사장님이 누르기 전엔 올리지 않아요</Note>
        </View>
      </JoinPage>
      <Sheet open={asking} onClose={() => setAsking(false)} title="리뷰를 아직 불러오지 않았어요">
        <Txt variant="body" color="ink2">{`${missing.map((m) => m.name).join(', ')} 리뷰를 불러오지 않았어요. 먼저 불러올까요?`}</Txt>
        <View style={{ gap: space.s8 }}>
          <Button label="먼저 불러올게요" onPress={() => setAsking(false)} />
          <Button kind="outline" label="불러오지 않고 넘어갈게요" onPress={proceed} />
        </View>
      </Sheet>
    </>
  );
}

const styles = StyleSheet.create({
  bold: { fontFamily: 'NotoSansKR_700Bold' },
  list: { marginTop: space.s16, borderRadius: radius.item, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface, overflow: 'hidden' },
  row: { minHeight: 76, flexDirection: 'row', alignItems: 'center', gap: space.s12, paddingHorizontal: space.s16, paddingVertical: space.s12 },
  rule: { borderTopWidth: 1, borderTopColor: colors.line },
  tile: { width: 44, height: 44, borderRadius: radius.tile, alignItems: 'center', justifyContent: 'center' },
  check: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  loadBtn: { height: 40, paddingHorizontal: space.s12, borderRadius: radius.tile, borderWidth: 1, borderColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
});
