// 움직임 (이전 앱에서 옮김).
//  LaunchLoading: 앱을 켤 때마다 첫 화면 위에 잠깐 덮는 로딩 화면 (Figma 10-m2 · 시작 모션 · 타이핑, 이전 앱 LaunchLoading.tsx).
//    노트북을 두드리는 도나 6프레임(Figma 'DONNA / 모션 / 타이핑'과 같은 시간, 한 바퀴 1.08초), 로고, 한 줄 소개.
//    아래에서는 첫 화면이 미리 그려지고, 한 바퀴 돈 뒤 흐려지며 사라진다. 누르면 바로 넘어간다. 움직임 줄이기를 켠 기기는 첫 프레임에 멈춘다.
//  Bone: 불러오는 동안 자리를 잡아 두는 회색 칸. 0.8초마다 숨 쉬듯 옅어졌다 짙어진다 (이전 앱 parts.tsx Bone).
import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Image, Platform, Pressable, StyleProp, StyleSheet, Text, View, ViewStyle } from 'react-native';

import { colors, space } from '@/theme/tokens';

const LOGO = require('@/assets/images/donna-logo.png');
const FRAMES = [
  require('@/assets/donna/typing-1.png'),
  require('@/assets/donna/typing-2.png'),
  require('@/assets/donna/typing-3.png'),
  require('@/assets/donna/typing-4.png'),
  require('@/assets/donna/typing-5.png'),
  require('@/assets/donna/typing-6.png'),
];
/** 프레임마다 머무는 시간(ms). 한 바퀴 1.08초 */
const HOLD = [180, 180, 180, 180, 120, 240];
const SHOW_MS = HOLD.reduce((a, b) => a + b, 0);
const FADE_MS = 300;

/** ready 가 될 때까지는 돌고, ready 가 되고 한 바퀴를 채우면 흐려지며 사라진다 */
export function LaunchLoading({ ready }: { ready: boolean }) {
  const [frame, setFrame] = useState(0);
  const [gone, setGone] = useState(false);
  const [minDone, setMinDone] = useState(false);
  const [opacity] = useState(() => new Animated.Value(1));
  const leaving = useRef(false);

  const leave = () => {
    if (leaving.current) return;
    leaving.current = true;
    Animated.timing(opacity, { toValue: 0, duration: FADE_MS, useNativeDriver: false }).start();
    // 화면이 가려져 있으면 애니메이션이 멈출 수 있다. 끝나기를 기다리지 않고 시간이 되면 걷어 낸다
    setTimeout(() => setGone(true), FADE_MS);
  };

  useEffect(() => {
    let reduce = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let i = 0;
    const tick = () => {
      timer = setTimeout(() => {
        if (reduce) return;
        i = (i + 1) % FRAMES.length;
        setFrame(i);
        tick();
      }, HOLD[i]);
    };
    AccessibilityInfo.isReduceMotionEnabled()
      .then((on) => (reduce = on))
      .catch(() => {});
    tick();
    const done = setTimeout(() => setMinDone(true), SHOW_MS);
    return () => {
      clearTimeout(timer);
      clearTimeout(done);
    };
  }, []);

  useEffect(() => {
    if (ready && minDone) leave();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, minDone]);

  if (gone) return null;
  return (
    <Animated.View style={[StyleSheet.absoluteFill, styles.cover, { opacity }]}>
      <Pressable accessibilityRole="progressbar" accessibilityLabel="도나를 불러오고 있어요" onPress={() => ready && leave()} style={styles.press}>
        <View style={{ alignItems: 'center', gap: space.s16 }}>
          {/* 여섯 장을 겹쳐 두고 보이는 것만 바꾼다. 장마다 새로 불러오면 깜빡일 수 있다 */}
          <View style={{ width: 256, height: 256 }}>
            {FRAMES.map((src, k) => (
              <Image key={k} source={src} resizeMode="contain" accessibilityIgnoresInvertColors style={[StyleSheet.absoluteFill, { width: 256, height: 256, opacity: k === frame ? 1 : 0 }]} />
            ))}
          </View>
          <View style={{ alignItems: 'center', gap: space.s8 }}>
            <Image source={LOGO} style={{ width: 132, height: 44 }} resizeMode="contain" accessibilityLabel="도나" />
            <Tagline />
          </View>
        </View>
      </Pressable>
    </Animated.View>
  );
}

/** "— 사장님을 위한 AI 비서 —" (Figma 한 줄 소개: 선 20 × 1.5, 사이 8, DoNA 03/Small ink-3) */
export function Tagline() {
  return (
    <View style={styles.tagline}>
      <View style={styles.rule} />
      <Text style={styles.taglineText}>사장님을 위한 AI 비서</Text>
      <View style={styles.rule} />
    </View>
  );
}

/** 불러오는 동안 자리 (0.55 ↔ 1 숨쉬기) */
export function Bone({ style }: { style?: StyleProp<ViewStyle> }) {
  const [v] = useState(() => new Animated.Value(0.55));
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(v, { toValue: 1, duration: 800, useNativeDriver: Platform.OS !== 'web' }),
        Animated.timing(v, { toValue: 0.55, duration: 800, useNativeDriver: Platform.OS !== 'web' }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [v]);
  return <Animated.View style={[{ borderRadius: 8, backgroundColor: colors.skeleton }, style, { opacity: v }]} />;
}

const styles = StyleSheet.create({
  cover: { backgroundColor: colors.paper, zIndex: 1000 },
  press: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.s24 },
  tagline: { flexDirection: 'row', alignItems: 'center', gap: space.s8 },
  rule: { width: 20, height: 1.5, backgroundColor: colors.line },
  taglineText: { fontFamily: 'NotoSansKR_500Medium', fontSize: 14, lineHeight: 20, letterSpacing: -0.14, color: colors.ink3 },
});
