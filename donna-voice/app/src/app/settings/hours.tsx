import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Modal, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon } from '@/components/Icon';
import { SubPage } from '@/components/settings';
import { Txt } from '@/components/Txt';
import { Button, Switch, useLoad } from '@/components/ui';
import { api, DayHours } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { colors, radius, space } from '@/theme/tokens';

// 설정 > 장사 시간 (Figma v0.2.1 G-06, 이전 앱 06-19h). 요일마다 시간과 문 여는 날을 고친다.
// 저장하면 가게 상태 줄과 브리핑 알림(기본 문 열기 1시간 전)이 바뀐 시간을 따른다.
// '네이버에서 다시 불러오기'는 고치기 전 네이버 시간을 칸에 채우기만 하고, 저장하기를 눌러야 바뀐다 (이전 앱과 같다).
const STEP = 30; // 분

const toMin = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
const toText = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;

/** 시각 하나를 30분씩 앞뒤로. 누르는 곳은 56. */
function Stepper({ label, value, onChange, min, max }: { label: string; value: string; onChange: (v: string) => void; min: number; max: number }) {
  const { scale } = useLayout();
  const m = toMin(value);
  const btn = (dir: -1 | 1) => {
    const next = m + dir * STEP;
    const off = next < min || next > max;
    return (
      <Pressable
        onPress={() => onChange(toText(next))}
        disabled={off}
        accessibilityRole="button"
        accessibilityLabel={`${label} ${dir < 0 ? '30분 앞으로' : '30분 뒤로'}`}
        style={[styles.step, off && { opacity: 0.35 }]}
      >
        <Icon name={dir < 0 ? 'chevronLeft' : 'chevronRight'} size={Math.round(24 * scale)} color="brand" />
      </Pressable>
    );
  };
  return (
    <View style={{ gap: space.s8 }}>
      <Txt variant="label" color="ink2">
        {label}
      </Txt>
      <View style={styles.stepper}>
        {btn(-1)}
        <Txt variant="title" style={{ flex: 1, textAlign: 'center' }}>
          {value}
        </Txt>
        {btn(1)}
      </View>
    </View>
  );
}

/** 한 요일의 시간을 고치는 아래 창. 이 요일만, 또는 문 여는 모든 요일에 똑같이. */
function DaySheet({ day, onClose, onApply }: { day: DayHours | null; onClose: () => void; onApply: (open: string, close: string, all: boolean) => void }) {
  const insets = useSafeAreaInsets();
  const { margin, contentMax } = useLayout();
  const [open, setOpen] = useState('10:30');
  const [close, setClose] = useState('20:30');
  useEffect(() => {
    if (day) {
      setOpen(day.open);
      setClose(day.close);
    }
  }, [day]);
  return (
    <Modal visible={!!day} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel="닫기" />
      <View style={[styles.sheet, { paddingHorizontal: margin, paddingBottom: Math.max(insets.bottom, space.s24) }]}>
        <View style={{ width: '100%', maxWidth: contentMax, alignSelf: 'center', gap: space.s16 }}>
          <Txt variant="title">{day ? `${day.label}요일 장사 시간` : ''}</Txt>
          <Stepper label="여는 시간" value={open} onChange={setOpen} min={5 * 60} max={toMin(close) - STEP} />
          <Stepper label="닫는 시간" value={close} onChange={setClose} min={toMin(open) + STEP} max={23 * 60 + 30} />
          <View style={{ gap: space.s8, marginTop: space.s8 }}>
            <Button label={day ? `${day.label}요일만 바꾸기` : '바꾸기'} onPress={() => onApply(open, close, false)} />
            <Button kind="outline" label="문 여는 모든 요일에 똑같이" onPress={() => onApply(open, close, true)} />
          </View>
        </View>
      </View>
    </Modal>
  );
}

export default function HoursScreen() {
  const router = useRouter();
  const { data, failed, reload } = useLoad(api.settings);
  const [days, setDays] = useState<DayHours[] | null>(null);
  const [editing, setEditing] = useState<DayHours | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (data && !days) setDays(data.hours.days);
  }, [data, days]);

  if (!data || !days) {
    return (
      <SubPage title="장사 시간">
        {failed ? (
          <Pressable onPress={reload} accessibilityRole="button">
            <Txt variant="bodyStrong">못 불러왔어요. 여기를 누르면 다시 불러와요.</Txt>
          </Pressable>
        ) : null}
      </SubPage>
    );
  }

  const change = (next: DayHours[]) => {
    setDays(next);
    setNote(null);
  };
  const save = async () => {
    setSaving(true);
    setNote(null);
    try {
      await api.patchSettings({ hours: { days: days.map((d) => ({ closed: d.closed, open: d.open, close: d.close })) } });
      router.back();
    } catch {
      setNote('저장하지 못했어요. 다시 눌러 주세요.');
      setSaving(false);
    }
  };

  return (
    <SubPage
      title="장사 시간"
      footer={
        <>
          <Button label={saving ? '저장하는 중' : '저장하기'} onPress={save} />
          <Button
            kind="outline"
            label="네이버에서 다시 불러오기"
            onPress={() => {
              change(data.hours.naver_days);
              setNote('네이버에서 불러왔어요. 저장하기를 누르면 바뀌어요.');
            }}
          />
        </>
      }
    >
      {note || data.briefing_notify.is_default ? (
        <Txt variant="label" color="ink2">
          {note ?? '고치면 브리핑 알림 시간도 같이 맞춰요'}
        </Txt>
      ) : null}
      <View style={styles.card}>
        {days.map((d, i) => (
          <View key={d.weekday}>
            {i > 0 ? <View style={styles.rule} /> : null}
            <View style={styles.dayRow}>
              <Txt variant="bodyStrong" style={styles.dayLabel}>
                {d.label}
              </Txt>
              <Pressable
                onPress={() => setEditing(d)}
                disabled={d.closed}
                accessibilityRole="button"
                accessibilityLabel={d.closed ? `${d.label}요일 쉬어요` : `${d.label}요일 ${d.open}부터 ${d.close}까지, 눌러서 바꾸기`}
                style={[styles.timeBox, d.closed && { backgroundColor: 'transparent' }]}
              >
                <Txt variant="bodyStrong" color={d.closed ? 'ink2' : 'ink'}>
                  {d.closed ? '쉬어요' : `${d.open} ~ ${d.close}`}
                </Txt>
              </Pressable>
              <Switch on={!d.closed} onChange={(on) => change(days.map((x) => (x.weekday === d.weekday ? { ...x, closed: !on } : x)))} label={`${d.label}요일 문 열기`} />
            </View>
          </View>
        ))}
      </View>
      <DaySheet
        day={editing}
        onClose={() => setEditing(null)}
        onApply={(open, close, all) => {
          change(days.map((x) => (all ? (x.closed ? x : { ...x, open, close }) : x.weekday === editing?.weekday ? { ...x, open, close } : x)));
          setEditing(null);
        }}
      />
    </SubPage>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, padding: space.s4 },
  rule: { height: 1, backgroundColor: colors.line, marginHorizontal: space.s12 },
  dayRow: { flexDirection: 'row', alignItems: 'center', gap: space.s12, paddingVertical: space.s8, paddingHorizontal: space.s12 },
  dayLabel: { width: 24, textAlign: 'center' },
  timeBox: { flex: 1, minHeight: 44, justifyContent: 'center', paddingHorizontal: space.s12, borderRadius: radius.tile, backgroundColor: colors.brandSoft },
  backdrop: { flex: 1, backgroundColor: 'rgba(43, 26, 15, 0.4)' },
  sheet: { backgroundColor: colors.paper, borderTopLeftRadius: radius.card, borderTopRightRadius: radius.card, paddingTop: space.s24 },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: space.s8, backgroundColor: colors.surface, borderRadius: radius.tile, borderWidth: 1, borderColor: colors.line, padding: space.s4 },
  step: { width: 56, height: 56, alignItems: 'center', justifyContent: 'center', borderRadius: radius.tile, backgroundColor: colors.brandSoft },
});
