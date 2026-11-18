import { useFocusEffect, useRouter } from 'expo-router';
import { ReactNode, useCallback, useEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, View } from 'react-native';

import { Icon, IconName } from '@/components/Icon';
import { FailNote, JoinPage, TitleWithDonna } from '@/components/join';
import { Bone } from '@/components/motion';
import { Txt } from '@/components/Txt';
import { Button } from '@/components/ui';
import { api, DayHours } from '@/lib/api';
import { join, NaverPlace, openSmartPlace, placeImage } from '@/lib/join';
import { useSession } from '@/lib/session';
import { colors, radius, space } from '@/theme/tokens';

// 가게 정보를 확인해 주세요 (이전 앱 06-2c). 네이버에서 불러온 장사 시간, 메뉴, 사진.
// 장사 시간은 여기서 고친다 (설정 > 장사 시간 화면). 메뉴와 사진은 네이버 플레이스에서 고친다: 도나는 바꾸지 않는다.

/** 같은 시간이 이어지는 요일을 묶는다: "월 ~ 금 10:30 ~ 20:30", "일 쉬어요" */
function weekLines(days: DayHours[]): string[] {
  const lines: string[] = [];
  let i = 0;
  while (i < days.length) {
    const key = days[i].closed ? 'off' : `${days[i].open}-${days[i].close}`;
    let j = i;
    while (j + 1 < days.length && (days[j + 1].closed ? 'off' : `${days[j + 1].open}-${days[j + 1].close}`) === key) j++;
    const span = i === j ? days[i].label : `${days[i].label} ~ ${days[j].label}`;
    lines.push(days[i].closed ? `${span} 쉬어요` : `${span} ${days[i].open} ~ ${days[i].close}`);
    i = j + 1;
  }
  return lines;
}

function Card({ icon, title, onEdit, children }: { icon: IconName; title: string; onEdit?: () => void; children: ReactNode }) {
  return (
    <View style={styles.card}>
      <View style={styles.cardHead}>
        <Icon name={icon} size={26} color="ink2" />
        <Txt variant="bodyStrong" style={[styles.bold, { flex: 1 }]}>
          {title}
        </Txt>
        {onEdit ? (
          <Pressable onPress={onEdit} accessibilityRole="button" accessibilityLabel={`${title} 고치기`} hitSlop={10} style={{ minHeight: 44, justifyContent: 'center' }}>
            <Txt variant="label" color="brand" style={[styles.bold, { textDecorationLine: 'underline' }]}>
              고치기
            </Txt>
          </Pressable>
        ) : null}
      </View>
      <View style={{ paddingLeft: 38, gap: space.s4 }}>{children}</View>
    </View>
  );
}

export default function StoreInfoScreen() {
  const router = useRouter();
  const { storeId } = useSession();
  const [place, setPlace] = useState<NaverPlace | null>(null);
  const [days, setDays] = useState<DayHours[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (storeId) join.place(storeId).then((r) => setPlace(r.place)).catch(() => setFailed(true));
  }, [storeId]);
  // 장사 시간 화면에서 고치고 돌아오면 다시 읽는다
  useFocusEffect(
    useCallback(() => {
      api.settings().then((s) => setDays(s.hours.days)).catch(() => setFailed(true));
    }, []),
  );

  const back = () => router.replace('/join/store');
  if (!place || !days) {
    return (
      <JoinPage progress={4} onBack={back}>
        <TitleWithDonna title="가게 정보를 확인해 주세요" sub="다르면 눌러서 고쳐 주세요" />
        {failed ? (
          <View style={{ marginTop: space.s16 }}>
            <FailNote title="불러오지 못했어요" sub="인터넷이 끊겼어요. 뒤로 가서 다시 해 주세요" />
          </View>
        ) : (
          <Bone style={{ marginTop: space.s16, height: 256, borderRadius: radius.item }} />
        )}
      </JoinPage>
    );
  }
  const names = place.menus.map((m) => m.name);
  const menuLine = `${names.slice(0, 3).join(', ')}${names.length > 3 ? ` 외 ${names.length - 3}개` : ''}`;
  return (
    <JoinPage progress={4} onBack={back} footer={<Button label="이대로 좋아요" onPress={() => router.push('/join/reviews')} />}>
      <TitleWithDonna title="가게 정보를 확인해 주세요" sub="다르면 눌러서 고쳐 주세요" />
      <View style={{ marginTop: space.s16, gap: space.s12 }}>
        <Card icon="clock" title="장사 시간" onEdit={() => router.push('/settings/hours')}>
          {weekLines(days).map((l) => (
            <Txt key={l} variant="body" color="ink2">
              {l}
            </Txt>
          ))}
        </Card>
        <Card icon="list" title={`메뉴 ${place.menus.length}개`} onEdit={openSmartPlace}>
          <Txt variant="body" color="ink2">
            {place.menus.length ? menuLine : '네이버 플레이스에 올린 메뉴가 없어요'}
          </Txt>
        </Card>
        <Card icon="image" title={`메뉴 사진 ${place.photo_count}장`} onEdit={openSmartPlace}>
          <Txt variant="body" color="ink2">
            인스타 피드에 올릴 때 써요
          </Txt>
          {place.logo ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.s8, marginTop: space.s4 }}>
              <Image source={{ uri: placeImage(place.logo) }} style={{ width: 40, height: 40 }} resizeMode="contain" accessibilityLabel="가게 로고" />
              <Txt variant="label" color="ink2" style={{ flex: 1 }}>
                소식에서 가게 로고도 찾았어요
              </Txt>
            </View>
          ) : null}
        </Card>
      </View>
    </JoinPage>
  );
}

const styles = StyleSheet.create({
  bold: { fontFamily: 'NotoSansKR_700Bold' },
  card: { gap: space.s4, padding: space.s16, borderRadius: radius.item, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: space.s12 },
});
