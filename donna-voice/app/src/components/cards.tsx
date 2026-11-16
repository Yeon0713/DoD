// 도나의 답에 붙는 카드 여섯 가지. 서버는 무엇인지(kind)만 알려 주고, 아이콘과 색은 여기서 정한다.
import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { BarsCard, Card, CountsCard, ReasonKind, ReviewCard, RowKind, RowsCard, ScheduledCard, TipCard } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { ColorName, colors, radius, space } from '@/theme/tokens';

import { Icon, IconName } from './Icon';
import { Txt } from './Txt';

const ROW_LOOK: Record<RowKind, { icon: IconName; tone: ColorName; soft: ColorName }> = {
  event: { icon: 'flag', tone: 'busy', soft: 'busySoft' },
  game: { icon: 'trophy', tone: 'calm', soft: 'calmSoft' },
  reservation: { icon: 'calendar', tone: 'brand', soft: 'brandSoft' },
  group_reservation: { icon: 'users', tone: 'done', soft: 'doneSoft' },
  schedule: { icon: 'calendar', tone: 'brand', soft: 'brandSoft' },
  reviews: { icon: 'message', tone: 'calm', soft: 'calmSoft' },
  scheduled_replies: { icon: 'clock', tone: 'done', soft: 'doneSoft' },
  reply: { icon: 'message', tone: 'brand', soft: 'brandSoft' },
  briefing: { icon: 'sun', tone: 'brand', soft: 'brandSoft' },
  off: { icon: 'power', tone: 'brand', soft: 'brandSoft' },
  done: { icon: 'check', tone: 'done', soft: 'doneSoft' },
};

export const REASON_LOOK: Record<ReasonKind, { icon: IconName; tone: ColorName; soft: ColorName }> = {
  weather: { icon: 'rain', tone: 'calm', soft: 'calmSoft' },
  game: { icon: 'trophy', tone: 'busy', soft: 'busySoft' },
  event: { icon: 'flag', tone: 'busy', soft: 'busySoft' },
  weekend: { icon: 'users', tone: 'brand', soft: 'brandSoft' },
  season: { icon: 'sun', tone: 'done', soft: 'doneSoft' },
  reservation: { icon: 'calendar', tone: 'brand', soft: 'brandSoft' },
};

/** 흰 카드. 안쪽 여백 16. */
export function Surface({ children, pad = space.s16, gap = space.s12 }: { children: ReactNode; pad?: number; gap?: number }) {
  return <View style={[styles.surface, { padding: pad, gap }]}>{children}</View>;
}

/** 아이콘이 든 네모 칸. */
export function Tile({ icon, tone, soft }: { icon: IconName; tone: ColorName; soft: ColorName }) {
  const { scale } = useLayout();
  const size = Math.round(44 * scale);
  return (
    <View style={[styles.tile, { width: size, height: size, backgroundColor: colors[soft] }]}>
      <Icon name={icon} size={Math.round(24 * scale)} color={tone} />
    </View>
  );
}

function Rows({ card, focus, mono }: { card: RowsCard; focus: string[]; mono?: boolean }) {
  const { scale } = useLayout();
  // 다 끝낸 것을 모아 보여 주는 목록 (D-12)
  if (card.rows.every((r) => r.kind === 'done')) {
    return (
      <Surface>
        <Txt variant="small" color="ink3">
          오늘 확인한 것
        </Txt>
        {card.rows.map((r) => (
          <View key={r.id} style={styles.inline}>
            <Icon name="check" size={Math.round(20 * scale)} color="done" />
            <Txt variant="bodyStrong">{r.value}</Txt>
          </View>
        ))}
      </Surface>
    );
  }
  return (
    <Surface pad={space.s4} gap={0}>
      {card.rows.map((r) => {
        // mono: 종류마다 색을 달리하지 않고 갈색 하나로만 쓴다 (색이 많으면 보기 불편하다)
        const look = mono ? { ...ROW_LOOK[r.kind], tone: 'brand' as ColorName, soft: 'brandSoft' as ColorName } : ROW_LOOK[r.kind];
        const on = focus.includes(r.id);
        return (
          <View key={r.id} style={[styles.row, on && { backgroundColor: colors.brandSoft }]}>
            <Tile icon={look.icon} tone={look.tone} soft={on ? 'surface' : look.soft} />
            <View style={styles.rowText}>
              {r.label ? (
                <Txt variant="small" color="ink3">
                  {r.label}
                </Txt>
              ) : null}
              <Txt variant="bodyStrong" numberOfLines={2}>
                {r.value}
              </Txt>
            </View>
          </View>
        );
      })}
    </Surface>
  );
}

function Counts({ card }: { card: CountsCard }) {
  const { scale } = useLayout();
  return (
    <View style={styles.counts}>
      {card.items.map((it) => {
        const good = it.kind === 'positive';
        const tone: ColorName = good ? 'done' : 'urgent';
        return (
          <View key={it.id} style={[styles.count, { backgroundColor: colors[good ? 'doneSoft' : 'urgentSoft'] }]}>
            <Icon name={good ? 'smile' : 'frown'} size={Math.round(28 * scale)} color={tone} />
            <View>
              <Txt variant="label" color={tone}>
                {it.label}
              </Txt>
              <Txt variant="display" color={tone}>
                {it.count}
                {it.unit}
              </Txt>
            </View>
          </View>
        );
      })}
    </View>
  );
}

export function Stars({ rating }: { rating: number }) {
  const { scale } = useLayout();
  return (
    <View style={styles.inline}>
      <View style={styles.stars}>
        {[1, 2, 3, 4, 5].map((n) => (
          <Icon key={n} name="star" size={Math.round(18 * scale)} color="brand" filled={n <= rating} />
        ))}
      </View>
      <Txt variant="label" color="ink2">
        {rating}점
      </Txt>
    </View>
  );
}

const hhmm = (iso: string | null) => {
  if (!iso) return '';
  const d = new Date(iso);
  const h = d.getHours();
  const m = d.getMinutes();
  const part = h < 12 ? '오전' : h === 12 ? '낮' : h < 17 ? '오후' : h < 21 ? '저녁' : '밤';
  return `${part} ${h > 12 ? h - 12 : h}시${m ? ` ${m}분` : ''}`;
};

function Review({ card }: { card: ReviewCard }) {
  const { scale } = useLayout();
  if (card.variant === 'summary') {
    return (
      <Surface>
        <Stars rating={card.rating} />
        <Txt variant="bodyStrong">{card.text}</Txt>
        {card.reply ? (
          <>
            <View style={styles.divider} />
            <View style={styles.reply}>
              <View style={{ paddingTop: space.s4 }}>
                <Icon name="message" size={Math.round(20 * scale)} color="brand" />
              </View>
              <Txt variant="body" color="ink2" style={{ flex: 1 }}>
                {card.reply.text}
              </Txt>
            </View>
          </>
        ) : null}
      </Surface>
    );
  }
  // 전체 보기 (D-09): 리뷰 원문과, 도나가 올렸거나 올릴 답글
  const replyTitle = card.reply?.scheduled_label ?? (card.reply?.posted_at ? `도나가 ${hhmm(card.reply.posted_at)}에 올린 답글` : '도나가 쓴 답글');
  return (
    <View style={{ gap: space.s8 }}>
      <Surface>
        <Stars rating={card.rating} />
        <Txt variant="body">{card.text}</Txt>
      </Surface>
      {card.reply ? (
        <View style={styles.soft}>
          <Txt variant="small" color="brand">
            {replyTitle}
          </Txt>
          <Txt variant="body">{card.reply.text}</Txt>
        </View>
      ) : null}
    </View>
  );
}

const TIP_LOOK: Record<TipCard['kind'], { icon: IconName; title: string }> = {
  improve: { icon: 'bulb', title: '이렇게 고쳐 보세요' },
  keep: { icon: 'thumb', title: '이렇게 지켜 보세요' },
  prepare: { icon: 'bulb', title: '이렇게 준비해 보세요' },
};

export function Tip({ card }: { card: Pick<TipCard, 'kind' | 'text'> }) {
  const { scale } = useLayout();
  const look = TIP_LOOK[card.kind];
  return (
    <View style={styles.soft}>
      <View style={styles.tagRow}>
        <Icon name={look.icon} size={Math.round(18 * scale)} color="brand" />
        <Txt variant="small" color="brand">
          {look.title}
        </Txt>
      </View>
      <Txt variant="bodyStrong">{card.text}</Txt>
    </View>
  );
}

export function Bars({ card }: { card: Pick<BarsCard, 'items' | 'unit' | 'title'> }) {
  const max = Math.max(1, ...card.items.map((i) => i.count));
  return (
    <Surface gap={space.s16}>
      {card.title ? (
        <Txt variant="small" color="ink3">
          {card.title}
        </Txt>
      ) : null}
      {card.items.map((it) => (
        <View key={it.id} style={{ gap: space.s4 }}>
          <View style={styles.barHead}>
            <Txt variant="bodyStrong" style={{ flex: 1 }} numberOfLines={1}>
              {it.label}
            </Txt>
            <Txt variant="small" color="ink3">
              {it.count}
              {card.unit}
            </Txt>
          </View>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${Math.round((it.count / max) * 100)}%` }]} />
          </View>
        </View>
      ))}
    </Surface>
  );
}

/** 색이 찬 작은 알약은 꼬리표다. 누르는 것이 아니다. */
export function Tag({ kind, label, mono }: { kind: ReasonKind; label: string; mono?: boolean }) {
  const { scale } = useLayout();
  const look = mono ? { ...REASON_LOOK[kind], tone: 'brand' as ColorName, soft: 'brandSoft' as ColorName } : REASON_LOOK[kind];
  return (
    <View style={[styles.tag, { backgroundColor: colors[look.soft] }]}>
      <Icon name={look.icon} size={Math.round(14 * scale)} color={look.tone} />
      <Txt variant="small" color={look.tone}>
        {label}
      </Txt>
    </View>
  );
}

function Scheduled({ card, focus, mono }: { card: ScheduledCard; focus: string[]; mono?: boolean }) {
  const { scale } = useLayout();
  return (
    <View style={{ gap: space.s8 }}>
      {card.items.map((it) => {
        const on = focus.includes(it.id);
        return (
          <View key={it.id} style={[styles.item, on && { borderColor: colors.brand, borderWidth: 2, padding: space.s16 - 1 }]}>
            <View style={{ width: Math.round(64 * scale), alignItems: 'center' }}>
              <Txt variant="title">{it.day_label}</Txt>
              <Txt variant="small" color="ink3">
                {it.time_label}
              </Txt>
            </View>
            <View style={{ flex: 1, gap: space.s4, alignItems: 'flex-start' }}>
              <Tag kind={it.reason.kind} label={it.reason.label} mono={mono} />
              <Txt variant="bodyStrong" numberOfLines={2}>
                {it.text}
              </Txt>
            </View>
          </View>
        );
      })}
    </View>
  );
}

/** 카드 묶음. 카드 사이는 16. */
export function Cards({ cards, focus = [], mono = false }: { cards: Card[]; focus?: string[]; mono?: boolean }) {
  return (
    <>
      {cards.map((c) => {
        switch (c.type) {
          case 'rows':
            return <Rows key={c.id} card={c} focus={focus} mono={mono} />;
          case 'counts':
            return <Counts key={c.id} card={c} />;
          case 'review':
            return <Review key={c.id} card={c} />;
          case 'tip':
            return <Tip key={c.id} card={c} />;
          case 'bars':
            return <Bars key={c.id} card={c} />;
          case 'scheduled':
            return <Scheduled key={c.id} card={c} focus={focus} mono={mono} />;
          default:
            return null;
        }
      })}
    </>
  );
}

const styles = StyleSheet.create({
  surface: { backgroundColor: colors.surface, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line },
  tile: { borderRadius: radius.tile, alignItems: 'center', justifyContent: 'center' },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.s12, padding: space.s12, borderRadius: radius.row },
  rowText: { flex: 1 },
  inline: { flexDirection: 'row', alignItems: 'center', gap: space.s8 },
  stars: { flexDirection: 'row', gap: space.s4 },
  counts: { flexDirection: 'row', gap: space.s8 },
  count: { flex: 1, padding: space.s16, borderRadius: radius.card, gap: space.s8 },
  divider: { height: 1, backgroundColor: colors.line },
  reply: { flexDirection: 'row', gap: space.s8 },
  soft: { backgroundColor: colors.brandSoft, borderRadius: radius.card, padding: space.s16, gap: space.s4 },
  tagRow: { flexDirection: 'row', alignItems: 'center', gap: space.s4 },
  barHead: { flexDirection: 'row', alignItems: 'center', gap: space.s8 },
  track: { height: 10, borderRadius: 5, backgroundColor: colors.line, overflow: 'hidden' },
  fill: { height: 10, borderRadius: 5, backgroundColor: colors.brand },
  tag: { flexDirection: 'row', alignItems: 'center', gap: space.s4, paddingVertical: space.s4, paddingHorizontal: space.s12, borderRadius: radius.pill },
  item: {
    flexDirection: 'row', alignItems: 'center', gap: space.s12, padding: space.s16,
    backgroundColor: colors.surface, borderRadius: radius.item, borderWidth: 1, borderColor: colors.line,
  },
});
