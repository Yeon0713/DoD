import { Pressable, View } from 'react-native';

import { Cards } from '@/components/cards';
import { Chips, DonnaLine, GaugeBar, OwnerBubble } from '@/components/talk';
import { Thread } from '@/components/Thread';
import { Txt } from '@/components/Txt';
import { useConversation } from '@/lib/conversation';
import { colors, radius, space } from '@/theme/tokens';

// 홈. 대화가 곧 화면이다.
//   처음에는 도나가 준비해 둔 것을 보여 준다 (D-01).
//   사장님이 물으면 사장님 말(오른쪽) → 도나 말(왼쪽) → 카드 → 할 수 있는 말(오른쪽) 순서로 쌓인다 (D-03 ~ D-12).
export default function HomeScreen() {
  const { home, homeFailed, turn, caption, focus, callFirst, send, reloadHome } = useConversation();
  const say = (text: string) => send(text, 'chip');

  if (turn) {
    return (
      <Thread follow withDonna>
        {turn.briefing ? <GaugeBar step={turn.briefing.step} total={turn.briefing.total} /> : null}
        {turn.owner_said ? <OwnerBubble text={turn.owner_said} /> : null}
        {turn.headline ? <DonnaLine headline={turn.headline} caption={caption} /> : null}
        <Cards cards={turn.cards} focus={focus} />
        <Chips items={turn.suggestions} onPick={say} call={callFirst} />
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
              <Pressable
                onPress={reloadHome}
                accessibilityRole="button"
                style={{ height: 44, paddingHorizontal: space.s16, borderRadius: radius.pill, backgroundColor: colors.brand, justifyContent: 'center' }}
              >
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
      <Chips items={home.suggestions} onPick={say} call={callFirst} />
    </Thread>
  );
}
