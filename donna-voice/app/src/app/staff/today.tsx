import { useFocusEffect, useRouter } from 'expo-router';
import { Fragment, useCallback, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { AttendanceStrip, BigButton, StaffFrame, StaffHeader } from '@/components/staff';
import { Txt } from '@/components/Txt';
import { api, ApiFailure, StaffTask, StaffToday } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { staffSession } from '@/lib/staffSession';
import { colors, radius, space } from '@/theme/tokens';

// F-06, F-09 할 일 (확정 포맷: 하루 순서형).
//   머리: 가게 로고, 이름, 날짜, 내 이름 꼬리표 / 출퇴근 줄
//   몸통: 오픈 전, 영업 중, 마감 순서. 왼쪽은 때, 오른쪽은 일 (삼성 캘린더 목록 보기). "지금" 선 위는 지난 때.
//   "확인 필요"는 그 때 묶음 맨 위에 따로 있고 저마다 눌러야 사라진다. 아쉬운 리뷰에서 나온 교정 카드도 여기에 뜬다
//   (2026-11-20 긴급에서 내림). 무엇을 할지(detail)를 보여 주고, 누르면 자세히로 간다.
//   긴급(비 오는 날 이벤트 등, 오늘 안 하면 손님이 바로 겪는 일)은 화면 맨 위에 붉게 뜨고, 확인해야 퇴근할 수 있다.
export default function StaffTodayScreen() {
  const router = useRouter();
  const [data, setData] = useState<StaffToday | null>(null);
  const [staffId, setStaffId] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);

  const load = useCallback(async () => {
    const s = await staffSession.load();
    if (!s.token || !s.staffId) {
      router.replace('/staff');
      return;
    }
    setStaffId(s.staffId);
    api.staff
      .today()
      .then(setData)
      .catch(async (e) => {
        // 로그인 표시가 끊김 (처음부터 다시, 사장님이 내보냄): 이 기기 기록을 지우고 입장 화면으로
        if (e instanceof ApiFailure && e.code === 'not_signed_in') {
          await staffSession.clear();
          router.replace('/staff');
        }
      });
  }, [router]);

  useFocusEffect(
    useCallback(() => {
      void load();
      const id = setInterval(load, 5000); // 사장님이 말로 보낸 새 할 일이 바로 보이게
      return () => clearInterval(id);
    }, [load]),
  );

  if (!data || !staffId) return <StaffFrame>{null}</StaffFrame>;
  const store = { name: data.store.name, logo_url: data.store.logo_url, date_label: data.date_label };
  const toggle = (t: StaffTask) => api.staff.done(t.id, t.done).then(load);
  const confirm = (t: StaffTask) => api.staff.confirm(t.id).then(() => setBlocked(null)).then(load);
  const checkout = () =>
    api.staff
      .checkout()
      .then(() => setBlocked(null))
      .then(load)
      .catch((e) => setBlocked(e instanceof ApiFailure ? e.message : '지금은 퇴근을 적지 못했어요.'));
  const nowLine = <NowLine key="now" />;

  return (
    <StaffFrame>
      <StaffHeader store={store} me={data.staff.call} />
      <AttendanceStrip state={data.attendance.state} label={data.attendance.label} detail={data.attendance.detail} onCheckout={checkout} />
      {blocked ? (
        <Txt variant="label" color="urgent" accessibilityRole="alert">
          {blocked}
        </Txt>
      ) : null}
      {(data.urgent ?? []).map((t) => (
        <UrgentCard key={t.id} task={t} onConfirm={() => confirm(t)} onOpen={() => router.push(`/staff/task/${t.id}`)} />
      ))}
      <View style={{ gap: space.s16 }}>
        {data.now_after === null ? nowLine : null}
        {data.groups.map((g) => (
          <Fragment key={g.phase}>
            <View style={styles.group}>
              <View style={styles.when}>
                <Txt variant="label" color={g.now ? 'brand' : 'ink2'} style={g.now ? { fontFamily: 'NotoSansKR_700Bold' } : undefined}>
                  {g.label}
                </Txt>
              </View>
              <View style={{ flex: 1, gap: space.s8 }}>
                {g.must.map((t) => (
                  <View key={t.id} style={styles.must}>
                    <Pressable
                      onPress={() => router.push(`/staff/task/${t.id}`)}
                      accessibilityRole="button"
                      accessibilityLabel={`${t.title} 자세히`}
                      style={{ gap: space.s4 }}
                    >
                      <Txt variant="bodyStrong">{t.title}</Txt>
                      {t.detail ? (
                        <Txt variant="body" color="ink2">
                          {t.detail}
                        </Txt>
                      ) : null}
                      <Txt variant="label" color="ink2">
                        {t.sub}
                      </Txt>
                    </Pressable>
                    <BigButton label="확인" onPress={() => confirm(t)} />
                  </View>
                ))}
                {g.tasks.length ? (
                  <View style={styles.list}>
                    {g.tasks.map((t, i) => (
                      <Fragment key={t.id}>
                        {i > 0 ? <View style={styles.line} /> : null}
                        <TaskRow task={t} onToggle={() => toggle(t)} onOpen={() => router.push(`/staff/task/${t.id}`)} />
                      </Fragment>
                    ))}
                  </View>
                ) : null}
              </View>
            </View>
            {data.now_after === g.phase ? nowLine : null}
          </Fragment>
        ))}
      </View>
    </StaffFrame>
  );
}

function TaskRow({ task, onToggle, onOpen }: { task: StaffTask; onToggle: () => void; onOpen: () => void }) {
  const { scale } = useLayout();
  const box = Math.round(26 * scale);
  // 새로 온 줄은 "방금"이 진하게 보인다 (F-09). 끝낸 줄에는 붙이지 않는다.
  const fresh = task.fresh && !task.done;
  return (
    <View style={styles.row}>
      <Pressable
        onPress={onToggle}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: task.done }}
        accessibilityLabel={task.title}
        hitSlop={10}
        style={[styles.box, { width: box, height: box }, task.done && { backgroundColor: colors.brand, borderColor: colors.brand }]}
      >
        {task.done ? <Icon name="check" size={Math.round(18 * scale)} color="brandInk" /> : null}
      </Pressable>
      <Pressable onPress={onOpen} style={{ flex: 1 }} accessibilityRole="button" accessibilityLabel={`${task.title} 자세히`}>
        <Txt variant="bodyStrong" color={task.done ? 'ink2' : 'ink'}>
          {task.title}
        </Txt>
        <Txt variant="label" color={fresh ? 'brand' : 'ink2'} style={fresh ? { fontFamily: 'NotoSansKR_700Bold' } : undefined}>
          {fresh ? `방금, ${task.sub}` : task.sub}
        </Txt>
      </Pressable>
    </View>
  );
}

/** 긴급 카드: 오늘 안 하면 손님이 바로 겪는 일 (비 오는 날 이벤트 등). 붉은 표시, 무엇을 어떻게, 확인. */
function UrgentCard({ task, onConfirm, onOpen }: { task: StaffTask; onConfirm: () => void; onOpen: () => void }) {
  const { scale } = useLayout();
  return (
    <View style={styles.urgent} accessibilityRole="alert">
      <Pressable onPress={onOpen} accessibilityRole="button" accessibilityLabel={`${task.title} 자세히`} style={{ gap: space.s8 }}>
        <View style={styles.badge}>
          <Icon name="alert" size={Math.round(16 * scale)} color="urgent" />
          <Txt variant="label" color="urgent" style={{ fontFamily: 'NotoSansKR_700Bold' }}>
            긴급
          </Txt>
          <Txt variant="label" color="ink2">
            {task.fresh ? `방금, ${task.sub}` : task.sub}
          </Txt>
        </View>
        <Txt variant="title">{task.title}</Txt>
        {task.detail ? (
          <Txt variant="body" color="ink2">
            {task.detail}
          </Txt>
        ) : null}
      </Pressable>
      <BigButton label="확인" onPress={onConfirm} />
    </View>
  );
}

/** 지금 시각 선 (삼성 캘린더). 선 위는 지난 때, 아래는 앞으로 할 때. */
function NowLine() {
  return (
    <View style={styles.now} accessibilityLabel="지금">
      <View style={styles.nowWhen}>
        <Txt variant="label" color="brand" style={{ fontFamily: 'NotoSansKR_700Bold' }}>
          지금
        </Txt>
      </View>
      <View style={styles.nowDot} />
      <View style={styles.nowBar} />
    </View>
  );
}

const styles = StyleSheet.create({
  group: { flexDirection: 'row', gap: space.s8 },
  when: { width: 56, paddingTop: space.s16 },
  must: { gap: space.s12, padding: space.s16, borderRadius: radius.card, backgroundColor: colors.brandSoft },
  urgent: { gap: space.s12, padding: space.s16, borderRadius: radius.card, backgroundColor: colors.urgentSoft, borderWidth: 2, borderColor: colors.urgent },
  badge: { flexDirection: 'row', alignItems: 'center', gap: space.s4 },
  list: { paddingVertical: space.s4, paddingHorizontal: space.s16, borderRadius: radius.card, backgroundColor: colors.surface },
  line: { height: 1, backgroundColor: colors.line },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: space.s12, paddingVertical: space.s12 },
  box: { marginTop: 2, borderRadius: 8, borderWidth: 2, borderColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  now: { flexDirection: 'row', alignItems: 'center', gap: space.s8 },
  nowWhen: { width: 56 },
  nowDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brand },
  nowBar: { flex: 1, height: 2, backgroundColor: colors.brand },
});
