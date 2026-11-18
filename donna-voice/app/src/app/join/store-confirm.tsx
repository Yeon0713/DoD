import { Redirect, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { FailNote, JoinPage, Note } from '@/components/join';
import { Txt } from '@/components/Txt';
import { Button } from '@/components/ui';
import { ApiFailure } from '@/lib/api';
import { join, joinState, placeImage, StorePlace, storeMapUrl, WEEKDAY_KO, WEEKDAYS } from '@/lib/join';
import { useLayout } from '@/lib/layout';
import { colors, radius, space } from '@/theme/tokens';

// 이 가게가 맞나요? (이전 앱 06-2s). 고른 가게를 네이버 지도에서 읽어 보여 주고(저장 안 함), 맞으면 등록한다.
// 계정과 가게는 다음 화면의 사장님 확인이 끝나야 이어진다.
const JS_DAY = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
const won = (n: number | null) => (n ? `${n.toLocaleString('ko-KR')}원` : '가격 변동');

export default function StoreConfirmScreen() {
  const router = useRouter();
  const { margin } = useLayout();
  const again = useLocalSearchParams<{ again?: string }>().again === '1';
  const picked = joinState.picked;
  const [place, setPlace] = useState<StorePlace | null>(null);
  const [failed, setFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!picked) return;
    setFailed(false);
    join.preview(picked).then((r) => setPlace(r.place)).catch(() => setFailed(true));
  }, [picked]);
  useEffect(load, [load]);

  if (!picked) return <Redirect href="/join/store" />;
  const backToSearch = () => router.replace(again ? '/join/store?again=1' : '/join/store');
  const map = (
    <Image
      source={{ uri: storeMapUrl({ lat: picked.lat, lng: picked.lng, level: 17, markers: [picked], selected: 0, w: 720, h: 460 }) }}
      accessibilityLabel={`${picked.name} 위치 지도`}
      style={{ height: 230, marginHorizontal: -margin, backgroundColor: colors.line }}
      resizeMode="cover"
    />
  );

  const register = async () => {
    if (!place) return;
    setSaving(true);
    setSaveFailed(null);
    try {
      const res = await join.register(place.place_id, null);
      joinState.check = { checkId: null, storeId: res.store_id, storeName: place.name };
      router.push(again ? '/join/owner-check?again=1' : '/join/owner-check');
    } catch (e) {
      setSaveFailed(e instanceof ApiFailure ? e.message : '잠시 뒤 다시 해 주세요.');
    } finally {
      setSaving(false);
    }
  };

  if (!place) {
    return (
      <JoinPage
        progress={again ? undefined : 2}
        onBack={backToSearch}
        footer={
          failed ? (
            <>
              <Button label="다시 확인하기" onPress={load} />
              <Button kind="outline" label="다른 가게 찾기" onPress={backToSearch} />
            </>
          ) : undefined
        }
      >
        {map}
        <Txt variant="title" style={{ marginTop: space.s16 }}>
          {picked.name}
        </Txt>
        <Txt variant="label" color="ink2">
          {picked.address}
        </Txt>
        {failed ? (
          <View style={{ marginTop: space.s24 }}>
            <FailNote title="가게 정보를 읽지 못했어요" sub="네이버 지도가 잠시 답하지 않아요. 다시 확인하거나 다른 가게를 찾아 주세요" />
          </View>
        ) : (
          <View style={{ marginTop: space.s32, alignItems: 'center', gap: space.s12 }} accessibilityLiveRegion="polite">
            <ActivityIndicator color={colors.brand} size="large" />
            <Txt variant="body" color="ink2" center>
              네이버 지도에서 가게 정보를 확인하고 있어요
            </Txt>
          </View>
        )}
      </JoinPage>
    );
  }

  const today = JS_DAY[new Date().getDay()];
  const hasHours = Object.keys(place.weekly_hours).length > 0;
  return (
    <JoinPage
      progress={again ? undefined : 2}
      onBack={backToSearch}
      footer={
        <>
          {saveFailed ? <FailNote title="등록하지 못했어요" sub={saveFailed} /> : null}
          <Button label={saving ? '등록하는 중' : '네, 우리 가게예요'} disabled={saving} onPress={() => void register()} />
          <Pressable onPress={backToSearch} accessibilityRole="button" style={{ minHeight: 44, alignItems: 'center', justifyContent: 'center' }}>
            <Txt variant="label" color="ink2" style={{ textDecorationLine: 'underline' }}>
              아니에요, 다시 찾을게요
            </Txt>
          </Pressable>
        </>
      }
    >
      {map}
      <View style={{ paddingTop: space.s16 }}>
        <Txt variant="label" color="brand" style={styles.bold}>
          이 가게가 맞나요?
        </Txt>
        <View style={styles.nameRow}>
          <Txt variant="display" style={{ flexShrink: 1 }}>
            {place.name}
          </Txt>
          {place.category ? (
            <View style={styles.chip}>
              <Txt variant="label" color="brand">
                {place.category}
              </Txt>
            </View>
          ) : null}
        </View>
        <View style={{ gap: space.s4, paddingBottom: space.s16, marginTop: space.s8 }}>
          <View style={{ flexDirection: 'row', gap: space.s8, alignItems: 'flex-start' }}>
            <View style={{ paddingTop: 3 }}>
              <Icon name="store" size={18} color="ink2" />
            </View>
            <Txt variant="body" style={{ flex: 1 }}>
              {place.road_address}
            </Txt>
          </View>
          {place.address && place.address !== place.road_address ? (
            <Txt variant="label" color="ink2" style={{ paddingLeft: 26 }}>{`지번 ${place.address}`}</Txt>
          ) : null}
          {place.review_total ? (
            <Txt variant="label" color="ink2" style={{ paddingLeft: 26 }}>{`네이버 방문자 리뷰 ${place.review_total.toLocaleString('ko-KR')}개`}</Txt>
          ) : null}
        </View>
        {hasHours ? (
          <View style={styles.section}>
            <Txt variant="bodyStrong" style={styles.bold}>
              영업시간
            </Txt>
            {WEEKDAYS.map((d) => {
              const h = place.weekly_hours[d];
              const isToday = d === today;
              return (
                <View key={d} style={{ flexDirection: 'row', alignItems: 'center' }}>
                  <Txt variant="body" color={isToday ? 'brand' : 'ink2'} style={[{ width: 40 }, isToday && styles.bold]}>
                    {WEEKDAY_KO[d]}
                  </Txt>
                  <Txt variant="body" color={h ? 'ink' : 'ink2'} style={[{ flex: 1 }, isToday && styles.bold]}>
                    {h ? `${h.open} ~ ${h.close}` : '쉬어요'}
                  </Txt>
                  {isToday ? (
                    <Txt variant="label" color="brand">
                      오늘
                    </Txt>
                  ) : null}
                </View>
              );
            })}
            {place.break_time ? <Txt variant="label" color="ink2">{`브레이크 타임 ${place.break_time.start} ~ ${place.break_time.end}`}</Txt> : null}
            {place.closed_note ? (
              <Txt variant="label" color="ink2">
                {place.closed_note}
              </Txt>
            ) : null}
          </View>
        ) : null}
        <View style={styles.section}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Txt variant="bodyStrong" style={styles.bold}>
              메뉴
            </Txt>
            {place.menus.length ? (
              <Txt variant="label" color="ink2">{`${place.menus.length}개`}</Txt>
            ) : null}
          </View>
          {place.menus.length ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -margin }} contentContainerStyle={{ paddingHorizontal: margin, gap: space.s12 }}>
              {place.menus.map((m) => (
                <View key={m.name} style={{ width: 120 }}>
                  {m.photo ? (
                    <Image source={{ uri: placeImage(m.photo) }} accessibilityLabel={m.name} style={styles.menuPhoto} resizeMode="cover" />
                  ) : (
                    <View style={[styles.menuPhoto, { alignItems: 'center', justifyContent: 'center' }]}>
                      <Icon name="image" size={24} color="ink3" />
                    </View>
                  )}
                  <Txt variant="label" numberOfLines={1} style={{ marginTop: space.s4 }}>
                    {m.name}
                  </Txt>
                  <Txt variant="label" color="ink2">
                    {won(m.price)}
                  </Txt>
                </View>
              ))}
            </ScrollView>
          ) : (
            <Txt variant="label" color="ink2">
              네이버 지도에 올린 메뉴가 없어요. 가입한 뒤 네이버 플레이스에서 넣을 수 있어요
            </Txt>
          )}
        </View>
      </View>
      <View style={{ marginTop: space.s8 }}>
        <Note>네이버 지도 정보예요. 다른 점은 다음 화면에서 고칠 수 있어요</Note>
      </View>
    </JoinPage>
  );
}

const styles = StyleSheet.create({
  bold: { fontFamily: 'NotoSansKR_700Bold' },
  nameRow: { marginTop: space.s4, flexDirection: 'row', alignItems: 'center', gap: space.s8 },
  chip: { paddingHorizontal: space.s8, paddingVertical: 2, borderRadius: radius.pill, backgroundColor: colors.brandSoft },
  section: { borderTopWidth: 1, borderTopColor: colors.line, paddingVertical: space.s16, gap: space.s8 },
  menuPhoto: { width: 120, height: 96, borderRadius: radius.tile, backgroundColor: colors.line },
});
