import { Redirect, Slot, usePathname } from 'expo-router';
import { View } from 'react-native';

import { Donna, donnaMoves, Header, ListeningPill, TabBar } from '@/components/dock';
import { ConversationProvider, useConversation } from '@/lib/conversation';
import { useLayout } from '@/lib/layout';
import { useSession } from '@/lib/session';
import { colors, space } from '@/theme/tokens';

// 화면의 틀. 자리는 어느 화면에서나 같다.
//   위: 날짜와 매장 이름, 소리
//   가운데: 탭마다 바뀌는 곳
//   아래: 메뉴바
// 도나와 듣기 알약은 홈에만 있다. 이번 주, 매출, 설정은 눈으로 보는 화면이라
// 마이크가 켜져 있든 꺼져 있든 알릴 것이 없다.
function Shell() {
  const { wide, margin, donna, width } = useLayout();
  const { voiceState } = useConversation();
  const home = usePathname() === '/';
  const moving = donnaMoves(voiceState);

  if (wide && home) {
    // 태블릿 가로의 홈: 왼쪽 칸 가운데에 도나와 듣기 알약, 오른쪽에 대화.
    const left = Math.min(420, Math.max(320, Math.round(width * 0.36)));
    return (
      <View style={{ flex: 1, backgroundColor: colors.home }}>
        <Header />
        <View style={{ flex: 1, flexDirection: 'row' }}>
          <View style={{ width: left, paddingLeft: margin, paddingBottom: space.s16, justifyContent: 'center' }}>
            <View style={{ alignItems: 'center', marginBottom: -8 }}>
              <Donna size={donna} moving={moving} />
            </View>
            <ListeningPill />
          </View>
          <View style={{ flex: 1 }}>
            <Slot />
          </View>
        </View>
        <TabBar />
      </View>
    );
  }
  return (
    <View style={{ flex: 1, backgroundColor: colors.home }}>
      <Header />
      <View style={{ flex: 1 }}>
        <Slot />
      </View>
      {home ? (
        <View style={{ paddingHorizontal: margin, paddingBottom: space.s16, alignItems: 'center' }}>
          <View style={{ width: '100%', maxWidth: 600 }}>
            <ListeningPill />
          </View>
        </View>
      ) : null}
      <TabBar />
    </View>
  );
}

export default function TabsLayout() {
  const { signedIn } = useSession();
  if (!signedIn) return <Redirect href="/start" />;
  return (
    <ConversationProvider>
      <Shell />
    </ConversationProvider>
  );
}
