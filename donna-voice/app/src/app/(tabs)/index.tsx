import { useRouter } from 'expo-router';
import { useEffect } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Cards } from '@/components/cards';
import { Icon } from '@/components/Icon';
import { DonnaLine, GaugeBar, OwnerBubble } from '@/components/talk';
import { Thread } from '@/components/Thread';
import { Txt } from '@/components/Txt';
import { ActionCard, Notice } from '@/lib/api';
import { bus } from '@/lib/bus';
import { useConversation } from '@/lib/conversation';
import { useLayout } from '@/lib/layout';
import { colors, radius, space } from '@/theme/tokens';

// 홈. 대화가 곧 화면이다 (Figma v0.2.1 하루 시나리오).
//   처음에는 도나가 준비해 둔 것을 보여 준다 (D-07).
//   사장님이 물으면 사장님 말(오른쪽) → 도나 말(왼쪽) → 카드 순서로 쌓인다.
//   추천 답변(칩)은 없다. 사장님은 그냥 말한다. 도나는 듣기 알약 바로 위에 선다.
//   도나 알림(D-05, D-23)은 소리 한 번과 알림 카드로 온다. 영업 중 아쉬운 리뷰는 도나가 먼저 묻고(2026-11-18),
//   알바생이 교정 카드를 확인했다는 알림은 한 줄을 읽는다.
export default function HomeScreen() {
  const { home, homeFailed, turn, caption, focus, notice, reloadHome, announce } = useConversation();
  const router = useRouter();

  // 인스타 화면에서 "허용"을 누르고 돌아왔을 때 (D-02)
  useEffect(() => bus.on('instagram_connected', (say: string) => announce('인스타를 연결했어요', say)), [announce]);

  const onAction = (a: ActionCard['action']) => {
    if (a === 'instagram_connect') router.push('/instagram');
  };

  if (turn) {
    return (
      <Thread follow withDonna>
        {turn.briefing ? <GaugeBar step={turn.briefing.step} total={turn.briefing.total} /> : null}
        {turn.owner_said ? <OwnerBubble text={turn.owner_said} /> : null}
        {turn.headline ? <DonnaLine headline={turn.headline} caption={caption} /> : null}
        <Cards cards={turn.cards} focus={focus} onAction={onAction} />
      </Thread>
    );
  }

  if (notice) {
    return (
      <Thread withDonna>
        <NoticeCard notice={notice} />
      </Thread>
    );
  }

  if (!home) {
    return (
      <Thread withDonna>
        {homeFailed ? (
          <>
            <DonnaLine headline="준비한 것을 못 불러왔어요" caption="인터넷이 끊겼을 수 있어요." />
            <View style={{ alignItems: 'flex-end' }}>
              <Pressable onPress={reloadHome} accessibilityRole="button" style={styles.retry}>
                <Txt variant="label" color="brandInk">
                  다시 불러오기
                </Txt>
              </Pressable>
            </View>
          </>
        ) : null}
      </Thread>
    );
  }

  return (
    <Thread withDonna>
      <DonnaLine headline={home.headline} />
      <Cards cards={home.cards} />
    </Thread>
  );
}

/** 도나 알림 카드 (D-05, D-23). 누구에게서 온 알림인지, 언제, 한 줄. */
function NoticeCard({ notice }: { notice: Notice }) {
  const { scale } = useLayout();
  return (
    <View style={styles.notice} accessibilityRole="alert">
      <View style={styles.noticeHead}>
        <View style={styles.inline}>
          <Icon name="bell" size={Math.round(16 * scale)} color="ink2" />
          <Txt variant="label" color="ink2">
            도나 알림
          </Txt>
        </View>
        <Txt variant="label" color="ink2">
          {notice.time_label}
        </Txt>
      </View>
      <Txt variant="bodyStrong">{notice.text}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  retry: { height: 44, paddingHorizontal: space.s16, borderRadius: radius.pill, backgroundColor: colors.brand, justifyContent: 'center' },
  notice: { backgroundColor: colors.surface, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, padding: space.s16, gap: space.s4 },
  noticeHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  inline: { flexDirection: 'row', alignItems: 'center', gap: space.s4 },
});
