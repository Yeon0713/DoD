// 대화 줄기를 이루는 부품: 게이지바, 사장님 말풍선, 도나의 말. (v0.2.1부터 할 수 있는 말 칩은 없다)
import { StyleSheet, View } from 'react-native';

import { colors, radius, space } from '@/theme/tokens';

import { Txt } from './Txt';

/** 브리핑이 얼마나 남았는지. 숫자 없이 칸으로만 보인다. */
export function GaugeBar({ step, total }: { step: number; total: number }) {
  return (
    <View style={styles.gauge} accessibilityLabel={`브리핑 ${total}단계 가운데 ${step}단계`}>
      {Array.from({ length: total }, (_, i) => (
        <View key={i} style={[styles.gaugeCell, { backgroundColor: i < step ? colors.brand : colors.line }]} />
      ))}
    </View>
  );
}

/** 사장님이 방금 한 말. 카카오톡의 내 말풍선처럼 오른쪽에 붙는다. */
export function OwnerBubble({ text }: { text: string }) {
  return (
    <View style={styles.right}>
      <View style={styles.bubble}>
        <Txt variant="bodyStrong" color="brandInk">
          {text}
        </Txt>
      </View>
    </View>
  );
}

/** 도나의 말. 왼쪽 세로 선으로 구분한다. 첫마디는 한 줄, 그 아래는 지금 읽고 있는 문장. */
export function DonnaLine({ headline, caption }: { headline: string; caption?: string | null }) {
  return (
    <View style={styles.line}>
      <View style={styles.bar} />
      <View style={styles.lineText}>
        <Txt variant="title" numberOfLines={2}>
          {headline}
        </Txt>
        {caption ? (
          <Txt variant="body" color="ink2" numberOfLines={2}>
            {caption}
          </Txt>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  gauge: { flexDirection: 'row', gap: space.s4 },
  gaugeCell: { flex: 1, height: 6, borderRadius: 3 },
  right: { flexDirection: 'row', justifyContent: 'flex-end' },
  bubble: {
    maxWidth: '88%',
    backgroundColor: colors.brand,
    paddingVertical: space.s4,
    paddingHorizontal: space.s12,
    borderRadius: radius.bubble,
    borderTopRightRadius: 4,
  },
  line: { flexDirection: 'row', gap: space.s12 },
  bar: { width: 3, borderRadius: 2, backgroundColor: colors.brand },
  lineText: { flex: 1, gap: space.s4 },
});
