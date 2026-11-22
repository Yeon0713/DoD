// 도나의 답에 붙는 카드. 서버는 무엇인지(kind)만 알려 주고, 아이콘과 색은 여기서 정한다.
// v0.2.1: 줄에는 이름표가 없고, 카드 안 숫자는 굵은 갈색이다. 색은 갈색 하나(좋은·아쉬운 리뷰만 초록·빨강).
import { ReactNode } from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';

import { ActionCard, BarsCard, Card, ChecklistCard, CountsCard, ImagesCard, InstaPostCard, InviteCard, ManualCard, media, MenusCard, PeopleCard, QuoteCard, ReasonKind, ReplyListCard, ReviewCard, RowKind, RowsCard, ScheduledCard, TipCard } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { ColorName, colors, radius, space } from '@/theme/tokens';

import { Icon, IconName } from './Icon';
import { Txt } from './Txt';

const B = { tone: 'brand' as ColorName, soft: 'brandSoft' as ColorName };
const ROW_ICON: Record<RowKind, IconName> = {
  event: 'flag', game: 'trophy', reservation: 'calendar', group_reservation: 'users', schedule: 'calendar',
  reviews: 'message', scheduled_replies: 'clock', reply: 'message', briefing: 'sun', off: 'power', done: 'check',
  weather: 'rain', instagram: 'instagram', staff: 'clipboard', person: 'users', task: 'clipboard', ban: 'ban',
  warning: 'alert', time: 'clock', date: 'calendar', phone: 'phone', lock: 'lock', message: 'message', invite: 'mail',
  image: 'image', users: 'users', clock: 'clock',
};
const ROW_LOOK = Object.fromEntries(Object.entries(ROW_ICON).map(([k, icon]) => [k, { icon, ...B }])) as Record<RowKind, { icon: IconName; tone: ColorName; soft: ColorName }>;

/** 숫자와 단위(12명, 2팀, 오후 2시)는 굵은 갈색으로. 갈색 굵은 글씨는 '숫자' 한 가지 뜻이다. */
const NUM = /(\d+(?:[,.]\d+)*(?:\s?(?:만 원|그릇|가지|명|팀|개|건|번|시|분|원|월|일|등))?)/;
export function NumText({ text, variant = 'bodyStrong', numberOfLines }: { text: string; variant?: 'bodyStrong' | 'label' | 'body'; numberOfLines?: number }) {
  const parts = text.split(NUM);
  return (
    <Txt variant={variant} numberOfLines={numberOfLines}>
      {parts.map((p, i) => (i % 2 === 1 ? <Txt key={i} variant={variant} color="brand" style={{ fontFamily: 'NotoSansKR_700Bold' }}>{p}</Txt> : p))}
    </Txt>
  );
}

export const REASON_LOOK: Record<ReasonKind, { icon: IconName; tone: ColorName; soft: ColorName }> = {
  weather: { icon: 'rain', tone: 'calm', soft: 'calmSoft' },
  game: { icon: 'trophy', tone: 'busy', soft: 'busySoft' },
  event: { icon: 'flag', tone: 'busy', soft: 'busySoft' },
  weekend: { icon: 'users', tone: 'brand', soft: 'brandSoft' },
  season: { icon: 'sun', tone: 'done', soft: 'doneSoft' },
  reservation: { icon: 'calendar', tone: 'brand', soft: 'brandSoft' },
  lunch: { icon: 'utensils', tone: 'brand', soft: 'brandSoft' },
  weekday_to_weekend: { icon: 'users', tone: 'brand', soft: 'brandSoft' },
  weekend_next_peak: { icon: 'utensils', tone: 'brand', soft: 'brandSoft' },
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
  // 다 끝낸 것을 모아 보여 주는 목록 (H-12b '오늘 아침에 한 것'): 초록 동그라미 체크, 한 것, 그 아래 언제 무엇을
  if (card.rows.every((r) => r.kind === 'done')) {
    const dot = Math.round(40 * scale);
    return (
      <View style={{ gap: space.s8 }}>
        <Txt variant="bodyStrong">{card.title ?? '오늘 확인한 것'}</Txt>
        <Surface pad={0} gap={0}>
          {card.rows.map((r, i) => (
            <View key={r.id} style={[styles.doneRow, i > 0 && styles.doneLine]}>
              <View style={[styles.doneDot, { width: dot, height: dot, borderRadius: dot / 2 }]}>
                <Icon name="check" size={Math.round(22 * scale)} color="done" />
              </View>
              <View style={{ flex: 1 }}>
                <Txt variant="body">{r.value}</Txt>
                {r.sub ? (
                  <Txt variant="label" color="done">
                    {r.sub}
                  </Txt>
                ) : null}
              </View>
            </View>
          ))}
        </Surface>
      </View>
    );
  }
  const list = (
    <Surface pad={space.s4} gap={0}>
      {card.rows.map((r) => {
        // mono: 종류마다 색을 달리하지 않고 갈색 하나로만 쓴다 (색이 많으면 보기 불편하다)
        const look = mono ? { ...ROW_LOOK[r.kind], tone: 'brand' as ColorName, soft: 'brandSoft' as ColorName } : ROW_LOOK[r.kind];
        const on = focus.includes(r.id);
        return (
          <View key={r.id} style={[styles.row, on && { backgroundColor: colors.brandSoft }]}>
            <Tile icon={look.icon} tone={look.tone} soft={on ? 'surface' : look.soft} />
            <View style={styles.rowText}>
              <NumText text={r.value} numberOfLines={2} />
            </View>
          </View>
        );
      })}
    </Surface>
  );
  if (!card.note) return list;
  return (
    <View style={{ gap: space.s8 }}>
      {list}
      <Checked label={card.note} />
    </View>
  );
}

/** 카드 아래 '✓ 알바생 할 일에 넣음', 그림 아래 '✓ 스토리에 올림' (H-07, H-12). */
function Checked({ label }: { label: string }) {
  const { scale } = useLayout();
  return (
    <View style={[styles.inline, { justifyContent: 'center', gap: space.s4 }]}>
      <Icon name="check" size={Math.round(18 * scale)} color="brand" />
      <Txt variant="label" color="brand">
        {label}
      </Txt>
    </View>
  );
}

/** 예약해 둔 좋은 리뷰 답글 (H-09): 손님 리뷰 한 줄(흐리게)과 도나가 써 둔 답글. */
function ReplyList({ card }: { card: ReplyListCard }) {
  const { scale } = useLayout();
  return (
    <Surface gap={space.s12}>
      {card.items.map((it) => (
        <View key={it.id} style={{ gap: space.s4 }}>
          <Txt variant="label" color="ink2" numberOfLines={1}>
            {it.quote}
          </Txt>
          <View style={styles.reply}>
            <View style={{ paddingTop: 3 }}>
              <Icon name="message" size={Math.round(18 * scale)} color="ink2" />
            </View>
            <Txt variant="body" style={{ flex: 1 }}>
              {it.reply}
            </Txt>
          </View>
        </View>
      ))}
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

/** 별점은 별로만 보인다. "2점" 같은 숫자는 쓰지 않고 말로도 읽지 않는다 (D-11). */
export function Stars({ rating }: { rating: number }) {
  const { scale } = useLayout();
  return (
    <View style={styles.stars} accessibilityLabel={`별 ${rating}개`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Icon key={n} name="star" size={Math.round(18 * scale)} color="brand" filled={n <= rating} />
      ))}
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
  // 리뷰와 실제로 단 답글 (D-11): 별, 손님 말, 선, 말풍선 아이콘과 답글 원문
  const label = card.reply?.scheduled_label;
  return (
    <Surface>
      <Stars rating={card.rating} />
      <Txt variant="bodyStrong">{`“${card.text.replace(/[“”]/g, '')}”`}</Txt>
      {card.reply ? (
        <>
          <View style={styles.divider} />
          {label ? (
            <Txt variant="label" color="ink2">
              {label}
            </Txt>
          ) : null}
          <View style={styles.reply}>
            <View style={{ paddingTop: space.s4 }}>
              <Icon name="message" size={Math.round(20 * scale)} color="brand" />
            </View>
            <Txt variant="body" color="ink2" style={{ flex: 1 }}>
              {card.reply.text}
              {card.reply.removed ? (
                <Txt variant="body" color="ink3" style={{ textDecorationLine: 'line-through' }}>
                  {` ${card.reply.removed}`}
                </Txt>
              ) : null}
            </Txt>
          </View>
        </>
      ) : null}
    </Surface>
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

/** prefix: 숫자 앞말. 좋은 리뷰에서 찾은 것은 "리뷰 9개", 매출 탭의 메뉴는 앞말 없이 "38개". */
export function Bars({ card, prefix = '리뷰 ' }: { card: Pick<BarsCard, 'items' | 'unit' | 'title'>; prefix?: string }) {
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
            <NumText text={`${prefix}${it.count}${card.unit}`} variant="label" />
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
              <Txt variant="label" color="ink2">
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

/** 이번 달 많이 나간 메뉴 (D-03 사진 확인, D-14 인스타에 올릴 메뉴). */
function Menus({ card, focus }: { card: MenusCard; focus: string[] }) {
  const { scale } = useLayout();
  const size = Math.round(44 * scale);
  // 지금 읽는 카드는 테두리 하나로 알린다 (줄마다 칠하면 무거워 보인다)
  const on = focus.includes(card.id);
  return (
    <View style={[styles.surface, { padding: space.s4 }, on && { borderColor: colors.brand, borderWidth: 2, padding: space.s4 - 1 }]}>
      {card.items.map((m) => (
        <View key={m.id} style={styles.row}>
          <Image source={{ uri: media(m.photo_url) ?? undefined }} style={{ width: size, height: size, borderRadius: radius.tile }} resizeMode="cover" />
          <View style={styles.rowText}>
            {card.editable ? null : (
              <Txt variant="label" color="ink2">
                {m.rank}등
              </Txt>
            )}
            <Txt variant="bodyStrong" numberOfLines={1}>
              {m.name}
            </Txt>
            {card.editable ? <NumText text={`이번 달 ${m.count_label}`} variant="label" /> : null}
          </View>
          {card.editable ? (
            <Txt variant="label" color="ink2">
              바꾸기
            </Txt>
          ) : (
            <NumText text={m.count_label} variant="label" />
          )}
        </View>
      ))}
    </View>
  );
}

/** 글에 넣을 손님 리뷰 한 문장 (D-14). */
function Quote({ card, focus }: { card: QuoteCard; focus: string[] }) {
  const { scale } = useLayout();
  return (
    <View style={[styles.soft, focus.includes(card.id) && { borderWidth: 2, borderColor: colors.brand, padding: space.s16 - 2 }]}>
      <View style={styles.tagRow}>
        <Icon name="quote" size={Math.round(16 * scale)} color="brand" />
        <Txt variant="label" color="brand">
          {card.label}
        </Txt>
      </View>
      <Txt variant="bodyStrong">{card.text}</Txt>
    </View>
  );
}

/** 인스타 게시물 모양 그대로 (D-15). 사진은 세로 4:5. */
function InstaPost({ card }: { card: InstaPostCard }) {
  const { scale } = useLayout();
  const w = Math.round(220 * scale);
  return (
    <View style={{ alignItems: 'center' }}>
      <View style={[styles.post, { width: w }]}>
        <View style={styles.postHead}>
          <Image source={{ uri: media(card.logo_url) ?? undefined }} style={styles.postAvatar} />
          <Txt variant="label" style={{ flex: 1, fontSize: 12 }} numberOfLines={1}>
            {card.handle}
          </Txt>
          <Txt variant="label" color="ink2">
            ···
          </Txt>
        </View>
        <View style={{ width: w, height: Math.round((w * 5) / 4), backgroundColor: colors.brandSoft, justifyContent: 'flex-end' }}>
          {card.photo_url ? <Image source={{ uri: media(card.photo_url) ?? undefined }} style={StyleSheet.absoluteFill} resizeMode="cover" /> : null}
          <View style={[styles.postBadge]}>
            <Txt variant="label" style={{ color: '#fff', fontSize: 12 }}>
              {card.slide}/{card.slides}
            </Txt>
          </View>
          <View style={styles.postShade}>
            <Txt variant="label" style={{ color: '#fff', fontSize: 12 }}>
              {card.top_label}
            </Txt>
            <Txt variant="bodyStrong" style={{ color: '#fff' }} numberOfLines={1}>
              {card.title}
            </Txt>
          </View>
        </View>
        <View style={styles.postFoot}>
          <View style={[styles.inline, { gap: space.s12 }]}>
            <Icon name="heart" size={20} color="ink" />
            <Icon name="message" size={20} color="ink" />
            <Icon name="send" size={20} color="ink" />
          </View>
          <Txt variant="label" color="ink2" style={{ fontSize: 12 }} numberOfLines={1}>
            {card.caption}
          </Txt>
        </View>
      </View>
    </View>
  );
}

/** '9:16' → 9/16. 모르면 세로 2:3. */
function ratioOf(aspect?: string): number {
  const [w, h] = (aspect ?? '').split(':').map(Number);
  return w > 0 && h > 0 ? w / h : 2 / 3;
}

/** 그림 여러 장을 나란히 (비 오는 날 이벤트: 포스터, 스토리에 올릴 사진). 높이를 맞추고 각자 제 비율로, 잘리지 않게. */
function Images({ card, focus }: { card: ImagesCard; focus: string[] }) {
  const { scale } = useLayout();
  const h = Math.round((card.items.length === 1 ? 300 : 240) * scale); // 스토리 한 장이면 크게 (H-06)
  const on = focus.includes(card.id);
  return (
    <View style={[styles.inline, { justifyContent: 'center', alignItems: 'flex-start', gap: space.s12 }]}>
      {card.items.map((it) => (
        <View key={it.id} style={{ alignItems: 'center', gap: space.s8 }}>
          <View style={[styles.post, { width: Math.round(h * ratioOf(it.aspect)), height: h, backgroundColor: colors.brandSoft }, on && { borderColor: colors.brand }]}>
            <Image source={{ uri: media(it.photo_url) ?? undefined }} style={StyleSheet.absoluteFill} resizeMode="contain" accessibilityLabel={it.label} />
          </View>
          {it.checked ? (
            <Checked label={it.label} />
          ) : (
            <Txt variant="label" color="ink2">
              {it.label}
            </Txt>
          )}
        </View>
      ))}
    </View>
  );
}

/** 알바생에게 시킨 것 (D-24 다 했는지, D-33 취소). 안 된 것이 위, 끝난 것이 아래. */
function Checklist({ card }: { card: ChecklistCard }) {
  const { scale } = useLayout();
  return (
    <Surface>
      <Txt variant="label" color="ink2">
        {card.title}
      </Txt>
      {card.items.map((it) => (
        <View key={it.id} style={[styles.inline, { alignItems: 'flex-start' }]}>
          <View style={{ paddingTop: 4 }}>
            {it.tone === 'urgent' ? (
              // 긴급 알바생 할 일 (비 오는 날 이벤트 등): 알바생 화면 맨 위에 붉은 표시로 뜨는 것과 같은 표시
              <Icon name="alert" size={Math.round(20 * scale)} color="urgent" />
            ) : (
              <Icon name={it.state === 'done' ? 'check' : it.state === 'canceled' ? 'x' : 'clock'} size={Math.round(20 * scale)} color={it.state === 'todo' ? 'ink2' : 'brand'} />
            )}
          </View>
          <View style={{ flex: 1 }}>
            <Txt variant="bodyStrong">{it.title}</Txt>
            <NumText text={it.sub} variant="label" />
          </View>
        </View>
      ))}
    </Surface>
  );
}

/** 알바생 목록 (D-30 오늘 나온 알바생). */
function People({ card }: { card: PeopleCard }) {
  const { scale } = useLayout();
  return (
    <Surface>
      <Txt variant="label" color="ink2">
        {card.title}
      </Txt>
      {card.items.map((p) => (
        <View key={p.id} style={[styles.inline, { alignItems: 'flex-start' }]}>
          <View style={{ paddingTop: 4 }}>
            <Icon name="user" size={Math.round(20 * scale)} color="brand" />
          </View>
          <View style={{ flex: 1 }}>
            <Txt variant="bodyStrong">{p.name}</Txt>
            <NumText text={p.sub} variant="label" />
          </View>
        </View>
      ))}
    </Surface>
  );
}

/** 알바생에게 보낼 글과 초대 코드 (D-04). */
function Invite({ card }: { card: InviteCard }) {
  return (
    <Surface>
      <Txt variant="body">{card.message}</Txt>
      <View style={[styles.soft, { gap: space.s8 }]}>
        <View>
          <Txt variant="label" color="ink2">
            주소
          </Txt>
          <Txt variant="bodyStrong">{card.url}</Txt>
        </View>
        <View>
          <Txt variant="label" color="ink2">
            초대 코드
          </Txt>
          <Txt variant="title">{card.code}</Txt>
        </View>
      </View>
    </Surface>
  );
}

/** 기본 매뉴얼 세 묶음 (D-06). 묶음 이름은 작은 글씨로 위에 둔다. */
function Manual({ card }: { card: ManualCard }) {
  const icon: Record<ManualCard['groups'][number]['kind'], IconName> = { before_open: 'sunrise', open: 'utensils', closing: 'moon' };
  return (
    <Surface pad={space.s4} gap={0}>
      {card.groups.map((g) => (
        <View key={g.id} style={styles.row}>
          <Tile icon={icon[g.kind]} {...B} />
          <View style={styles.rowText}>
            <Txt variant="label" color="ink2">
              {g.label}
            </Txt>
            <Txt variant="bodyStrong">{g.text}</Txt>
          </View>
        </View>
      ))}
    </Surface>
  );
}

/** 말로 할 수 없는 한 번의 일 (D-01: 인스타 연결). */
function Action({ card, onAction }: { card: ActionCard; onAction?: (a: ActionCard['action']) => void }) {
  const { scale } = useLayout();
  return (
    <Pressable
      onPress={() => onAction?.(card.action)}
      accessibilityRole="button"
      style={({ pressed }) => [styles.action, { height: Math.round(56 * scale), opacity: pressed ? 0.85 : 1 }]}
    >
      <Txt variant="button" color="brandInk">
        {card.label}
      </Txt>
    </Pressable>
  );
}

/** 카드 묶음. 카드 사이는 16. */
export function Cards({ cards, focus = [], mono = true, onAction }: { cards: Card[]; focus?: string[]; mono?: boolean; onAction?: (a: ActionCard['action']) => void }) {
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
            return <Scheduled key={c.id} card={c} focus={focus} mono />;
          case 'menus':
            return <Menus key={c.id} card={c} focus={focus} />;
          case 'quote':
            return <Quote key={c.id} card={c} focus={focus} />;
          case 'insta_post':
            return <InstaPost key={c.id} card={c} />;
          case 'images':
            return <Images key={c.id} card={c} focus={focus} />;
          case 'checklist':
            return <Checklist key={c.id} card={c} />;
          case 'people':
            return <People key={c.id} card={c} />;
          case 'invite':
            return <Invite key={c.id} card={c} />;
          case 'manual':
            return <Manual key={c.id} card={c} />;
          case 'action':
            return <Action key={c.id} card={c} onAction={onAction} />;
          case 'reply_list':
            return <ReplyList key={c.id} card={c} />;
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
  doneRow: { flexDirection: 'row', alignItems: 'center', gap: space.s12, paddingVertical: space.s12, paddingHorizontal: space.s16 },
  doneLine: { borderTopWidth: 1, borderTopColor: colors.line },
  doneDot: { backgroundColor: colors.doneSoft, alignItems: 'center', justifyContent: 'center' },
  reply: { flexDirection: 'row', gap: space.s8 },
  soft: { backgroundColor: colors.brandSoft, borderRadius: radius.card, padding: space.s16, gap: space.s4 },
  tagRow: { flexDirection: 'row', alignItems: 'center', gap: space.s4 },
  barHead: { flexDirection: 'row', alignItems: 'center', gap: space.s8 },
  track: { height: 10, borderRadius: 5, backgroundColor: colors.line, overflow: 'hidden' },
  fill: { height: 10, borderRadius: 5, backgroundColor: colors.brand },
  tag: { flexDirection: 'row', alignItems: 'center', gap: space.s4, paddingVertical: space.s4, paddingHorizontal: space.s12, borderRadius: radius.pill },
  post: { backgroundColor: colors.surface, borderRadius: radius.tile, borderWidth: 1, borderColor: colors.line, overflow: 'hidden' },
  postHead: { flexDirection: 'row', alignItems: 'center', gap: space.s8, padding: space.s8 },
  postAvatar: { width: 24, height: 24, borderRadius: 12, borderWidth: 1, borderColor: colors.line },
  postBadge: { position: 'absolute', top: space.s8, right: space.s8, backgroundColor: 'rgba(0,0,0,0.45)', borderRadius: radius.pill, paddingHorizontal: space.s8 },
  postShade: { padding: space.s12, backgroundColor: 'rgba(0,0,0,0.35)' },
  postFoot: { padding: space.s8, gap: space.s4 },
  action: { borderRadius: radius.button, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  item: {
    flexDirection: 'row', alignItems: 'center', gap: space.s12, padding: space.s16,
    backgroundColor: colors.surface, borderRadius: radius.item, borderWidth: 1, borderColor: colors.line,
  },
});
