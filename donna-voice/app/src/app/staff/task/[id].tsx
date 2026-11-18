import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { BigButton, StaffFrame } from '@/components/staff';
import { Txt } from '@/components/Txt';
import { api, StaffTaskDetail } from '@/lib/api';
import { staffSession } from '@/lib/staffSession';
import { colors, radius, space } from '@/theme/tokens';

// F-08 할 일 자세히: 도나가 짧게 줄인 제목 아래에 사장님이 한 말을 그대로 붙인다.
export default function StaffTaskScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [task, setTask] = useState<StaffTaskDetail | null>(null);
  const signedIn = !!staffSession.get().token;
  const load = useCallback(() => {
    if (signedIn && id) api.staff.task(id).then(setTask).catch(() => {});
  }, [id, signedIn]);
  useEffect(load, [load]);
  if (!task || !signedIn) return <StaffFrame>{null}</StaffFrame>;
  const finish = async () => {
    if (task.must_confirm) await api.staff.confirm(task.id);
    else if (!task.done) await api.staff.done(task.id);
    router.back();
  };
  return (
    <StaffFrame bottom={task.done ? undefined : <BigButton label={task.must_confirm ? '확인' : '완료'} onPress={finish} />}>
      <Pressable onPress={() => router.back()} accessibilityRole="button" style={styles.back}>
        <Icon name="chevronLeft" size={20} color="ink2" />
        <Txt variant="label" color="ink2">
          할 일
        </Txt>
      </Pressable>
      <View style={{ gap: space.s4 }}>
        <Txt variant="label" color={task.urgent ? 'urgent' : 'brand'}>
          {task.tag}
        </Txt>
        <Txt variant="display">{task.title}</Txt>
      </View>
      {task.owner_words ? (
        <View style={styles.card}>
          <View style={styles.inline}>
            <Icon name={task.urgent ? 'alert' : 'mic'} size={16} color={task.urgent ? 'urgent' : 'brand'} />
            <Txt variant="label" color="ink2">
              {task.owner_words_label}
            </Txt>
          </View>
          <Txt variant="body">{task.owner_words}</Txt>
        </View>
      ) : null}
      {task.until ? (
        <View style={styles.card}>
          <Txt variant="bodyStrong">{task.until}</Txt>
        </View>
      ) : null}
    </StaffFrame>
  );
}

const styles = StyleSheet.create({
  back: { flexDirection: 'row', alignItems: 'center', gap: space.s4, height: 44 },
  card: { gap: space.s8, padding: space.s16, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface },
  inline: { flexDirection: 'row', alignItems: 'center', gap: space.s4 },
});
