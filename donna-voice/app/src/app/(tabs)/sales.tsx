import { Pressable, StyleSheet, View } from 'react-native';

import { Bars, Surface } from '@/components/cards';
import { Icon } from '@/components/Icon';
import { DonnaLine } from '@/components/talk';
import { Thread } from '@/components/Thread';
import { Txt } from '@/components/Txt';
import { Columns, useLoad } from '@/components/ui';
import { api } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { colors, space } from '@/theme/tokens';

// 매출. 사장님이 알고 싶은 것: "장사가 어떤가, 지난주보다 나은가, 뭐가 잘 팔리나."
//   큰 숫자 하나 (문 열기 전에는 어제, 문 연 뒤에는 오늘 지금까지)와 지난주 같은 요일 비교
//   이번 주 요일별 막대 (연한 막대는 지난주)
//   잘 팔린 메뉴 세 개
const CHART_H = 112;

/** 지난주보다 많은지 적은지. 화살표와 색으로 먼저 보이고, 글로도 읽힌다. */
function Trend({ up, text }: { up: boolean; text: string }) {
  return (
    <View style={styles.compare}>
      <View style={{ paddingTop: space.s4 }}>
        <Icon name={up ? 'arrowUp' : 'arrowDown'} size={20} color={up ? 'done' : 'urgent'} />
      </View>
      <Txt variant="bodyStrong" color={up ? 'done' : 'urgent'} style={{ flex: 1 }}>
        {text}
      </Txt>
    </View>
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
  const { primary, week, top_menus } = data;
  const up = primary.direction === 'up';

  const compare = (
      <Surface>
        <View style={styles.pair}>
          <View style={{ flex: 1 }}>
            <Txt variant="small" color="ink3">
              {primary.label}
            </Txt>
            <Txt variant="title">{primary.amount_label}</Txt>
          </View>
          <View style={{ flex: 1 }}>
            <Txt variant="small" color="ink3">
              {primary.compare_label}
            </Txt>
            <Txt variant="title" color="ink3">
              {primary.compare_amount_label}
            </Txt>
          </View>
        </View>
        <Trend up={up} text={primary.compare_text} />
      </Surface>
  );
  const chart = (
      <Surface>
        <Txt variant="small" color="ink3">
          이번 주
        </Txt>
        <View style={styles.chart} accessibilityLabel="이번 주 요일별 매출 막대">
          {week.bars.map((b) => {
            const last = Math.max(4, Math.round((b.last_week_amount / week.max_amount) * CHART_H));
            const now = b.amount ? Math.max(4, Math.round((b.amount / week.max_amount) * CHART_H)) : 0;
            return (
              <View key={b.date} style={styles.col}>
                <View style={styles.bars}>
                  <View style={[styles.bar, { height: last, backgroundColor: colors.line }]} />
                  <View style={[styles.bar, { height: now, backgroundColor: colors.brand }]} />
                </View>
                <Txt variant="small" color={b.is_today ? 'ink' : 'ink3'} style={b.is_today ? { fontFamily: 'NotoSansKR_700Bold' } : undefined}>
                  {b.weekday_label}
                </Txt>
              </View>
            );
          })}
        </View>
        <Txt variant="bodyStrong">이번 주 지금까지 {week.total_label}</Txt>
        <Trend up={week.direction === 'up'} text={week.compare_text} />
        <View style={styles.legend}>
          <View style={[styles.swatch, { backgroundColor: colors.brand }]} />
          <Txt variant="small" color="ink3">
            이번 주
          </Txt>
          <View style={[styles.swatch, { backgroundColor: colors.line, marginLeft: space.s8 }]} />
          <Txt variant="small" color="ink3">
            지난주
          </Txt>
        </View>
      </Surface>
  );
  const menus = (
      <Bars card={{ title: top_menus.label, unit: top_menus.unit, items: top_menus.items }} />
  );

  // 도나가 위에서 숫자를 말했으니, 카드는 견줄 것을 나란히 보여 준다.
  // 태블릿 가로: 왼쪽에 비교와 잘 팔린 메뉴, 오른쪽에 이번 주 막대.
  return (
    <Thread>
      <DonnaLine headline={data.headline} />
      {wide ? (
        <Columns
          left={
            <>
              {compare}
              {menus}
            </>
          }
          right={chart}
        />
      ) : (
        <>
          {compare}
          {chart}
          {menus}
        </>
      )}
    </Thread>
  );
}

const styles = StyleSheet.create({
  compare: { flexDirection: 'row', alignItems: 'flex-start', gap: space.s4 },
  pair: { flexDirection: 'row', gap: space.s12 },
  chart: { flexDirection: 'row', gap: space.s8, alignItems: 'flex-end' },
  col: { flex: 1, alignItems: 'center', gap: space.s4 },
  bars: { height: CHART_H, flexDirection: 'row', alignItems: 'flex-end', gap: 2 },
  bar: { width: 12, borderTopLeftRadius: 4, borderTopRightRadius: 4 },
  legend: { flexDirection: 'row', alignItems: 'center', gap: space.s4 },
  swatch: { width: 12, height: 12, borderRadius: 3 },
});
