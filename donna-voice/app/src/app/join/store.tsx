import { useLocalSearchParams, useRouter } from 'expo-router';
import { ComponentRef, useEffect, useRef, useState } from 'react';
import { Image, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { DonnaPic, FailNote, JoinPage } from '@/components/join';
import { Bone } from '@/components/motion';
import { Txt } from '@/components/Txt';
import { Button } from '@/components/ui';
import { join, joinState, SearchedPlace, storeMapUrl } from '@/lib/join';
import { colors, radius, space } from '@/theme/tokens';

// 우리 가게 찾기 (이전 앱 06-2). 네이버 지역 검색으로 많아야 5곳, 지도에 번호 핀. 설정 "우리 가게 다시 찾기"(?again=1)에서도 쓴다.
const CENTER = { lat: 37.2066, lng: 126.8273 }; // 처음 지도: 초옹장이 있는 화성 남양읍
const samePlace = (a: SearchedPlace | null, b: SearchedPlace) => !!a && a.name === b.name && a.address === b.address;

export default function StoreSearchScreen() {
  const router = useRouter();
  const again = useLocalSearchParams<{ again?: string }>().again === '1';
  const [query, setQuery] = useState('');
  const [searched, setSearched] = useState('');
  const [items, setItems] = useState<SearchedPlace[] | null>(null);
  const [state, setState] = useState<'idle' | 'loading' | 'failed'>('idle');
  const [picked, setPicked] = useState<SearchedPlace | null>(null);
  const input = useRef<ComponentRef<typeof TextInput>>(null);

  // 쓰는 동안 매번 찾지 않고, 쓰기를 멈추면 찾는다
  useEffect(() => {
    const t = setTimeout(() => setSearched(query.trim()), 400);
    return () => clearTimeout(t);
  }, [query]);
  useEffect(() => {
    if (searched.length < 2) {
      setItems(null);
      setState('idle');
      return;
    }
    let alive = true;
    setState('loading');
    join
      .search(searched)
      .then((r) => alive && (setItems(r.items), setState('idle')))
      .catch(() => alive && setState('failed'));
    return () => {
      alive = false;
    };
  }, [searched]);

  const list = items ?? [];
  const chosenIndex = list.findIndex((p) => samePlace(picked, p));
  const chosen = chosenIndex >= 0 ? list[chosenIndex] : null;
  const center = chosen ?? list[0] ?? CENTER;
  const map = storeMapUrl({
    lat: center.lat, lng: center.lng, level: chosen ? 16 : list.length > 1 ? 14 : list.length ? 16 : 15, markers: list, numbered: true,
    selected: chosen ? chosenIndex : list.length === 1 ? 0 : -2, w: 720, h: 400,
  });
  const confirm = () => {
    if (!chosen) return;
    joinState.picked = chosen;
    router.push(again ? '/join/store-confirm?again=1' : '/join/store-confirm');
  };

  return (
    <JoinPage
      progress={again ? undefined : 1}
      onBack={() => (again ? router.replace('/settings') : router.replace('/login'))}
      footer={
        <>
          {chosen ? (
            <Txt variant="label" color="ink2" center>
              {`${chosen.name}, ${chosen.address.split(' ').slice(1, 3).join(' ')}`}
            </Txt>
          ) : null}
          <Button label="이 가게로 할게요" onPress={confirm} disabled={!chosen} />
        </>
      }
    >
      <Txt variant="display" accessibilityRole="header">
        우리 가게를 찾아 주세요
      </Txt>
      <Txt variant="body" color="ink2" style={{ marginTop: space.s4 }}>
        네이버 지도에 올라 있는 가게에서 찾아요
      </Txt>
      <View style={styles.search}>
        <Icon name="search" size={22} color="ink2" />
        <TextInput
          ref={input}
          accessibilityLabel="가게 이름"
          placeholder="가게 이름, 동네 이름"
          placeholderTextColor={colors.ink3}
          value={query}
          onChangeText={setQuery}
          returnKeyType="search"
          onSubmitEditing={() => {
            setSearched(query.trim());
            input.current?.blur();
          }}
          style={styles.searchInput}
        />
        {query ? (
          <Pressable accessibilityRole="button" accessibilityLabel="지우기" hitSlop={10} onPress={() => setQuery('')} style={styles.clear}>
            <Icon name="x" size={14} color="ink2" />
          </Pressable>
        ) : null}
      </View>

      {state === 'loading' ? (
        <View style={{ marginTop: space.s16, gap: space.s12 }}>
          <Bone style={{ height: 200, borderRadius: radius.item }} />
          <Bone style={{ height: 72, borderRadius: radius.item }} />
          <Bone style={{ height: 72, borderRadius: radius.item }} />
        </View>
      ) : state === 'failed' ? (
        <View style={{ marginTop: space.s16 }}>
          <FailNote title="찾지 못했어요" sub="네이버 검색이 잠시 안 돼요. 조금 뒤에 다시 써 주세요" />
        </View>
      ) : searched.length >= 2 && items && list.length === 0 ? (
        <View style={{ marginTop: space.s24, alignItems: 'center', gap: space.s4 }}>
          <DonnaPic img="q-shrug" size={140} />
          <Txt variant="title">가게를 못 찾았어요</Txt>
          <Txt variant="body" color="ink2" center>
            동네 이름과 함께 써 보세요. 예: 화성 남양 칼국수
          </Txt>
        </View>
      ) : (
        <View style={{ marginTop: space.s16, gap: space.s16 }}>
          <Image source={{ uri: map }} accessibilityLabel={chosen ? `${chosen.name} 위치 지도` : '지도'} style={styles.map} resizeMode="cover" />
          {list.length ? (
            <View style={{ gap: space.s8 }}>
              <Txt variant="label" color="ink2">{`찾은 가게 ${list.length}곳`}</Txt>
              <View style={styles.list}>
                {list.map((p, i) => {
                  const on = i === chosenIndex;
                  return (
                    <Pressable
                      key={`${p.name}|${p.address}`}
                      onPress={() => setPicked(p)}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: on }}
                      accessibilityLabel={`${i + 1}번 ${p.name}, ${p.category}, ${p.address}`}
                      style={[styles.item, i > 0 && styles.itemRule, on && { backgroundColor: colors.brandSoft }]}
                    >
                      <View style={[styles.num, { backgroundColor: on ? colors.brand : colors.line }]}>
                        <Txt variant="label" color={on ? 'brandInk' : 'ink2'} style={styles.bold}>
                          {i + 1}
                        </Txt>
                      </View>
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.s8 }}>
                          <Txt variant="bodyStrong" style={[styles.bold, { flexShrink: 1 }]} numberOfLines={1}>
                            {p.name}
                          </Txt>
                          {p.category ? (
                            <Txt variant="label" color="ink2">
                              {p.category}
                            </Txt>
                          ) : null}
                        </View>
                        <Txt variant="label" color="ink2" numberOfLines={1}>
                          {p.address}
                        </Txt>
                      </View>
                      <View style={[styles.radio, on && { backgroundColor: colors.brand, borderColor: colors.brand }]}>{on ? <Icon name="check" size={14} color="brandInk" /> : null}</View>
                    </Pressable>
                  );
                })}
              </View>
              <Txt variant="label" color="ink2">
                우리 가게를 눌러 고른 뒤 아래 버튼을 눌러 주세요
              </Txt>
            </View>
          ) : null}
        </View>
      )}
    </JoinPage>
  );
}

const styles = StyleSheet.create({
  bold: { fontFamily: 'NotoSansKR_700Bold' },
  search: { marginTop: space.s16, height: 56, flexDirection: 'row', alignItems: 'center', gap: space.s12, paddingHorizontal: space.s16, borderRadius: radius.item, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface },
  searchInput: { flex: 1, fontSize: 18, fontFamily: 'NotoSansKR_500Medium', color: colors.ink, height: 56 },
  clear: { width: 24, height: 24, borderRadius: 12, backgroundColor: colors.line, alignItems: 'center', justifyContent: 'center' },
  map: { height: 200, borderRadius: radius.item, backgroundColor: colors.line },
  list: { borderRadius: radius.item, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface, overflow: 'hidden' },
  item: { flexDirection: 'row', alignItems: 'center', gap: space.s12, paddingHorizontal: space.s16, paddingVertical: space.s12, minHeight: 64 },
  itemRule: { borderTopWidth: 1, borderTopColor: colors.line },
  num: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  radio: { width: 24, height: 24, borderRadius: 12, borderWidth: 2, borderColor: colors.line, alignItems: 'center', justifyContent: 'center' },
});
