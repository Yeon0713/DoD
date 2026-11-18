import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { SettingsGroup, SettingsRow, SubPage } from '@/components/settings';
import { Txt } from '@/components/Txt';
import { Button, Switch, useLoad } from '@/components/ui';
import { api } from '@/lib/api';
import { useLayout } from '@/lib/layout';
import { colors, radius, space } from '@/theme/tokens';

// 설정 > 브리핑 알림 (Figma v0.2.1 G-08). 브리핑은 사장님이 부를 때 한다.
// 알림은 기본 문 열기 1시간 전이고, 사장님이 문 열기 2시간 ~ 30분 전 가운데 고른다 (2026-11-16 결정).
// 기본을 고르면 time 을 비워 보내, 장사 시간을 바꿔도 1시간 전을 따라가게 한다.
export default function NotifyScreen() {
  const router = useRouter();
  const { scale } = useLayout();
  const { data, failed, reload } = useLoad(api.settings);
  const [on, setOn] = useState(true);
  const [time, setTime] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (data && time === null) {
      setOn(data.briefing_notify.on);
      setTime(data.briefing_notify.time);
    }
  }, [data, time]);

  if (!data || time === null) {
    return (
      <SubPage title="브리핑 알림">
        {failed ? (
          <Pressable onPress={reload} accessibilityRole="button">
            <Txt variant="bodyStrong">못 불러왔어요. 여기를 누르면 다시 불러와요.</Txt>
          </Pressable>
        ) : null}
      </SubPage>
    );
  }

  const notify = data.briefing_notify;
  const save = async () => {
    setSaving(true);
    setError(false);
    try {
      await api.patchSettings({ briefing_notify: { on, time: time === notify.default_time ? null : time } });
      router.back();
    } catch {
      setError(true);
      setSaving(false);
    }
  };

  return (
    <SubPage
      title="브리핑 알림"
      footer={
        <>
          {error ? (
            <Txt variant="label" color="urgent" accessibilityRole="alert">
              저장하지 못했어요. 다시 눌러 주세요.
            </Txt>
          ) : null}
          <Button label={saving ? '저장하는 중' : '저장하기'} onPress={save} />
        </>
      }
    >
      <SettingsGroup inset={false}>
        <SettingsRow title="알림 받기" sub="오늘 일정 브리핑을 들을 때가 되면 알려 드려요" right={<Switch on={on} onChange={setOn} label="브리핑 알림 받기" />} />
      </SettingsGroup>
      <View style={{ gap: space.s8, opacity: on ? 1 : 0.45 }}>
        <Txt variant="label" color="ink2" accessibilityRole="header">
          알림 시간
        </Txt>
        <View style={styles.card} accessibilityRole="radiogroup">
          {notify.options.map((o, i) => {
            const picked = o.time === time;
            return (
              <View key={o.time}>
                {i > 0 ? <View style={styles.rule} /> : null}
                <Pressable
                  onPress={() => setTime(o.time)}
                  disabled={!on}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: picked, disabled: !on }}
                  accessibilityLabel={`${o.label}, ${o.sub}${o.is_default ? ', 기본' : ''}`}
                  style={styles.option}
                >
                  <View style={{ flex: 1 }}>
                    <Txt variant="bodyStrong" style={picked ? styles.bold : undefined}>
                      {o.label}
                    </Txt>
                    <Txt variant="label" color="ink2">
                      {o.is_default ? `${o.sub} (기본)` : o.sub}
                    </Txt>
                  </View>
                  <View style={styles.mark}>{picked ? <Icon name="check" size={Math.round(24 * scale)} color="brand" /> : null}</View>
                </Pressable>
              </View>
            );
          })}
        </View>
      </View>
    </SubPage>
  );
}

const styles = StyleSheet.create({
  bold: { fontFamily: 'NotoSansKR_700Bold' },
  card: { backgroundColor: colors.surface, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, padding: space.s4 },
  rule: { height: 1, backgroundColor: colors.line, marginHorizontal: space.s12 },
  option: { flexDirection: 'row', alignItems: 'center', gap: space.s12, padding: space.s12, minHeight: 56 },
  mark: { width: 24, height: 24, alignItems: 'center', justifyContent: 'center' },
});
