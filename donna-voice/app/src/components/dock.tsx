// 화면 아래에 늘 있는 것: 타이핑하는 도나, 듣기 알약, 메뉴바. 그리고 위쪽 머리.
import { usePathname, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Defs, Ellipse, RadialGradient, Stop } from 'react-native-svg';

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

/** 타이핑하는 도나. 평소에는 멈춰 있고, 사장님이나 도나가 말하는 동안에만 움직인다. */
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
  speaking: '도나가 말하고 있어요',
  not_understood: '한 번 더 말씀해 주세요',
  error: '지금은 답하기 어려워요',
  mic_off: '마이크가 꺼져 있어요',
};

/** 맨 아래 큰 알약. 도나가 듣는지 말하는지를 알려 준다. 듣는 동안에는 받아쓴 말이 여기 나타난다. */
export function ListeningPill() {
  const { voiceState, heard } = useConversation();
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
  // 마이크가 꺼져 있을 때만 누를 수 있다: 켜는 화면으로 간다.
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

/** 위쪽: 왼쪽에 날짜와 그 아래 매장 이름, 오른쪽에 소리. */
export function Header() {
  const { home } = useConversation();
  const { sound, setSound } = useSession();
  const { margin, scale, wide, contentMax } = useLayout();
  const insets = useSafeAreaInsets();
  const onHome = usePathname() === '/';
  // 날짜와 매장 이름은 아래 내용(게이지바, 도나 말의 세로 선, 카드)과 같은 왼쪽 선에서 시작한다.
  return (
    <View style={[styles.header, { paddingTop: Math.max(insets.top, space.s16) + space.s8, paddingHorizontal: margin }]}>
      <View style={[styles.headerInner, !wide && { maxWidth: contentMax }, wide && !onHome && { maxWidth: 960 }]}>
      <View style={{ flex: 1, gap: space.s4 }}>
        <Txt variant="label" color="ink2">
          {home?.date_label ?? deviceDate()}
        </Txt>
        <Txt variant="title" numberOfLines={1}>
          {home?.store.name ?? ' '}
        </Txt>
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
  header: { paddingBottom: space.s24, alignItems: 'center' },
  headerInner: { width: '100%', flexDirection: 'row', alignItems: 'center' },
  // 아이콘(24)의 오른쪽 끝이 오른쪽 여백 선에 오도록, 손이 닿는 칸(44)을 10만큼 밖으로 뺀다.
  soundBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', marginRight: -10 },
  tabs: { backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: space.s8 },
  tabsInner: { flexDirection: 'row', alignSelf: 'center', width: '100%', maxWidth: 720 },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.s4, minHeight: 56 },
});
