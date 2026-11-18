import { useLocalSearchParams, useRouter } from 'expo-router';
import { createElement, useCallback, useEffect, useState } from 'react';
import { Platform as RNPlatform, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { Txt } from '@/components/Txt';
import { api, Platform } from '@/lib/api';
import { DEMO_VIEWS, DemoView, onDev } from '@/lib/devChannel';
import { useSession } from '@/lib/session';
import { staffSession } from '@/lib/staffSession';
import { colors, radius, space } from '@/theme/tokens';

// 발표 시연 화면 (웹, 개발 모드에서만). 팀 개선안 2026-11-18: "사장님은 화면을 안 봤는데, 뒤에서 실제 세상이 바뀌었다".
// 이 화면에는 세 화면만 있다. 시각 바꾸기, 손님 리뷰 넣기, 사장님 말은 다른 탭의 개발자 모드(/dev)에서 보낸다.
//   사장님       사장님 앱 (/ 를 휴대폰 크기 그대로)
//   리뷰 플랫폼   손님 리뷰와 올라간 답글 (GET /v1/dev/platform). 실제 플랫폼 화면을 흉내 내지 않는다
//   알바생       하린의 휴대폰. 아직 안 들어왔으면 예시 메신저(/demo-messenger, Figma F-01)에서 시작한다:
//                사장님 "하린이 초대해 줘" → "카카오톡으로 보내 줘" → 메신저에 글 도착 → 링크 → 코드 → 가입 → 할 일 (2026-11-18)
//                들어와 있으면(로그인 표시가 있으면) 할 일(/staff/today). '처음부터'를 하면 로그인 표시를 지운다.
// 보기: /demo?view=all | owner | platform | staff (위의 탭, 또는 /dev 의 '보는 화면'). 안 보이는 화면도 켜 둔다
// (리뷰 플랫폼만 볼 때도 사장님 앱이 알림을 받고 /dev 에서 보낸 말을 듣게).
// 이 화면은 /v1/notices 를 읽지 않는다 (알림은 한 번만 읽히므로 사장님 앱이 받아야 한다).
// 그래서 시연할 때 다른 탭에 사장님 앱(/)을 열어 두지 않는다. 먼저 읽은 쪽이 알림을 가져간다.
const PHONE = { width: 375, height: 812 };
const STAFF_START = '/demo-messenger?to=하린';
const isView = (v: unknown): v is DemoView => DEMO_VIEWS.some((d) => d.key === v);

export default function DemoScreen() {
  const session = useSession();
  const router = useRouter();
  const params = useLocalSearchParams<{ view?: string }>();
  const view: DemoView = isView(params.view) ? params.view : 'all';
  const [ready, setReady] = useState(false);
  const [round, setRound] = useState(0); // 개발자 모드에서 '처음부터'를 하면 두 휴대폰을 다시 연다
  const [platform, setPlatform] = useState<Platform | null>(null);
  const [staffSrc, setStaffSrc] = useState(STAFF_START);
  const [staffRound, setStaffRound] = useState(0);

  // 사장님 세션(초옹장)을 넣고, 알바생 휴대폰은 들어와 있으면 할 일, 아니면 메신저에서 연다
  useEffect(() => {
    session.enter('s005', '초옹장');
    void staffSession.load().then((s) => {
      setStaffSrc(s.token ? '/staff/today' : STAFF_START);
      setReady(true);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const setView = useCallback((next: DemoView) => router.setParams({ view: next }), [router]);
  useEffect(
    () =>
      onDev((m) => {
        if (m.type === 'view') setView(m.view);
        if (m.type === 'reload') {
          // 처음부터: 서버의 알바생 기록이 지워졌으니 알바생 휴대폰도 처음(메신저)으로
          void staffSession.clear().then(() => {
            setStaffSrc(STAFF_START);
            setRound((n) => n + 1);
          });
        }
        if (m.type === 'staff_session') {
          // 개발자 모드 '하린 바로 가입' (연습용): 받은 로그인 표시를 넣고 할 일 화면으로
          void staffSession.clear().then(() =>
            staffSession.set({ token: m.token, staffId: m.staffId, name: m.name }).then(() => {
              setStaffSrc('/staff/today');
              setStaffRound((n) => n + 1);
            }),
          );
        }
      }),
    [setView],
  );

  const loadPlatform = useCallback(() => api.dev.platform().then(setPlatform).catch(() => {}), []);
  useEffect(() => {
    void loadPlatform();
    const id = setInterval(loadPlatform, 2000);
    return () => clearInterval(id);
  }, [loadPlatform, round]);

  if (RNPlatform.OS !== 'web' || !__DEV__) {
    return (
      <View style={styles.page}>
        <Txt variant="body">시연 화면은 웹 개발 모드에서만 열려요.</Txt>
      </View>
    );
  }

  const shown = (key: Exclude<DemoView, 'all'>) => view === 'all' || view === key;
  return (
    <ScrollView style={styles.page} contentContainerStyle={{ padding: space.s16, gap: space.s16 }}>
      <View style={styles.tabs} accessibilityRole="tablist">
        {DEMO_VIEWS.map((d) => (
          <Pressable
            key={d.key}
            onPress={() => setView(d.key)}
            accessibilityRole="tab"
            accessibilityState={{ selected: view === d.key }}
            style={[styles.tab, view === d.key && styles.tabOn]}
          >
            <Txt variant="label" color={view === d.key ? 'brandInk' : 'brand'}>
              {d.label}
            </Txt>
          </Pressable>
        ))}
      </View>

      <View style={[styles.columns, view !== 'all' && { justifyContent: 'center' }]}>
        <Column title="사장님 (주방)" hidden={!shown('owner')} only={view === 'owner'}>
          {ready ? <Phone key={`owner-${round}`} src="/" allowMic /> : null}
        </Column>
        <Column title="리뷰 플랫폼 (예시 화면)" hidden={!shown('platform')} only={view === 'platform'}>
          <PlatformPanel data={platform} wide={view === 'platform'} />
        </Column>
        <Column title="알바생 하린" hidden={!shown('staff')} only={view === 'staff'}>
          {ready ? <Phone key={`staff-${round}-${staffRound}`} src={staffSrc} /> : null}
        </Column>
      </View>
    </ScrollView>
  );
}

function Phone({ src, allowMic }: { src: string; allowMic?: boolean }) {
  return createElement('iframe', {
    src,
    title: src,
    allow: allowMic ? 'microphone; autoplay' : 'autoplay',
    style: { width: PHONE.width, maxWidth: '100%', height: PHONE.height, border: `1px solid ${colors.line}`, borderRadius: 28, background: colors.paper },
  });
}

/** 한 칸. 안 보일 때도 지우지 않고 숨긴다 (사장님 앱이 계속 듣고 알림을 받게). */
function Column({ title, hidden, only, children }: { title: string; hidden: boolean; only: boolean; children: React.ReactNode }) {
  return (
    <View style={[{ gap: space.s8, maxWidth: '100%' }, hidden && { display: 'none' }]}>
      {only ? null : (
        <Txt variant="label" color="ink2" style={{ fontFamily: 'NotoSansKR_700Bold' }}>
          {title}
        </Txt>
      )}
      {children}
    </View>
  );
}

function Stars({ rating }: { rating: number }) {
  return (
    <View style={{ flexDirection: 'row', gap: 2 }}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Icon key={n} name="star" size={14} color={n <= rating ? 'busy' : 'line'} />
      ))}
    </View>
  );
}

function PlatformPanel({ data, wide }: { data: Platform | null; wide: boolean }) {
  return (
    <View style={[styles.panel, { width: wide ? 560 : PHONE.width + 45, maxWidth: '100%', height: PHONE.height }]}>
      <ScrollView contentContainerStyle={{ gap: space.s12, padding: space.s16 }}>
        {(data?.items ?? []).map((item) => (
          <View key={item.id} style={[styles.review, item.reply?.fresh && styles.fresh]}>
            <View style={styles.reviewHead}>
              <Stars rating={item.rating} />
              <Txt variant="small" color="ink2">
                {item.platform_label} · {item.written_label}
              </Txt>
            </View>
            {item.menus.length ? (
              <Txt variant="small" color="ink2">
                {item.menus.join(', ')}
              </Txt>
            ) : null}
            <Txt variant="body">{item.text}</Txt>
            {item.reply ? (
              <View style={styles.reply}>
                <Txt variant="small" color={item.reply.fresh ? 'urgent' : 'ink2'} style={{ fontFamily: 'NotoSansKR_700Bold' }}>
                  {item.reply.fresh ? '방금 올라온 사장님 답글' : `사장님 답글 · ${item.reply.posted_label}`}
                </Txt>
                <Txt variant="body" color="ink2">
                  {item.reply.text}
                </Txt>
              </View>
            ) : (
              <Txt variant="small" color="ink3">
                답글 없음
              </Txt>
            )}
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.home },
  tabs: { flexDirection: 'row', flexWrap: 'wrap', gap: space.s8 },
  tab: { paddingHorizontal: space.s12, height: 36, borderRadius: radius.pill, backgroundColor: colors.brandSoft, justifyContent: 'center' },
  tabOn: { backgroundColor: colors.brand },
  columns: { flexDirection: 'row', flexWrap: 'wrap', gap: space.s24, alignItems: 'flex-start' },
  panel: { backgroundColor: colors.surface, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, overflow: 'hidden' },
  review: { gap: space.s4, padding: space.s12, borderRadius: radius.row, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.paper },
  fresh: { borderColor: colors.urgent, borderWidth: 2 },
  reviewHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  reply: { gap: space.s4, marginTop: space.s4, padding: space.s12, borderRadius: radius.row, backgroundColor: colors.brandSoft },
});
