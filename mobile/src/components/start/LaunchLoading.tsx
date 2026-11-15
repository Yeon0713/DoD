// 앱을 켤 때마다 첫 화면 위에 잠깐 덮는 로딩 화면 (Figma 10-m2 · 시작 모션 · 타이핑).
// 노트북을 두드리는 도나(6프레임, 원본 시트 '00 · 에셋 › DONNA / 타이핑 / 원본 시트'), 로고, 한 줄 소개.
// 아래에서는 첫 화면이 미리 그려지고, 한 바퀴(1.08초) 돈 뒤 흐려지며 사라진다. 누르면 바로 넘어간다.
import { useEffect, useRef, useState } from "react";
import { AccessibilityInfo, Animated, Image, Pressable, StyleSheet, View } from "react-native";
import { Text } from "@/components/ui/Text";
import tokens from "@/theme/tokens.json";

const LOGO = require("../../../assets/images/donna-logo.png");
const FRAMES = [
  require("../../../assets/donna/typing-1.png"),
  require("../../../assets/donna/typing-2.png"),
  require("../../../assets/donna/typing-3.png"),
  require("../../../assets/donna/typing-4.png"),
  require("../../../assets/donna/typing-5.png"),
  require("../../../assets/donna/typing-6.png"),
];
/** 프레임마다 머무는 시간(ms). Figma 컴포넌트 'DONNA / 모션 / 타이핑'과 같은 값, 한 바퀴 1.08초 */
const HOLD = [180, 180, 180, 180, 120, 240];
const LOOPS = 1;
const SHOW_MS = HOLD.reduce((a, b) => a + b, 0) * LOOPS;
const FADE_MS = 300;

export function LaunchLoading() {
  const [frame, setFrame] = useState(0);
  const [gone, setGone] = useState(false);
  const [opacity] = useState(() => new Animated.Value(1));
  const leaving = useRef(false);

  const leave = () => {
    if (leaving.current) return;
    leaving.current = true;
    Animated.timing(opacity, { toValue: 0, duration: FADE_MS, useNativeDriver: false }).start();
    // 화면이 뒤에 가려져 있으면 애니메이션이 멈출 수 있다. 끝나기를 기다리지 않고 시간이 되면 걷어 낸다
    setTimeout(() => setGone(true), FADE_MS);
  };

  // 움직임 줄이기를 켠 기기에서는 첫 프레임에 멈춰 둔다
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
    const done = setTimeout(leave, SHOW_MS);
    return () => {
      clearTimeout(timer);
      clearTimeout(done);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (gone) return null;

  return (
    <Animated.View style={[StyleSheet.absoluteFill, { opacity, backgroundColor: tokens.colors.paper, zIndex: 1000 }]}>
      <Pressable
        testID="launch-loading"
        accessibilityRole="progressbar"
        accessibilityLabel="도나를 불러오고 있어요"
        onPress={leave}
        style={{ flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 24 }}
      >
        <View style={{ alignItems: "center", gap: 16 }}>
          {/* 여섯 장을 겹쳐 두고 보이는 것만 바꾼다. 장마다 새로 불러오면 깜빡일 수 있다 */}
          <View style={{ width: 256, height: 256 }}>
            {FRAMES.map((src, k) => (
              <Image
                key={k}
                source={src}
                resizeMode="contain"
                accessibilityIgnoresInvertColors
                style={[StyleSheet.absoluteFill, { width: 256, height: 256, opacity: k === frame ? 1 : 0 }]}
              />
            ))}
          </View>
          <View style={{ alignItems: "center", gap: 8 }}>
            <Image source={LOGO} style={{ width: 132, height: 44 }} resizeMode="contain" accessibilityLabel="도나" />
            <View className="flex-row items-center justify-center gap-2">
              <View className="h-0.5 w-5 bg-line" />
              <Text className="text-small text-ink-3">사장님을 위한 AI 비서</Text>
              <View className="h-0.5 w-5 bg-line" />
            </View>
          </View>
        </View>
      </Pressable>
    </Animated.View>
  );
}
