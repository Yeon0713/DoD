import { useCallback, useEffect, useState } from 'react';
import { Platform as RNPlatform, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';

import { Txt } from '@/components/Txt';
import { api } from '@/lib/api';
import { DEMO_VIEWS, DevMessage, onDev, sendDev } from '@/lib/devChannel';
import { useSession } from '@/lib/session';
import { colors, fonts, radius, space } from '@/theme/tokens';

// 개발자 모드 (웹, 개발 모드에서만). 시연 화면(/demo)을 다른 탭에 띄워 두고 여기서 보낸다.
//   처음부터, 시각, 손님 리뷰  → 음성 백엔드(8100) 개발용 API 를 바로 부른다
//   사장님 말, 보는 화면       → 같은 주소의 다른 탭으로 보낸다 (lib/devChannel.ts). 사장님 앱이 열려 있어야 듣는다
//   기록                     → 사장님 앱이 들은 말을 어떻게 했는지, 도나가 무엇이라 답했는지
// 시험 순서: donna-voice/docs/test-scenarios-closed-loop.md W
const DAY = '2026-11-17';
const OWNER_LINES = [
  '도나야, 오늘 일정 브리핑해 줘',
  '응, 그렇게 해',
  '다음',
  '도나야, 진행해',
  '응, 진행해',
  '도나야, 쿠폰 빼고 사과만 올려',
  '도나야, 카드는 넣지 마',
  '도나야, 응, 올려',
  '도나야, 안 해',
];
// 알바생 일 (server/voice/staff_orders.py). 순서대로 누르면 초대 → 가입 → 시키기 → 확인 → 취소를 시연할 수 있다
const STAFF_LINES = [
  '도나야, 하린이 초대해 줘',
  '카카오톡으로 보내 줘',
  '도나야, 하린이한테 오늘 들어온 감자가 물이 많으니까 감자전 반죽에 전분 한 숟갈 더 넣으라고 해',
  '도나야, 새뱅이 다 떨어졌으니까 오늘은 장칼국수 주문 받지 말라고 해',
  '오늘만',
  '매일',
  '응, 보내 줘',
  '도나야, 시킨 거 다 했대?',
  '도나야, 그거 취소해',
  '도나야, 알바생 누구 있어?',
  '도나야, 알바생 매뉴얼 보여 줘',
];
const REVIEWS = [
  ['leak', '국물 샘'],
  ['missing', '누락'],
  ['cold', '식음'],
  ['hall', '홀 응대'],
] as const;
const HEARD_LABEL = { sent: '보냄', uncalled: '부르지 않은 말이라 흘려들음 ("도나야"를 붙이거나 도나가 말한 뒤 8초 안에)', too_short: '너무 짧아 흘려들음' };

type Line = { id: number; at: string; text: string; tone: 'me' | 'app' | 'donna' | 'error' };
let lineId = 0;

export default function DevScreen() {
  const session = useSession();
  const [now, setNow] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [said, setSaid] = useState('도나야, ');
  const [clockText, setClockText] = useState('15:35');
  const [log, setLog] = useState<Line[]>([]);

  const add = useCallback((text: string, tone: Line['tone']) => {
    const at = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setLog((old) => [{ id: lineId++, at, text, tone }, ...old].slice(0, 30));
  }, []);

  useEffect(() => {
    session.enter('s005', '초옹장'); // 개발용 API 가 초옹장(s005)을 부르게
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadNow = useCallback(() => api.dev.platform().then((p) => setNow(p.now_label)).catch(() => setNow(null)), []);
  useEffect(() => {
    void loadNow();
    const id = setInterval(loadNow, 3000);
    return () => clearInterval(id);
  }, [loadNow]);

  // 사장님 앱이 알려 주는 것
  useEffect(
    () =>
      onDev((m: DevMessage) => {
        if (m.type === 'heard') add(`사장님 앱: “${m.text}” → ${HEARD_LABEL[m.result]}`, 'app');
        if (m.type === 'turn' && m.kind !== 'ignore') add(`도나 (${m.kind}, ${m.intent}): ${m.headline ?? ''}${m.say.length ? ` — ${m.say.join(' ')}` : ''}`, 'donna');
        if (m.type === 'turn' && m.kind === 'ignore') add(`도나: 도나에게 한 말이 아니라 가만히 있음 (${m.said ?? ''})`, 'donna');
      }),
    [add],
  );

  const run = async (label: string, job: () => Promise<unknown>) => {
    setBusy(label);
    add(label, 'me');
    try {
      await job();
    } catch (e) {
      add(`실패: ${(e as Error).message}`, 'error');
    } finally {
      setBusy(null);
      void loadNow();
    }
  };
  const restart = () =>
    run('처음부터 (초옹장 데이터 다시 넣기, 1 ~ 2분)', async () => {
      await api.dev.fixtures();
      sendDev({ type: 'reload' });
      add('다시 넣었어요. 시연 화면의 휴대폰을 다시 열었어요', 'me');
    });
  const at = (hhmm: string) => {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(hhmm)) {
      add(`시각은 15:35 처럼 적어 주세요 (${hhmm})`, 'error');
      return;
    }
    void run(`시각 ${DAY} ${hhmm}`, () => api.dev.clock(`${DAY}T${hhmm}:00+09:00`));
  };
  const plus = (minutes: number) =>
    run(`시각 +${minutes}분`, async () => {
      const current = new Date((await api.dev.platform()).now);
      await api.dev.clock(new Date(current.getTime() + minutes * 60000).toISOString());
    });
  const joinHarin = () =>
    run('하린 바로 가입 (연습용)', async () => {
      const r = await api.dev.staffJoin('하린');
      sendDev({ type: 'staff_session', token: r.token, staffId: r.staff_id, name: r.name });
      add('하린이 가입한 상태로 시연 화면의 알바생 휴대폰을 열었어요', 'me');
    });
  const say = (text: string) => {
    const clean = text.trim();
    if (!clean) return;
    sendDev({ type: 'say', text: clean });
    add(`사장님 말 보냄: “${clean}”`, 'me');
  };

  if (RNPlatform.OS !== 'web' || !__DEV__) {
    return (
      <View style={styles.page}>
        <Txt variant="body">개발자 모드는 웹 개발 모드에서만 열려요.</Txt>
      </View>
    );
  }

  return (
    <ScrollView style={styles.page} contentContainerStyle={styles.body}>
      <View style={{ gap: space.s4 }}>
        <Txt variant="title">개발자 모드</Txt>
        <Txt variant="small" color="ink2">
          시연 화면은 다른 탭에서 /demo 로 열어 두세요. 사장님 앱(/)은 한 곳에만 열어 두세요 (알림은 먼저 읽은 쪽이 가져갑니다).
        </Txt>
      </View>

      <Group label="시연">
        <Btn label="처음부터" onPress={restart} busy={busy} />
      </Group>

      <Group label="보는 화면 (시연 화면에 보냄)">
        {DEMO_VIEWS.map((d) => (
          <Btn key={d.key} label={d.label} onPress={() => sendDev({ type: 'view', view: d.key })} busy={null} quiet />
        ))}
      </Group>

      <Group label={`시각 (백엔드 지금: ${now ?? '모름'})`}>
        <Btn label="15:35" onPress={() => at('15:35')} busy={busy} />
        <Btn label="+5분" onPress={() => plus(5)} busy={busy} />
        <Btn label="+10분" onPress={() => plus(10)} busy={busy} />
        <Btn label="+15분" onPress={() => plus(15)} busy={busy} />
        <View style={styles.inputRow}>
          <TextInput value={clockText} onChangeText={setClockText} onSubmitEditing={() => at(clockText)} style={[styles.input, { width: 80 }]} accessibilityLabel="옮길 시각" />
          <Btn label="옮기기" onPress={() => at(clockText)} busy={busy} />
        </View>
      </Group>

      <Group label="손님 리뷰 넣기 (지금 시각에)">
        {REVIEWS.map(([name, label]) => (
          <Btn key={name} label={label} onPress={() => run(`리뷰 넣기: ${label}`, () => api.dev.demoReview(name))} busy={busy} />
        ))}
      </Group>

      <Group label="사장님 말 (마이크 대신)">
        {OWNER_LINES.map((line) => (
          <Btn key={line} label={line} onPress={() => say(line)} busy={null} quiet />
        ))}
        <View style={[styles.inputRow, { width: '100%' }]}>
          <TextInput
            value={said}
            onChangeText={setSaid}
            onSubmitEditing={() => say(said)}
            placeholder="도나야, 오늘 남은 일 뭐야?"
            style={[styles.input, { flex: 1 }]}
            accessibilityLabel="사장님이 할 말"
          />
          <Btn label="말하기" onPress={() => say(said)} busy={null} />
        </View>
      </Group>

      <Group label="알바생 (사장님 말, 2026-11-18)">
        {STAFF_LINES.map((line) => (
          <Btn key={line} label={line} onPress={() => say(line)} busy={null} quiet />
        ))}
        <Btn label="연습용: 하린 바로 가입 (초대 건너뛰기)" onPress={joinHarin} busy={busy} />
      </Group>

      <View style={styles.log}>
        <Txt variant="small" color="ink2">
          기록 (최근 것 위)
        </Txt>
        {log.length ? (
          log.map((l) => (
            <Txt key={l.id} variant="small" color={l.tone === 'error' ? 'urgent' : l.tone === 'donna' ? 'brand' : l.tone === 'app' ? 'ink2' : 'ink'}>
              {l.at}  {l.text}
            </Txt>
          ))
        ) : (
          <Txt variant="small" color="ink3">
            아직 없어요
          </Txt>
        )}
      </View>
    </ScrollView>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: space.s8 }}>
      <Txt variant="label" color="ink2" style={{ fontFamily: fonts.bold }}>
        {label}
      </Txt>
      <View style={styles.row}>{children}</View>
    </View>
  );
}

function Btn({ label, onPress, busy, quiet }: { label: string; onPress: () => void; busy: string | null; quiet?: boolean }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!!busy}
      accessibilityRole="button"
      style={({ pressed }) => [styles.btn, quiet && styles.btnQuiet, { opacity: busy ? 0.5 : pressed ? 0.8 : 1 }]}
    >
      <Txt variant="label" color={quiet ? 'brand' : 'brandInk'}>
        {label}
      </Txt>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.paper },
  body: { padding: space.s24, gap: space.s24, maxWidth: 720, width: '100%', alignSelf: 'center' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.s8, alignItems: 'center' },
  btn: { paddingHorizontal: space.s12, height: 36, borderRadius: radius.pill, backgroundColor: colors.brand, justifyContent: 'center' },
  btnQuiet: { backgroundColor: colors.brandSoft },
  inputRow: { flexDirection: 'row', gap: space.s8, alignItems: 'center' },
  input: { height: 36, paddingHorizontal: space.s12, borderRadius: radius.row, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface, fontFamily: fonts.regular, fontSize: 15, color: colors.ink },
  log: { gap: space.s4, padding: space.s16, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface },
});
