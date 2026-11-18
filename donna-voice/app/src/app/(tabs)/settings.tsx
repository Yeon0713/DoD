import { useFocusEffect, useRouter } from 'expo-router';
import { Fragment, ReactNode, useCallback, useRef } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { notifySub, SettingsGroup, SettingsRow } from '@/components/settings';
import { DonnaLine } from '@/components/talk';
import { Thread } from '@/components/Thread';
import { Txt } from '@/components/Txt';
import { Columns, Switch, useLoad } from '@/components/ui';
import { api } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { useSession } from '@/lib/session';
import { voice } from '@/lib/voice';
import { colors, radius, space } from '@/theme/tokens';

// 설정 (Figma v0.2.1 G-05). 이전 앱(v0.2.0 전)의 설정에 지금 설정을 합쳤다. 사장님이 쓰는 것만 둔다
// (개발 화면, 개발자 대시보드, 시험 날짜는 개발자 대시보드로).
//   가게: 장사 시간(G-06), 알바생(알바생 기능을 연결하면)
//   도나에게 맡긴 일: 아쉬운 리뷰에 바로 답하기, 브리핑 알림(G-08, 기본 문 열기 1시간 전)
//   목소리와 마이크 / 연결된 곳 / 계정(G-07, 로그아웃은 여기 안으로)
// 이전 앱의 '알림 받는 시간(하루 3번)'과 '바쁜 장사 시간'은 뺐다: 브리핑은 부를 때 하고, 꼭 알 일 알림을 막지 않게.

export default function SettingsScreen() {
  const router = useRouter();
  const session = useSession();
  const { wide } = useLayout();
  const { data, failed, reload, setData } = useLoad(api.settings);
  const micOn = session.mic === 'granted' && voice.sttSupported();

  // 장사 시간·브리핑 알림 화면에서 저장하고 돌아오면 다시 불러온다 (처음 열 때는 useLoad 가 이미 불렀다).
  const first = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (first.current) {
        first.current = false;
        return;
      }
      reload();
    }, [reload]),
  );

  if (!data) {
    return (
      <Thread>
        {failed ? (
          <Pressable onPress={reload} accessibilityRole="button">
            <DonnaLine headline="설정을 못 불러왔어요" caption="여기를 누르면 다시 불러와요." />
          </Pressable>
        ) : null}
      </Thread>
    );
  }

  const setAutoReply = (on: boolean) => {
    setData({ ...data, negative_review_auto_reply: on });
    api.patchSettings({ negative_review_auto_reply: on }).then(setData).catch(reload);
  };
  const notify = data.briefing_notify;
  const login = session.login === 'naver' ? '네이버' : session.login === 'phone' ? '휴대폰' : null;

  const store = (
    <SettingsGroup title="가게">
      <SettingsRow icon="clock" title="장사 시간" value={data.hours.summary_label} onPress={() => router.push('/settings/hours')} />
      {data.staff_count != null ? <SettingsRow icon="users" title="알바생" value={`${data.staff_count}명`} /> : null}
      <SettingsRow icon="store" title="우리 가게 다시 찾기" onPress={() => router.push('/join/store?again=1')} />
    </SettingsGroup>
  );
  const jobs = (
    <SettingsGroup title="도나에게 맡긴 일">
      <SettingsRow
        icon="message"
        title="아쉬운 리뷰 바로 답하기"
        sub={data.negative_review_auto_reply ? '30분 안에 사과 답글을 달아요' : '브리핑 때 알려만 드려요'}
        right={<Switch on={data.negative_review_auto_reply === true} onChange={setAutoReply} label="아쉬운 리뷰 바로 답하기" />}
      />
      <SettingsRow icon="bell" title="브리핑 알림" sub={notifySub(notify)} value={notify.on ? notify.time_label : '꺼짐'} onPress={() => router.push('/settings/notify')} />
    </SettingsGroup>
  );
  const voiceGroup = (
    <SettingsGroup title="목소리와 마이크">
      <SettingsRow
        icon="volume"
        title="도나 목소리"
        sub={session.sound ? '소리 내어 알려 드려요' : '화면으로만 알려 드려요'}
        right={<Switch on={session.sound} onChange={session.setSound} label="도나 목소리" />}
      />
      <SettingsRow
        icon="mic"
        title="마이크"
        sub={micOn ? '“도나야” 하고 부르면 들어요' : '꺼져 있어요'}
        value={micOn ? '켜짐' : null}
        right={
          micOn ? null : (
            <Pressable onPress={() => router.push('/mic')} accessibilityRole="button" style={styles.smallBtn}>
              <Txt variant="label" color="brandInk">
                켜기
              </Txt>
            </Pressable>
          )
        }
      />
    </SettingsGroup>
  );
  const links = (
    <SettingsGroup title="연결된 곳">
      {data.platforms.map((p) => (
        <SettingsRow key={p.key} icon="link" title={p.name} value={p.connected ? '연결됨' : '연결 안 됨'} />
      ))}
    </SettingsGroup>
  );
  const account = (
    <SettingsGroup title="계정">
      <SettingsRow icon="user" title="계정" value={login} onPress={() => router.push('/settings/account')} />
    </SettingsGroup>
  );

  // 묶음 사이는 24 (주제가 바뀜). 태블릿 가로: 왼쪽에 가게와 맡긴 일, 오른쪽에 목소리, 연결, 계정.
  const column = (...groups: ReactNode[]) => (
    <View style={{ gap: space.s24 }}>
      {groups.map((g, i) => (
        <Fragment key={i}>{g}</Fragment>
      ))}
    </View>
  );
  return (
    <Thread>
      {wide ? <Columns left={column(store, jobs)} right={column(voiceGroup, links, account)} /> : column(store, jobs, voiceGroup, links, account)}
    </Thread>
  );
}

const styles = StyleSheet.create({
  smallBtn: { height: 44, paddingHorizontal: space.s16, borderRadius: radius.pill, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
});
