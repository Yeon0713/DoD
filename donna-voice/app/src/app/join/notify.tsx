import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { FailNote, JoinPage, TitleWithDonna } from '@/components/join';
import { Txt } from '@/components/Txt';
import { Button, useLoad } from '@/components/ui';
import { api } from '@/lib/api';
import { useSession } from '@/lib/session';
import { useEnterApp } from '@/lib/useEnterApp';
import { colors, radius, space } from '@/theme/tokens';

// 마지막 단계: 브리핑 알림 시각 (이전 앱의 출근·퇴근 시간과 알림 시간 두 단계를 v0.2.1 에 맞게 하나로).
// 브리핑은 사장님이 부를 때 하고, 알림은 기본 문 열기 1시간 전이다. 고르면 그 가게로 앱에 들어간다 (마이크를 아직 안 켰으면 E-03 부터).
export default function JoinNotifyScreen() {
  const router = useRouter();
  const { storeId } = useSession();
  const enterApp = useEnterApp();
  const { data, failed } = useLoad(api.settings);
  const [time, setTime] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (data && time === null) setTime(data.briefing_notify.time);
  }, [data, time]);

  const done = async () => {
    if (!data || !time || !storeId || saving) return;
    setSaving(true);
    setError(false);
    try {
      await api.patchSettings({ briefing_notify: { on: true, time: time === data.briefing_notify.default_time ? null : time } });
      await enterApp(storeId);
    } catch {
      setError(true);
      setSaving(false);
    }
  };

  return (
    <JoinPage
      progress={6}
      onBack={() => router.replace('/join/reviews')}
      footer={
        <>
          {error ? <FailNote title="저장하지 못했어요" sub="다시 눌러 주세요" /> : null}
          <Button label={saving ? '준비하는 중' : '이대로 좋아요'} onPress={() => void done()} />
        </>
      }
    >
      <TitleWithDonna title="브리핑 알림을 언제 받을까요?" img="b4-0" sub="오늘 일정 브리핑을 들을 때가 되면 알려 드려요" />
      {failed ? (
        <View style={{ marginTop: space.s16 }}>
          <FailNote title="불러오지 못했어요" />
        </View>
      ) : null}
      {data ? (
        <View style={styles.card} accessibilityRole="radiogroup">
          {data.briefing_notify.options.map((o, i) => {
            const picked = o.time === time;
            return (
              <View key={o.time}>
                {i > 0 ? <View style={styles.rule} /> : null}
                <Pressable onPress={() => setTime(o.time)} accessibilityRole="radio" accessibilityState={{ checked: picked }} accessibilityLabel={`${o.label}, ${o.sub}`} style={styles.option}>
                  <View style={{ flex: 1 }}>
                    <Txt variant="bodyStrong" style={picked ? styles.bold : undefined}>
                      {o.label}
                    </Txt>
                    <Txt variant="label" color="ink2">
                      {o.is_default ? `${o.sub} (기본)` : o.sub}
                    </Txt>
                  </View>
                  <View style={{ width: 24, height: 24 }}>{picked ? <Icon name="check" size={24} color="brand" /> : null}</View>
                </Pressable>
              </View>
            );
          })}
        </View>
      ) : null}
    </JoinPage>
  );
}

const styles = StyleSheet.create({
  bold: { fontFamily: 'NotoSansKR_700Bold' },
  card: { marginTop: space.s16, backgroundColor: colors.surface, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, padding: space.s4 },
  rule: { height: 1, backgroundColor: colors.line, marginHorizontal: space.s12 },
  option: { flexDirection: 'row', alignItems: 'center', gap: space.s12, padding: space.s12, minHeight: 56 },
});
