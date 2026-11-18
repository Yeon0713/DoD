import { Pressable, StyleSheet, View } from 'react-native';

import { NumText, Stars, Surface } from '@/components/cards';
import { Icon } from '@/components/Icon';
import { DonnaLine } from '@/components/talk';
import { Thread } from '@/components/Thread';
import { Txt } from '@/components/Txt';
import { Columns, useLoad } from '@/components/ui';
import { api, Sales } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { colors, radius, space } from '@/theme/tokens';

// 매출 (Figma v0.2.1 G-04). 사장님이 매일 쓰는 앱(캐시노트, 배민 사장님, 토스 포스)의 첫 화면에서 거꾸로 읽은 순서:
//   ① 오늘 지금까지 (문 열기 전에는 어제) ↔ 지난주 같은 요일 이맘때. 가장 크게(36), 막대 두 개.
//   ② 이번 주 · 이번 달 지금까지 ↔ 지난주 · 지난달 이맘때. 나란히(22).
//   ③ 도나 답글을 받고 다시 온 손님(28)과 가장 최근 손님의 리뷰와 답글. 도나를 쓰는 이유.
//   ④ 이번 달 가장 많이 나간 메뉴 세 개 (인스타 피드에 올리는 숫자와 같다).
// 견주는 모양은 하나: 화살표 + 숫자(갈색 굵게) + 많아요/적어요. 빨강·초록은 쓰지 않는다
// (사장님이 쓰는 금융 앱은 빨강이 오름이라 뜻이 엇갈린다). 요일 막대와 범례, 같은 숫자 되풀이, 이번 달 예상은 뺐다.

/** diff_label 만 갈색 굵게. "지난주보다 5만 원 많아요" */
function DiffLine({ text, diff, up, size }: { text: string; diff: string; up: boolean; size: 'big' | 'small' }) {
  const { scale } = useLayout();
  const i = text.indexOf(diff);
  const variant = size === 'big' ? 'bodyStrong' : 'label';
  const bold = size === 'small' ? styles.bold : undefined;
  return (
    <View style={styles.diff}>
      <View style={{ paddingTop: size === 'big' ? space.s4 : 3 }}>
        <Icon name={up ? 'arrowUp' : 'arrowDown'} size={Math.round((size === 'big' ? 20 : 16) * scale)} color="brand" />
      </View>
      <Txt variant={variant} style={[{ flex: 1 }, bold]}>
        {i < 0 ? (
          text
        ) : (
          <>
            {text.slice(0, i)}
            <Txt variant={variant} color="brand" style={styles.bold}>
              {diff}
            </Txt>
            {text.slice(i + diff.length)}
          </>
        )}
      </Txt>
    </View>
  );
}

/** ① 오늘 지금까지: 큰 숫자, 그 아래 오늘 막대, 지난주 같은 요일 이맘때(빈 막대), 차이 한 줄. 숫자는 한 번씩만. */
function Today({ p }: { p: Sales['primary'] }) {
  const { type } = useLayout();
  const max = Math.max(p.amount, p.compare_amount, 1);
  const pct = (n: number) => `${Math.max(2, Math.round((n / max) * 100))}%` as const;
  return (
    <Surface gap={space.s8}>
      <Txt variant="label" color="ink2">
        {p.label}
      </Txt>
      <Txt variant="display" style={{ fontSize: type.display.fontSize + 8, lineHeight: type.display.lineHeight + 6 }} accessibilityRole="header">
        {p.amount_label}
      </Txt>
      <View style={[styles.bar, styles.barNow, { width: pct(p.amount) }]} />
      <Txt variant="label" color="ink2">
        {`${p.compare_label} ${p.compare_amount_label}`}
      </Txt>
      <View style={[styles.bar, styles.barThen, { width: pct(p.compare_amount) }]} />
      <DiffLine text={p.short_text} diff={p.diff_label} up={p.direction === 'up'} size="big" />
    </Surface>
  );
}

/** ② 이번 주 · 이번 달: 같은 모양 두 칸을 나란히. */
function Period({ label, amount, compare, diff, up, diffText }: { label: string; amount: string; compare: string | null; diff: string; up: boolean; diffText: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Surface gap={space.s4}>
        <Txt variant="label" color="ink2">
          {label}
        </Txt>
        <Txt variant="title">{amount}</Txt>
        {compare ? (
          <>
            <Txt variant="label" color="ink2" style={{ marginTop: space.s4 }}>
              {compare}
            </Txt>
            <DiffLine text={diffText} diff={diff} up={up} size="small" />
          </>
        ) : null}
      </Surface>
    </View>
  );
}

/** ③ 도나 답글을 받고 다시 온 손님. '답글 덕분에'가 아니라 다시 온 사실만 적는다. 리뷰 칸은 D-11 모양. */
function Revisits({ r }: { r: Sales['revisits'] }) {
  const { scale } = useLayout();
  const latest = r.latest;
  return (
    <Surface>
      <View style={{ gap: space.s4 }}>
        <Txt variant="label" color="ink2">
          {r.label}
        </Txt>
        <View style={styles.countRow}>
          <Txt variant="display">{r.count_label}</Txt>
          <Txt variant="label" color="ink2" style={{ paddingBottom: space.s4 }}>
            {r.last_week_label}
          </Txt>
        </View>
      </View>
      {latest ? (
        <>
          <View style={styles.divider} />
          <View style={{ gap: space.s4 }}>
            <Txt variant="label" color="ink2">
              가장 최근에 다시 온 손님
            </Txt>
            <NumText text={latest.came_back_label} />
          </View>
          <View style={styles.review}>
            <View style={styles.reviewHead}>
              <Stars rating={latest.review.rating} />
              <Txt variant="label" color="ink2">
                {latest.review.date_label}
              </Txt>
            </View>
            <Txt variant="bodyStrong">{`“${latest.review.text}”`}</Txt>
            <View style={styles.divider} />
            <View style={styles.reply}>
              <View style={{ paddingTop: space.s4 }}>
                <Icon name="message" size={Math.round(20 * scale)} color="brand" />
              </View>
              <Txt variant="body" color="ink2" style={{ flex: 1 }}>
                {latest.reply.text}
              </Txt>
            </View>
          </View>
        </>
      ) : null}
    </Surface>
  );
}

/** ④ 이번 달 가장 많이 나간 메뉴. 순위, 이름, 그릇 수 (숫자만 갈색 굵게). */
function Menus({ m }: { m: NonNullable<Sales['top_menus_month']> }) {
  return (
    <Surface>
      <Txt variant="label" color="ink2">
        {m.label}
      </Txt>
      {m.items.slice(0, 3).map((it, i) => (
        <View key={it.id} style={styles.menuRow}>
          <Txt variant="bodyStrong" color="brand" style={[styles.bold, styles.rank]}>
            {i + 1}
          </Txt>
          <Txt variant="bodyStrong" style={{ flex: 1 }} numberOfLines={1}>
            {it.label}
          </Txt>
          <NumText text={`${it.count}${m.unit}`} variant="label" />
        </View>
      ))}
    </Surface>
  );
}

export default function SalesScreen() {
  const { data, failed, reload } = useLoad(api.sales);
  const { wide } = useLayout();

  if (!data) {
    return (
      <Thread>
        {failed ? (
          <Pressable onPress={reload} accessibilityRole="button">
            <DonnaLine headline="매출을 못 불러왔어요" caption="여기를 누르면 다시 불러와요." />
          </Pressable>
        ) : null}
      </Thread>
    );
  }
  const { primary, week, month, revisits, top_menus_month } = data;
  const pair = (
    <View style={styles.pair}>
      <Period label={week.label} amount={week.total_label} compare={week.compare_label} diff={week.diff_label} diffText={week.diff_text} up={week.direction === 'up'} />
      <Period
        label={month.label}
        amount={month.amount_label}
        compare={month.has_last ? month.compare_label : null}
        diff={month.diff_label}
        diffText={month.diff_text}
        up={month.direction === 'up'}
      />
    </View>
  );
  const left = (
    <>
      <Today p={primary} />
      {pair}
    </>
  );
  const right = (
    <>
      <Revisits r={revisits} />
      {top_menus_month ? <Menus m={top_menus_month} /> : null}
    </>
  );
  // 태블릿 가로: 왼쪽에 매출 숫자(①②), 오른쪽에 다시 온 손님과 메뉴(③④).
  return <Thread>{wide ? <Columns left={left} right={right} /> : <>{left}{right}</>}</Thread>;
}

const styles = StyleSheet.create({
  bold: { fontFamily: 'NotoSansKR_700Bold' },
  diff: { flexDirection: 'row', alignItems: 'flex-start', gap: space.s4 },
  bar: { height: 12, borderRadius: 6 },
  barNow: { backgroundColor: colors.brand },
  // 지난번은 테두리만 있는 빈 막대 (선 색은 바탕과 대비가 모자라 ink3 테두리)
  barThen: { borderWidth: 1.5, borderColor: colors.ink3 },
  pair: { flexDirection: 'row', gap: space.s8 },
  countRow: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: space.s8 },
  divider: { height: 1, backgroundColor: colors.line },
  review: { backgroundColor: colors.brandSoft, borderRadius: radius.row, padding: space.s16, gap: space.s12 },
  reviewHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.s8 },
  reply: { flexDirection: 'row', alignItems: 'flex-start', gap: space.s8 },
  menuRow: { flexDirection: 'row', alignItems: 'center', gap: space.s12 },
  rank: { width: 16, textAlign: 'center' },
});
