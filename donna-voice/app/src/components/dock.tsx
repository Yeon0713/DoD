// 화면 아래에 늘 있는 것: 타이핑하는 도나, 듣기 알약, 메뉴바. 그리고 위쪽 머리.
import { usePathname, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Defs, Ellipse, RadialGradient, Stop } from 'react-native-svg';

import { media } from '@/lib/api';
import { useConversation, VoiceState } from '@/lib/conversation';
import { useLayout } from '@/lib/layout';
import { useSession } from '@/lib/session';
import { colors, radius, space } from '@/theme/tokens';

import { Icon, IconName } from './Icon';
import { Txt } from './Txt';

const FRAMES = [
  require('@/assets/donna/typing-1.png'),
  require('@/assets/donna/typing-2.png'),
  require('@/assets/donna/typing-3.png'),
  require('@/assets/donna/typing-4.png'),
  require('@/assets/donna/typing-5.png'),
  require('@/assets/donna/typing-6.png'),
];
const FRAME_MS = [180, 180, 180, 180, 120, 240];

/** 도나가 타이핑하는 때: 마이크가 사장님 말을 알아듣는 동안(듣고 있어요, 받아쓰는 중, 답 기다리는 중)과 도나가 말하는 동안.
 *  시작 화면(Figma 10-m2)과 같은 6프레임 모션이다. 대기("도나야" 하고 불러 주세요), 못 알아들음, 마이크 꺼짐에는 멈춘다. */
export const donnaMoves = (s: VoiceState) => s === 'listening' || s === 'hearing' || s === 'waiting' || s === 'speaking';

/** 타이핑하는 도나. 평소에는 멈춰 있고, 마이크가 알아듣거나 도나가 말하는 동안에만 움직인다. */
export function Donna({ size, moving }: { size: number; moving: boolean }) {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    if (!moving) {
      setFrame(0);
      return;
    }
    let i = 0;
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      i = (i + 1) % FRAMES.length;
      setFrame(i);
      timer = setTimeout(tick, FRAME_MS[i]);
    };
    timer = setTimeout(tick, FRAME_MS[0]);
    return () => clearTimeout(timer);
  }, [moving]);
  return (
    <View style={{ width: size * 2, height: size * 1.5, alignItems: 'center', justifyContent: 'flex-end' }} pointerEvents="none">
      <Svg width={size * 2} height={size * 1.5} style={StyleSheet.absoluteFill}>
        <Defs>
          <RadialGradient id="glow" cx="50%" cy="50%" rx="50%" ry="50%">
            <Stop offset="0" stopColor={colors.surface} stopOpacity={0.95} />
            <Stop offset="1" stopColor={colors.surface} stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Ellipse cx={size} cy={size * 0.75} rx={size} ry={size * 0.75} fill="url(#glow)" />
      </Svg>
      <View style={{ width: size, height: size }}>
        {FRAMES.map((src, i) => (
          <Image key={i} source={src} style={[StyleSheet.absoluteFill, { width: size, height: size, opacity: i === frame ? 1 : 0 }]} resizeMode="contain" />
        ))}
      </View>
    </View>
  );
}

function Dots() {
  return (
    <View style={styles.dots}>
      {[1, 0.6, 0.3].map((o) => (
        <View key={o} style={[styles.dot, { opacity: o }]} />
      ))}
    </View>
  );
}

function Wave() {
  const [t, setT] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setT((v) => v + 1), 160);
    return () => clearInterval(id);
  }, []);
  const base = [10, 20, 26, 14, 22];
  return (
    <View style={styles.wave}>
      {base.map((h, i) => (
        <View key={i} style={[styles.waveBar, { height: 8 + ((h + ((t + i) % 3) * 6) % 20) }]} />
      ))}
    </View>
  );
}

const PILL_TEXT: Record<VoiceState, string> = {
  standby: '“도나야” 하고 불러 주세요',
  listening: '듣고 있어요',
  hearing: '',
  waiting: '',
  preparing: '도나 목소리를 준비하고 있어요',
  retry_audio: '음성을 재생하지 못했어요 · 다시 듣기',
  speaking: '도나가 말하고 있어요',
  not_understood: '한 번 더 말씀해 주세요',
  error: '지금은 답하기 어려워요',
  mic_off: '마이크가 꺼져 있어요',
};

/** 맨 아래 큰 알약. 도나가 듣는지 말하는지를 알려 준다. 듣는 동안에는 받아쓴 말이 여기 나타난다. */
export function ListeningPill() {
  const { voiceState, heard, retryAudio } = useConversation();
  const { scale } = useLayout();
  const router = useRouter();
  const hearing = voiceState === 'hearing' || voiceState === 'waiting';
  const text = hearing ? `“${heard}”` : PILL_TEXT[voiceState];
  const icon: IconName | null = voiceState === 'not_understood' || voiceState === 'error' ? 'help' : voiceState === 'mic_off' ? 'micOff' : null;
  const body = (
    <View style={[styles.pill, { height: Math.round(56 * scale) }, hearing && { borderColor: colors.brand, borderWidth: 2 }]}>
      {icon ? <Icon name={icon} size={Math.round(22 * scale)} color="busy" /> : voiceState === 'standby' ? <Dots /> : <Wave />}
      <Txt variant="bodyStrong" numberOfLines={1} style={{ flexShrink: 1 }}>
        {text}
      </Txt>
    </View>
  );
  if (voiceState === 'retry_audio') {
    return <Pressable onPress={retryAudio} accessibilityRole="button" accessibilityLabel="다시 듣기">{body}</Pressable>;
  }
  if (voiceState === 'mic_off') {
    return (
      <Pressable onPress={() => router.push('/mic')} accessibilityRole="button" accessibilityLabel="마이크 켜기">
        {body}
      </Pressable>
    );
  }
  return body;
}

const DAYS = ['일', '월', '화', '수', '목', '금', '토'];
/** 서버에서 날짜를 못 받았을 때는 이 기기의 날짜를 쓴다. */
function deviceDate() {
  const d = new Date();
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${DAYS[d.getDay()]}요일`;
}

/** 위쪽 (v0.2.1 확정 포맷): 왼쪽에 가게 로고와 매장 이름, 그 아래 날짜. 오른쪽에 소리. 아래에 가게 상태 줄. */
export function Header() {
  const { home } = useConversation();
  const { sound, setSound } = useSession();
  const { margin, scale, wide, contentMax } = useLayout();
  const insets = useSafeAreaInsets();
  const onHome = usePathname() === '/';
  // 로고는 아래 내용(가게 상태 줄, 게이지바, 도나 말의 세로 선, 카드)과 같은 왼쪽 선에서 시작한다.
  const logo = media(home?.store.logo_url);
  const box = Math.round(48 * scale);
  const status = home?.store_status;
  return (
    <View style={[styles.header, { paddingTop: Math.max(insets.top, space.s16) + space.s8, paddingHorizontal: margin }]}>
      <View style={[styles.headerInner, !wide && { maxWidth: contentMax }, wide && !onHome && { maxWidth: 960 }]}>
      <View style={styles.store}>
        <View style={[styles.logo, { width: box, height: box }]}>
          {logo ? <Image source={{ uri: logo }} style={{ width: box, height: box }} resizeMode="cover" accessibilityLabel={`${home?.store.name} 로고`} /> : (
            <Txt variant="title" color="brand">{home?.store.name?.[0] ?? ' '}</Txt>
          )}
        </View>
        <View style={{ flex: 1 }}>
          <Txt variant="title" numberOfLines={1}>
            {home?.store.name ?? ' '}
          </Txt>
          <Txt variant="label" color="ink2">
            {home?.date_label ?? deviceDate()}
          </Txt>
        </View>
      </View>
      <Pressable
        onPress={() => setSound(!sound)}
        accessibilityRole="switch"
        accessibilityState={{ checked: sound }}
        accessibilityLabel={sound ? '소리 끄기' : '소리 켜기'}
        style={styles.soundBtn}
      >
        <Icon name={sound ? 'volume' : 'volumeOff'} size={Math.round(24 * scale)} color={sound ? 'ink2' : 'ink3'} />
      </Pressable>
      </View>
      {status ? (
        <View style={[styles.statusWrap, !wide && { maxWidth: contentMax }, wide && !onHome && { maxWidth: 960 }]}>
          <StoreStatus status={status} />
        </View>
      ) : null}
    </View>
  );
}

/** 가게 상태 줄: 점과 "영업 전/영업 중/영업 끝", 여는 시각이나 닫는 시각. 영업시간에서 바로 나온다. */
export function StoreStatus({ status }: { status: { state: 'before_open' | 'open' | 'closed'; label: string; detail: string } }) {
  const open = status.state === 'open';
  return (
    <View style={styles.status} accessibilityLabel={`${status.label}, ${status.detail}`}>
      <View style={[styles.statusDot, open ? { backgroundColor: colors.brand } : { borderWidth: 2, borderColor: colors.ink3 }]} />
      <Txt variant="label" color={open ? 'brand' : 'ink'} style={{ fontFamily: 'NotoSansKR_700Bold' }}>
        {status.label}
      </Txt>
      <Txt variant="label" color="ink2" numberOfLines={1} style={{ flexShrink: 1 }}>
        {status.detail}
      </Txt>
    </View>
  );
}

const TABS: { path: string; label: string; icon: IconName }[] = [
  { path: '/', label: '홈', icon: 'home' },
  // 이름은 하는 일을 말한다. 달력 모양이라는 것은 아이콘이 이미 알려 준다.
  { path: '/calendar', label: '일정', icon: 'calendar' },
  { path: '/sales', label: '매출', icon: 'chart' },
  { path: '/settings', label: '설정', icon: 'sliders' },
];

/** 맨 아래 메뉴바. 어느 화면 크기에서나 같은 자리에 있다. */
export function TabBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { scale } = useLayout();
  const { reset } = useConversation();
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.tabs, { paddingBottom: Math.max(insets.bottom, space.s8) }]}>
      <View style={styles.tabsInner}>
        {TABS.map((t) => {
          const on = pathname === t.path;
          return (
            <Pressable
              key={t.path}
              // 홈에 있을 때 홈을 다시 누르면 대화를 접고 준비해 둔 것으로 돌아간다.
              onPress={() => (on && t.path === '/' ? reset() : router.navigate(t.path as never))}
              accessibilityRole="tab"
              accessibilityState={{ selected: on }}
              style={styles.tab}
            >
              <Icon name={t.icon} size={Math.round(26 * scale)} color={on ? 'ink' : 'ink3'} />
              <Txt variant="small" color={on ? 'ink' : 'ink3'} style={on ? { fontFamily: 'NotoSansKR_700Bold' } : undefined}>
                {t.label}
              </Txt>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  dots: { flexDirection: 'row', gap: space.s4, alignItems: 'center' },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brand },
  wave: { flexDirection: 'row', gap: space.s4, alignItems: 'center', height: 28 },
  waveBar: { width: 4, borderRadius: 2, backgroundColor: colors.brand },
  pill: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.s8,
    paddingHorizontal: space.s16, borderRadius: radius.pill,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.line,
  },
  header: { paddingBottom: space.s16, alignItems: 'center' },
  headerInner: { width: '100%', flexDirection: 'row', alignItems: 'center' },
  store: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: space.s12 },
  logo: { borderRadius: radius.tile, borderWidth: 1, borderColor: colors.line, overflow: 'hidden', alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface },
  statusWrap: { width: '100%', marginTop: space.s12 },
  status: { flexDirection: 'row', alignItems: 'center', gap: space.s8, paddingVertical: 10, paddingHorizontal: space.s16, borderRadius: radius.tile, backgroundColor: colors.brandSoft },
  statusDot: { width: 10, height: 10, borderRadius: 5 },
  // 아이콘(24)의 오른쪽 끝이 오른쪽 여백 선에 오도록, 손이 닿는 칸(44)을 10만큼 밖으로 뺀다.
  soundBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', marginRight: -10 },
  tabs: { backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: space.s8 },
  tabsInner: { flexDirection: 'row', alignSelf: 'center', width: '100%', maxWidth: 720 },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.s4, minHeight: 56 },
});
