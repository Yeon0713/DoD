import { useRouter } from 'expo-router';
import { ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Surface } from '@/components/cards';
import { DonnaLine } from '@/components/talk';
import { Thread } from '@/components/Thread';
import { Txt } from '@/components/Txt';
import { Button, Columns, Switch, useLoad } from '@/components/ui';
import { api } from '@/lib/api';
import { useConversation } from '@/lib/conversation';
import { useSession } from '@/lib/session';
import { voice } from '@/lib/voice';
import { colors, radius, space } from '@/theme/tokens';

// 설정. 사장님이 알고 싶은 것: "도나에게 맡긴 것을 내가 끄고 켤 수 있나."
// 도나가 대신 하는 일(소리 내기, 듣기, 답글 달기)만 둔다.
function Row({ title, desc, right }: { title: string; desc?: string; right?: ReactNode }) {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <Txt variant="bodyStrong">{title}</Txt>
        {desc ? (
          <Txt variant="small" color="ink3">
            {desc}
          </Txt>
        ) : null}
      </View>
      {right}
    </View>
  );
}

function Label({ children }: { children: string }) {
  return (
    <Txt variant="small" color="ink3">
      {children}
    </Txt>
  );
}

export default function SettingsScreen() {
  const router = useRouter();
  const session = useSession();
  const { reset } = useConversation();
  const { data, failed, reload, setData } = useLoad(api.settings);
  const micOn = session.mic === 'granted' && voice.sttSupported();

  const setAutoReply = (on: boolean) => {
    if (!data) return;
    setData({ ...data, negative_review_auto_reply: on });
    api.patchSettings({ negative_review_auto_reply: on }).then(setData).catch(reload);
  };
  const logout = () => {
    reset();
    session.signOut();
    router.replace('/start');
  };

  // 태블릿 가로: 왼쪽에 도나가 하는 일, 오른쪽에 연결된 곳과 로그아웃.
  return (
    <Thread>
      <Columns
        left={
          <>
      <View style={styles.group}>
        <Label>도나가 말하고 듣는 것</Label>
        <Surface gap={0} pad={space.s4}>
          <Row title="도나 목소리" desc={session.sound ? '소리 내어 알려 드려요' : '화면으로만 알려 드려요'} right={<Switch on={session.sound} onChange={session.setSound} label="도나 목소리" />} />
          <View style={styles.divider} />
          <Row
            title="마이크"
            desc={micOn ? '“도나야” 하고 부르면 들어요' : '꺼져 있어요. 칩을 눌러 쓸 수 있어요'}
            right={
              micOn ? (
                <Txt variant="label" color="done">
                  켜짐
                </Txt>
              ) : (
                <Pressable onPress={() => router.push('/mic')} accessibilityRole="button" style={styles.smallBtn}>
                  <Txt variant="label" color="brandInk">
                    켜기
                  </Txt>
                </Pressable>
              )
            }
          />
        </Surface>
      </View>

      <View style={styles.group}>
        <Label>도나에게 맡긴 일</Label>
        {data ? (
          <Surface gap={0} pad={space.s4}>
            <Row
              title="아쉬운 리뷰에 바로 답하기"
              desc={data.negative_review_auto_reply ? '30분 안에 사과 답글을 달고 브리핑 때 알려 드려요' : '도나가 답하지 않고 브리핑 때 알려만 드려요'}
              right={<Switch on={data.negative_review_auto_reply === true} onChange={setAutoReply} label="아쉬운 리뷰에 바로 답하기" />}
            />
            <View style={styles.divider} />
            <Row title="오늘 일정 브리핑 준비" desc={`문 여는 ${data.open_time_label}보다 한 시간 먼저`} right={<Txt variant="label" color="ink2">{data.briefing_time_label}</Txt>} />
          </Surface>
        ) : failed ? (
          <Pressable onPress={reload} accessibilityRole="button">
            <DonnaLine headline="설정을 못 불러왔어요" caption="여기를 누르면 다시 불러와요." />
          </Pressable>
        ) : null}
      </View>

          </>
        }
        right={
          <>
      {data ? (
        <View style={styles.group}>
          <Label>도나가 리뷰를 읽어 오는 곳</Label>
          <Surface gap={0} pad={space.s4}>
            {data.platforms.map((p, i) => (
              <View key={p.key}>
                {i > 0 ? <View style={styles.divider} /> : null}
                <Row title={p.name} right={<Txt variant="label" color={p.connected ? 'done' : 'ink3'}>{p.connected ? '연결됨' : '연결 안 됨'}</Txt>} />
              </View>
            ))}
          </Surface>
        </View>
      ) : null}

      <View style={{ marginTop: space.s8 }}>
        <Button kind="outline" label="로그아웃" onPress={logout} />
      </View>
          </>
        }
      />
    </Thread>
  );
}

const styles = StyleSheet.create({
  group: { gap: space.s8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.s12, padding: space.s12, minHeight: 56 },
  divider: { height: 1, backgroundColor: colors.line, marginHorizontal: space.s12 },
  smallBtn: { height: 44, paddingHorizontal: space.s16, borderRadius: radius.pill, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
});
