import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';

import { Surface, Tip } from '@/components/cards';
import { Icon, IconName } from '@/components/Icon';
import { DonnaLine } from '@/components/talk';
import { Thread } from '@/components/Thread';
import { Txt } from '@/components/Txt';
import { Group, Segmented, useLoad } from '@/components/ui';
import { api, DoneItem, Week, WeekDay } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { colors, radius, space } from '@/theme/tokens';

// 일정 탭. 사장님이 눈으로 확인하는 화면이다 (마이크가 필요 없다).
//
// 왜 보나: "이번 주에 내가 챙길 날이 언제지?"를 가게 벽의 종이 달력을 보듯 한눈에 확인하려고.
// 무엇을 느끼나: 행사, 경기, 비, 단체 예약, 도나가 올릴 답글이 내가 적지 않아도 달력에 이미 적혀 있다.
//
// 배우지 않아도 쓰게, 사장님이 이미 매일 쓰는 달력을 그대로 따른다 (갤럭시 기본 캘린더, One UI 4부터).
//   휴대폰·태블릿 세로 = 캘린더의 "목록 보기": 일이 있는 날은 날짜 칸이 옅게 차고, 날짜를 누르면 아래에 그날의 일정이
//                        "시각 | 할 일" 한 줄씩 나온다. 날짜 줄에는 날씨.
//   태블릿 가로       = 캘린더의 "월간 보기"(가게 벽의 종이 달력): 한 달이 왼쪽을 채우고, 날짜 칸 안에 일정의 짧은 이름이
//                        적힌다. 오른쪽에 고른 날의 목록. 한 달 안에 이번 주가 다 보이므로 이번 주/이번 달을 고르지 않는다.
// 새로 만든 그림, 붐빔 예상, 큰 한마디, 진행 띠는 없다. 도나가 더하는 것은 준비할 것 한 줄뿐이다.
type Mode = 'week' | 'month';
const WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일'];
const WEATHER_ICON: Record<string, IconName> = { 비: 'rain', 구름: 'cloud', 맑음: 'sun' };

/** 고른 날 목록의 한 줄. 왼쪽 시각, 오른쪽 할 일 (캘린더 목록 보기와 같다). */
type Line = { id: string; time: string | null; allDay?: string; title: string; sub?: string; donna?: boolean };

/** 그날 목록에 놓을 줄들. 시각 순으로, 하루 종일인 것이 맨 위. */
function linesOf(d: WeekDay): Line[] {
  const plans = d.plans.map((p) => ({
    id: p.id,
    time: p.time_label,
    allDay: p.starts_at ? undefined : '하루 종일',
    title: p.text,
    // 종류 이름(경기, 행사)을 아래에 작게. 내용에 이미 들어 있으면(하루 종일 비) 되풀이하지 않는다.
    sub: p.text.includes(p.label) ? undefined : p.label,
    at: p.starts_at ?? '',
  }));
  const replies = d.scheduled.map((r) => ({ id: r.id, time: r.time_label, title: r.text, sub: '도나가 올릴 답글', donna: true, at: r.post_at }));
  return [...plans, ...replies].sort((a, b) => a.at.localeCompare(b.at));
}

/** 오늘은 지난 일정이 빠지고 남은 것만 나온다 (캘린더의 "오늘" 위젯처럼). */
function todayLines(d: WeekDay): Line[] {
  const rest = d.remaining.map((r) => ({ id: r.id, time: r.time_label, allDay: r.time_label ? undefined : '오늘 중', title: r.text }));
  const replies = d.scheduled.map((r) => ({ id: r.id, time: r.time_label, title: r.text, sub: '도나가 올릴 답글', donna: true }));
  return [...rest, ...replies];
}

/** 한 일 한 줄. 누가 했는지는 아래 작은 글로 구분한다. */
function DoneRow({ item }: { item: DoneItem }) {
  const { scale } = useLayout();
  const who = item.actor === 'owner' ? (item.after_briefing ? '사장님이 브리핑을 듣고' : '사장님') : '도나';
  return (
    <View style={styles.doneRow}>
      <View style={{ paddingTop: space.s4 }}>
        <Icon name="check" size={Math.round(20 * scale)} color="brand" />
      </View>
      <View style={{ flex: 1 }}>
        <Txt variant="bodyStrong">{item.text}</Txt>
        <Txt variant="small" color="ink3">
          {who}
          {item.time_label ? ` ${item.time_label}` : ''}
        </Txt>
      </View>
    </View>
  );
}

/** 날짜 숫자. 오늘은 테두리, 고른 날은 갈색으로 찬 동그라미 (캘린더와 같다). */
function DayNumber({ d, on, size: base = 32 }: { d: WeekDay; on: boolean; size?: number }) {
  const { scale } = useLayout();
  const size = Math.round(base * scale);
  return (
    <View
      style={[
        styles.number,
        { width: size, height: size, borderRadius: size / 2 },
        d.is_today && { borderColor: colors.brand },
        on && { backgroundColor: colors.brand, borderColor: colors.brand },
      ]}
    >
      <Txt variant="label" color={on ? 'brandInk' : d.is_past || !d.in_month ? 'ink3' : 'ink'} style={on || d.is_today ? styles.bold : undefined}>
        {d.day}
      </Txt>
    </View>
  );
}

/** 휴대폰의 날짜 칸 (목록 보기). 일이 있는 날은 칸이 옅게 찬다. 글은 없다. */
function SmallCell({ d, on, weekday, onPick }: { d: WeekDay; on: boolean; weekday: boolean; onPick: (date: string) => void }) {
  const { scale } = useLayout();
  const has = d.marks.length > 0;
  return (
    <Pressable onPress={() => onPick(d.date)} accessibilityRole="button" accessibilityState={{ selected: on }} accessibilityLabel={`${d.date_label}, ${d.title}`} style={{ flex: 1 }}>
      <View style={[styles.smallCell, { minHeight: Math.round((weekday ? 72 : 48) * scale) }, has && { backgroundColor: colors.brandSoft }, !d.in_month && { opacity: 0.35 }]}>
        {weekday ? (
          <Txt variant="small" color="ink3">
            {d.weekday_label}
          </Txt>
        ) : null}
        <DayNumber d={d} on={on} />
      </View>
    </Pressable>
  );
}

/** 칸 안에 적는 일정 이름 하나. 가게의 일은 옅은 갈색 띠, 도나가 할 일은 띠 없이 말풍선 아이콘. */
function Label({ text, donna }: { text: string; donna?: boolean }) {
  return (
    <View style={[styles.label, !donna && { backgroundColor: colors.brandSoft }]}>
      {donna ? <Icon name="message" size={13} color="brand" /> : null}
      <Txt variant="small" color={donna ? 'brand' : 'ink'} style={styles.labelText} numberOfLines={1}>
        {text}
      </Txt>
    </View>
  );
}

/** 태블릿 가로의 날짜 칸 (종이 달력). 숫자 아래에 그날 일정의 짧은 이름이 들어가는 만큼 적히고, 나머지는 개수로. */
function WallCell({ d, on, height, onPick }: { d: WeekDay; on: boolean; height: number; onPick: (date: string) => void }) {
  const items = [
    ...d.plans.map((p) => ({ id: p.id, text: p.short, donna: false })),
    ...d.scheduled.map((r) => ({ id: r.id, text: '답글', donna: true })),
  ];
  const { scale } = useLayout();
  const number = Math.round(24 * scale);
  // 칸에 들어가는 이름 줄 수: 칸 높이에서 안쪽 여백(8)과 숫자를 빼고 한 줄(18 + 사이 2)로 나눈다.
  const fit = Math.max(1, Math.floor((height - space.s8 - number) / 20));
  const max = items.length > fit ? fit - 1 : fit;
  return (
    <Pressable onPress={() => onPick(d.date)} accessibilityRole="button" accessibilityState={{ selected: on }} accessibilityLabel={`${d.date_label}, ${d.title}`} style={{ flex: 1 }}>
      <View style={[styles.wallCell, { height }, on && { borderColor: colors.brand }, (d.is_past || !d.in_month) && { opacity: 0.45 }]}>
        <View style={{ alignItems: 'center' }}>
          <DayNumber d={d} on={on} size={24} />
        </View>
        {items.slice(0, max).map((it) => (
          <Label key={it.id} text={it.text} donna={it.donna} />
        ))}
        {items.length > max ? (
          <Txt variant="small" color="ink3" style={[styles.labelText, { textAlign: 'center' }]}>
            +{items.length - max}
          </Txt>
        ) : null}
      </View>
    </Pressable>
  );
}

function WeekdayRow() {
  return (
    <View style={styles.row7}>
      {WEEKDAYS.map((w) => (
        <View key={w} style={{ flex: 1, alignItems: 'center' }}>
          <Txt variant="small" color="ink3">
            {w}
          </Txt>
        </View>
      ))}
    </View>
  );
}

function monthWeeks(data: Week) {
  return Array.from({ length: 6 }, (_, w) => data.days.slice(w * 7, w * 7 + 7)).filter((w) => w.some((d) => d.in_month));
}

/** 휴대폰·태블릿 세로의 달력: 이번 주 7칸 또는 한 달. */
function SmallCalendar({ data, mode, picked, onPick }: { data: Week; mode: Mode; picked: string; onPick: (date: string) => void }) {
  if (mode === 'week') {
    return (
      <View style={styles.row7}>
        {data.days
          .filter((d) => data.week_dates.includes(d.date))
          .map((d) => (
            <SmallCell key={d.date} d={d} on={d.date === picked} weekday onPick={onPick} />
          ))}
      </View>
    );
  }
  return (
    <Surface pad={space.s12} gap={space.s4}>
      <WeekdayRow />
      {monthWeeks(data).map((week) => (
        <View key={week[0].date} style={styles.row7}>
          {week.map((d) => (
            <SmallCell key={d.date} d={d} on={d.date === picked} weekday={false} onPick={onPick} />
          ))}
        </View>
      ))}
    </Surface>
  );
}

/** 태블릿 가로의 달력 (종이 달력). 한 달이 왼쪽 칸의 높이를 채운다. */
function WallCalendar({ data, picked, onPick }: { data: Week; picked: string; onPick: (date: string) => void }) {
  const { height } = useWindowDimensions();
  const weeks = monthWeeks(data);
  // 머리(날짜, 매장 이름 102), 달 이름과 요일 줄(64), 아래 메뉴바(74), 아래 여백(16), 줄 사이를 뺀 높이를 줄 수로 나눈다.
  const room = Math.max(height - 272, 360);
  const rowHeight = Math.max(Math.floor((room - space.s4 * (weeks.length - 1)) / weeks.length), 72);
  return (
    <View style={{ gap: space.s4 }}>
      <View style={styles.monthHead}>
        <Txt variant="label" style={styles.bold}>
          {data.month_label}
        </Txt>
      </View>
      <WeekdayRow />
      {weeks.map((week) => (
        <View key={week[0].date} style={styles.row7}>
          {week.map((d) => (
            <WallCell key={d.date} d={d} on={d.date === picked} height={rowHeight} onPick={onPick} />
          ))}
        </View>
      ))}
    </View>
  );
}

/** 고른 날의 목록 한 줄: 왼쪽 시각(갈색), 오른쪽 할 일. 하루 종일인 것은 시각 대신 작은 꼬리표. */
function ListLine({ line, last }: { line: Line; last: boolean }) {
  const { scale } = useLayout();
  return (
    <View style={[styles.line, !last && styles.lineRule]}>
      <View style={{ width: Math.round(88 * scale) }}>
        {line.allDay ? (
          <View style={styles.allDay}>
            <Txt variant="small" color="brand">
              {line.allDay}
            </Txt>
          </View>
        ) : (
          <Txt variant="small" color="brand" style={[styles.bold, { paddingTop: 4 }]}>
            {line.time}
          </Txt>
        )}
      </View>
      <View style={{ flex: 1 }}>
        <Txt variant="bodyStrong">{line.title}</Txt>
        {line.sub ? (
          <View style={styles.sub}>
            {line.donna ? <Icon name="message" size={14} color="ink3" /> : null}
            <Txt variant="small" color="ink3">
              {line.sub}
            </Txt>
          </View>
        ) : null}
      </View>
    </View>
  );
}

/** 접어 두는 묶음. 눌러야 펼쳐진다. */
function Fold({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Surface>
      <Pressable onPress={() => setOpen(!open)} accessibilityRole="button" accessibilityState={{ expanded: open }} style={styles.foldHead}>
        <View style={{ flex: 1 }}>
          <Txt variant="bodyStrong">{title}</Txt>
          {open ? null : (
            <Txt variant="small" color="ink3" numberOfLines={1}>
              {hint}
            </Txt>
          )}
        </View>
        <View style={{ transform: [{ rotate: open ? '-90deg' : '90deg' }] }}>
          <Icon name="chevronRight" size={22} color="ink3" />
        </View>
      </Pressable>
      {open ? children : null}
    </Surface>
  );
}

/** 고른 날 (캘린더 목록 보기의 아래쪽). 날짜와 날씨 한 줄, 그날의 일정 목록, 준비할 것, 한 것. */
function DayPanel({ day }: { day: WeekDay }) {
  const lines = day.is_today ? todayLines(day) : linesOf(day);
  return (
    <>
      <View style={styles.dayHead}>
        <Txt variant="label" style={styles.bold}>
          {day.date_label}
          {day.is_today ? ', 오늘' : ''}
        </Txt>
        {day.weather ? (
          <View style={styles.sub}>
            <Icon name={WEATHER_ICON[day.weather.label] ?? 'cloud'} size={16} color="ink3" />
            <Txt variant="small" color="ink3">
              {day.weather.temp_min}° / {day.weather.temp_max}°
            </Txt>
          </View>
        ) : null}
      </View>

      {lines.length || !day.is_past ? (
        <Surface pad={space.s4} gap={0}>
          {lines.length ? (
            lines.map((l, i) => <ListLine key={l.id} line={l} last={i === lines.length - 1} />)
          ) : (
            <View style={styles.line}>
              <Txt variant="bodyStrong" color="ink3">
                {day.is_today ? '남은 일이 없어요' : '잡힌 일이 없어요'}
              </Txt>
            </View>
          )}
        </Surface>
      ) : null}

      {day.tip ? <Tip card={{ kind: 'prepare', text: day.tip }} /> : null}

      {day.is_today && day.done.length ? (
        <Fold title="오늘 한 것" hint={day.done[day.done.length - 1].text}>
          {day.done.map((d) => (
            <DoneRow key={d.id} item={d} />
          ))}
        </Fold>
      ) : null}

      {day.is_past ? (
        <Group label="이날 한 것">
          <Surface>{day.done.length ? day.done.map((d) => <DoneRow key={d.id} item={d} />) : <Txt variant="bodyStrong">적힌 것이 없어요</Txt>}</Surface>
        </Group>
      ) : null}
    </>
  );
}

export default function CalendarScreen() {
  const { data, failed, reload } = useLoad(api.week);
  const { wide } = useLayout();
  const [mode, setMode] = useState<Mode>('week');
  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => {
    if (data && !picked) setPicked(data.today);
  }, [data, picked]);

  if (!data) {
    return (
      <Thread>
        {failed ? (
          <Pressable onPress={reload} accessibilityRole="button">
            <DonnaLine headline="일정을 못 불러왔어요" caption="여기를 누르면 다시 불러와요." />
          </Pressable>
        ) : null}
      </Thread>
    );
  }
  const day = data.days.find((d) => d.date === picked) ?? data.days.find((d) => d.is_today) ?? data.days[0];
  // 이번 주만 보는 중에 다른 주의 날짜가 골라져 있으면 오늘로 돌린다.
  const switchMode = (next: Mode) => {
    setMode(next);
    if (next === 'week' && !data.week_dates.includes(day.date)) setPicked(data.today);
  };
  const toggle = (
    <Segmented
      options={[
        { key: 'week', label: '이번 주' },
        { key: 'month', label: '이번 달' },
      ]}
      value={mode}
      onChange={switchMode}
    />
  );

  // 태블릿 가로: 왼쪽에 한 달 종이 달력, 오른쪽에 고른 날의 목록(폭 360: 시각과 할 일이 대개 한 줄에 들어간다).
  if (wide) {
    return (
      <Thread>
        <View style={styles.wide}>
          <View style={{ flex: 1 }}>
            <WallCalendar data={data} picked={day.date} onPick={setPicked} />
          </View>
          <View style={{ width: 360, gap: space.s16 }}>
            <DayPanel day={day} />
          </View>
        </View>
      </Thread>
    );
  }
  return (
    <Thread>
      <View style={{ gap: space.s8 }}>
        {toggle}
        <SmallCalendar data={data} mode={mode} picked={day.date} onPick={setPicked} />
      </View>
      <DayPanel day={day} />
    </Thread>
  );
}

const styles = StyleSheet.create({
  bold: { fontFamily: 'NotoSansKR_700Bold' },
  doneRow: { flexDirection: 'row', gap: space.s8 },
  row7: { flexDirection: 'row', gap: space.s4 },
  number: { alignItems: 'center', justifyContent: 'center', borderWidth: 1.5, borderColor: 'transparent' },
  smallCell: { alignItems: 'center', justifyContent: 'center', gap: space.s4, paddingVertical: space.s4, borderRadius: radius.tile },
  monthHead: { minHeight: 32, justifyContent: 'center' },
  wallCell: { alignItems: 'stretch', gap: 2, padding: space.s4, borderRadius: radius.tile, borderWidth: 1.5, borderColor: colors.line, backgroundColor: colors.surface, overflow: 'hidden' },
  label: { flexDirection: 'row', alignItems: 'center', gap: 2, paddingHorizontal: space.s4, borderRadius: 4 },
  labelText: { fontSize: 13, lineHeight: 18 },
  wide: { flexDirection: 'row', gap: space.s24, alignItems: 'flex-start' },
  dayHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.s8, minHeight: 32 },
  sub: { flexDirection: 'row', alignItems: 'center', gap: space.s4 },
  line: { flexDirection: 'row', alignItems: 'flex-start', gap: space.s8, paddingVertical: space.s12, paddingHorizontal: space.s12 },
  lineRule: { borderBottomWidth: 1, borderBottomColor: colors.line },
  allDay: { alignSelf: 'flex-start', paddingHorizontal: space.s8, borderRadius: radius.pill, backgroundColor: colors.brandSoft },
  foldHead: { flexDirection: 'row', alignItems: 'center', gap: space.s8, minHeight: 44 },
});
