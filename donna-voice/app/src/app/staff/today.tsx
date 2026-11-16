import { useFocusEffect, useRouter } from 'expo-router';
import { Fragment, useCallback, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { AttendanceStrip, BigButton, StaffFrame, StaffHeader } from '@/components/staff';
import { Txt } from '@/components/Txt';
import { api, StaffTask, StaffToday } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { staffSession } from '@/lib/staffSession';
import { colors, radius, space } from '@/theme/tokens';

// F-06, F-09 할 일 (확정 포맷: 하루 순서형).
//   머리: 가게 로고, 이름, 날짜, 내 이름 꼬리표 / 출퇴근 줄
//   몸통: 오픈 전, 영업 중, 마감 순서. 왼쪽은 때, 오른쪽은 일 (삼성 캘린더 목록 보기). "지금" 선 위는 지난 때.
//   "확인 필요"는 그 때 묶음 맨 위에 따로 있고 저마다 눌러야 사라진다.
export default function StaffTodayScreen() {
  const router = useRouter();
  const [data, setData] = useState<StaffToday | null>(null);
  const [staffId, setStaffId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const s = await staffSession.load();
    if (!s.staffId) {
      router.replace('/staff');
      return;
    }
    setStaffId(s.staffId);
    api.staff.today(s.staffId).then(setData).catch(() => {});
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
  const toggle = (t: StaffTask) => api.staff.done(t.id, staffId, t.done).then(load);
  const confirm = (t: StaffTask) => api.staff.confirm(t.id, staffId).then(load);
  const checkout = () => api.staff.checkout(staffId).then(load);
  const nowLine = <NowLine key="now" />;

  return (
    <StaffFrame>
      <StaffHeader store={store} me={data.staff.call} />
      <AttendanceStrip state={data.attendance.state} label={data.attendance.label} detail={data.attendance.detail} onCheckout={checkout} />
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
                    <Txt variant="bodyStrong">{t.title}</Txt>
                    <Txt variant="label" color="ink2">
                      {t.sub}
                    </Txt>
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
  list: { paddingVertical: space.s4, paddingHorizontal: space.s16, borderRadius: radius.card, backgroundColor: colors.surface },
  line: { height: 1, backgroundColor: colors.line },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: space.s12, paddingVertical: space.s12 },
  box: { marginTop: 2, borderRadius: 8, borderWidth: 2, borderColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  now: { flexDirection: 'row', alignItems: 'center', gap: space.s8 },
  nowWhen: { width: 56 },
  nowDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brand },
  nowBar: { flex: 1, height: 2, backgroundColor: colors.brand },
});
