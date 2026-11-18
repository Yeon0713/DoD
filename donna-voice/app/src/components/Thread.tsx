import { ComponentRef, ReactNode, useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useConversation } from '@/lib/conversation';
import { useLayout } from '@/lib/layout';
import { space } from '@/theme/tokens';

import { Donna, donnaMoves } from './dock';

/**
 * 가운데 구역. 내용을 위에서부터 쌓고, 덩어리 사이는 16.
 * 도나는 홈에서만 나온다 (withDonna).
 *   휴대폰: 내용 뒤, 듣기 알약 바로 위에 서 있다 (Figma).
 *   태블릿 세로: 내용 아래 남은 자리의 가운데에 선다.
 *   태블릿 가로: 여기가 아니라 왼쪽 칸 가운데에 선다 ((tabs)/_layout.tsx).
 * 내용이 도나 자리까지 내려오면 도나는 자리를 비켜 준다.
 */
export function Thread({ children, follow = false, withDonna = false }: { children: ReactNode; follow?: boolean; withDonna?: boolean }) {
  const { wide, margin, donna, contentMax, mode } = useLayout();
  const { voiceState, progress, turn } = useConversation();
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const [box, setBox] = useState(0);
  const [content, setContent] = useState(0);
  const moving = donnaMoves(voiceState);
  // 휴대폰: 도나는 알약 위로 8만큼 겹쳐 선다. 내용 끝(아래 여백 16 포함)이 도나 머리보다 위에 있을 때만 보인다.
  // 태블릿 세로: 내용 끝과 알약 사이 남은 자리의 가운데에 선다. 도나가 다 들어갈 때만 보인다.
  const centered = mode === 'tabletPortrait';
  const free = box - content;
  const roomForDonna = withDonna && !wide && box > 0 && content > 0 && (centered ? free >= donna + 16 : content <= box + 8 - donna);
  // 도나 그림은 감싸는 칸(높이 1.5배)의 아래쪽에 있다. 그림이 남은 자리의 가운데에 오도록 칸을 올려 놓는다.
  const donnaPlace = centered ? { top: content + (free - donna) / 2 - donna * 0.5 } : { bottom: -8 };
  // 내용이 화면보다 길면, 도나가 읽는 만큼 화면이 따라 내려간다. 손으로 밀지 않아도 지금 말하는 줄이 보인다.
  const turnId = turn?.turn_id;
  useEffect(() => {
    if (!follow) return;
    const over = Math.max(0, content - box);
    scroll.current?.scrollTo({ y: Math.round(over * progress), animated: true });
  }, [follow, progress, content, box, turnId]);
  return (
    <View style={styles.box} onLayout={(e) => setBox(e.nativeEvent.layout.height)}>
      {wide || !withDonna ? null : (
        <View style={[styles.donna, donnaPlace, { opacity: roomForDonna ? 1 : 0 }]} pointerEvents="none">
          <Donna size={donna} moving={moving && roomForDonna} />
        </View>
      )}
      <ScrollView
        ref={scroll}
        style={styles.box}
        contentContainerStyle={{ paddingHorizontal: margin, paddingBottom: space.s16, alignItems: 'center' }}
        onContentSizeChange={(_, h) => setContent(h)}
        showsVerticalScrollIndicator={false}
      >
        <View style={{ width: '100%', maxWidth: wide ? (withDonna ? 680 : 960) : contentMax, gap: space.s16 }}>{children}</View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { flex: 1 },
  donna: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
});
