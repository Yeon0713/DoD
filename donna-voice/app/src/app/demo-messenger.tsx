import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { Txt } from '@/components/Txt';
import { api, Messenger } from '@/lib/api';
import { colors, radius, space } from '@/theme/tokens';

// 시연용 예시 메신저 (Figma v0.2.1 F-01 "사장님이 보낸 글 받기"). 알바생이 평소 쓰는 메신저(카카오톡)를 흉내 낸 화면이다.
// 실제 카카오톡을 쓰면 링크가 이 컴퓨터(localhost)를 가리켜 알바생 휴대폰에서 열리지 않으므로, 시연 화면(/demo)의
// 알바생 휴대폰에서만 이 화면으로 대신한다. 사장님이 "카카오톡으로 보내 줘"라고 하면 2초 안에 글이 도착한다.
// 링크를 누르면 알바생 입장 화면(/staff?code=…)으로 가고 초대 코드가 채워져 있다.
// 데이터: GET /v1/dev/messenger?to=하린 (server/voice/api/dev.py). 도나가 문자나 알림톡을 보내는 것이 아니다.
const BG = '#e9edf2';

export default function DemoMessenger() {
  const router = useRouter();
  const { to } = useLocalSearchParams<{ to?: string }>();
  const name = String(to ?? '하린');
  const [data, setData] = useState<Messenger | null>(null);

  const load = useCallback(() => api.dev.messenger(name).then(setData).catch(() => {}), [name]);
  useEffect(() => {
    void load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [load]);

  const items = data?.items ?? [];
  return (
    <View style={styles.page}>
      <View style={styles.head}>
        <Icon name="chevronLeft" size={22} color="ink" />
        <Txt variant="title">사장님</Txt>
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        {items.length === 0 ? (
          <Txt variant="label" color="ink3" center style={{ marginTop: space.s32 }}>
            {`${name} 씨의 메신저예요.\n사장님이 보낸 글이 여기에 와요.`}
          </Txt>
        ) : null}
        {items.map((m) => (
          <View key={m.id} style={{ gap: space.s8 }}>
            <View style={styles.datePill}>
              <Txt variant="small" color="ink2">
                {m.date_label}
              </Txt>
            </View>
            <View style={styles.row}>
              <View style={styles.avatar} />
              <View style={{ flex: 1, gap: space.s4 }}>
                <Txt variant="small" color="ink2">
                  사장님
                </Txt>
                <View style={styles.bubble}>
                  <Txt variant="body">{m.text}</Txt>
                  <Pressable onPress={() => router.push(m.link as never)} accessibilityRole="link" accessibilityLabel="알바생 할 일 페이지 열기">
                    <Txt variant="body" color="brand" style={{ textDecorationLine: 'underline' }}>
                      {m.url}
                    </Txt>
                  </Pressable>
                  <Txt variant="bodyStrong">{`초대 코드 ${m.code}`}</Txt>
                </View>
                <Pressable onPress={() => router.push(m.link as never)} style={styles.preview} accessibilityRole="link">
                  <View style={styles.previewTop}>
                    <Txt variant="title" color="brandInk">
                      D
                    </Txt>
                  </View>
                  <View style={{ padding: space.s12, gap: 2 }}>
                    <Txt variant="label">{`${data?.store.name ?? ''} 알바생`}</Txt>
                    <Txt variant="small" color="ink3">
                      donna.app
                    </Txt>
                  </View>
                </Pressable>
                <Txt variant="small" color="ink3">
                  {m.usable ? m.time_label : `${m.time_label} · 지금은 쓸 수 없는 코드예요`}
                </Txt>
              </View>
            </View>
          </View>
        ))}
      </ScrollView>
      <View style={styles.input}>
        <Txt variant="title" color="ink3">
          +
        </Txt>
        <Txt variant="label" color="ink3" style={{ flex: 1 }}>
          메시지 입력
        </Txt>
        <Icon name="send" size={18} color="ink2" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: BG },
  head: { flexDirection: 'row', alignItems: 'center', gap: space.s12, paddingHorizontal: space.s16, paddingTop: space.s24, paddingBottom: space.s12 },
  body: { padding: space.s16, gap: space.s16 },
  datePill: { alignSelf: 'center', paddingHorizontal: space.s12, paddingVertical: space.s4, borderRadius: radius.pill, backgroundColor: '#d5dbe3' },
  row: { flexDirection: 'row', gap: space.s8, alignItems: 'flex-start' },
  avatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.brandSoft },
  bubble: { gap: space.s8, padding: space.s12, borderRadius: radius.bubble, backgroundColor: colors.surface, maxWidth: 280 },
  preview: { maxWidth: 280, borderRadius: radius.bubble, overflow: 'hidden', backgroundColor: colors.surface },
  previewTop: { height: 72, backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center' },
  input: { flexDirection: 'row', alignItems: 'center', gap: space.s12, margin: space.s12, paddingHorizontal: space.s16, height: 44, borderRadius: radius.pill, backgroundColor: colors.surface },
});
