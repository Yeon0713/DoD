// 가입: 우리 가게 찾기 → 이 가게가 맞나요? → (가게 정보 확인) → 리뷰 불러오기 → 출근·퇴근 시간 → (알림 시간).
// 네이버 로그인만으로는 사장님 가게를 알 수 없어서, 사장님이 네이버 지도에서 가게를 찾아 고르고 확인한 뒤 등록한다.
// 등록하면 서버가 네이버 지도에서 가게 정보를 한 번 읽어 DB 에 저장하고 (server/app/modules/stores), 다음 로그인부터 이 가게로 들어온다.
// 리뷰는 배민, 네이버, 쿠팡이츠를 따로 불러온다. 지금은 버튼을 누르면 3초 기다린 뒤 목업 리뷰가 들어간다.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Redirect, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState, type ComponentRef } from "react";
import { ActivityIndicator, Image, Pressable, ScrollView, TextInput, View } from "react-native";
import { Icon, type IconName } from "@/components/icons/Icon";
import { DONNA_IMG } from "@/components/ui/donna";
import { back, go } from "@/components/ui/nav";
import { Bone, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Sheet } from "@/components/ui/Sheet";
import { FailNote, Note, SubPage } from "@/components/ui/sub";
import { Text } from "@/components/ui/Text";
import { account } from "@/lib/account";
import { api, ApiFailure, storeMapUrl, USE_MOCK, type ReviewSource, type SearchedPlace, type StorePlace } from "@/lib/api";
import { fromMin, suggestSlots, toMin, WEEKDAY_KO } from "@/lib/hours";
import { flashToast } from "@/lib/localStore";
import { naverProfile } from "@/lib/naverDemo";
import { currentNow } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";
import type { Weekday } from "@/types/contract";
import { startProblem } from "./AccountScreens";
import { TitleWithDonna, weekLines, weekStateOf } from "./HoursEditor";
import { errorText, param, pickedPlace, STEPS } from "./flow";

const C = tokens.colors;
const DAYS: Weekday[] = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
const JS_DAY: Weekday[] = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
const CHUNCHEON = { lat: 37.8747, lng: 127.7342 };
const EXAMPLES = ["춘천 피플스클럽", "석사동 돈가스", "효자동 국수"];

/** 이 기기 사장님 계정 열쇠. 같은 계정으로 다시 로그인하면 등록해 둔 가게로 들어온다 */
function ownerKey(): string | undefined {
  const naverId = naverProfile.read().value?.received.id;
  if (naverId) return `naver:${naverId}`;
  const phone = account.read().phone;
  return phone ? `phone:${phone}` : undefined;
}

/** 목업 모드: 서버 없이 고른 곳만으로 확인 화면을 그린다 */
function mockPlace(p: SearchedPlace): StorePlace {
  return { place_id: "mock", name: p.name, category: p.category, road_address: p.address, address: p.jibun_address, lat: p.lat, lng: p.lng, weekly_hours: {}, break_time: null, menus: [], review_total: 0, closed_note: null };
}

const won = (n: number | null) => (n ? `${n.toLocaleString("ko-KR")}원` : "가격 변동");
const samePlace = (a: SearchedPlace | null, b: SearchedPlace) => !!a && a.name === b.name && a.address === b.address;

function NumberBadge({ n, on }: { n: number; on: boolean }) {
  return (
    <View className={`h-7 w-7 items-center justify-center rounded-full ${on ? "bg-brand" : "bg-line"}`}>
      <Text className={`text-small font-bold ${on ? "text-brand-ink" : "text-ink-2"}`}>{n}</Text>
    </View>
  );
}

function Chip({ children }: { children: string }) {
  return (
    <View className="self-start rounded-full bg-brand-soft px-2.5 py-0.5">
      <Text className="text-small font-medium text-brand">{children}</Text>
    </View>
  );
}

/** 지도 그림. full 이면 화면 가로 끝까지 */
function MapImage({ uri, label, full, height = 200 }: { uri: string | null; label: string; full?: boolean; height?: number }) {
  if (!uri) return null;
  return (
    <Image
      testID="store-map"
      source={{ uri }}
      accessibilityLabel={label}
      style={{ height, marginHorizontal: full ? -24 : 0, borderRadius: full ? 0 : 16, backgroundColor: C.line }}
      resizeMode="cover"
    />
  );
}

/** 06-2 우리 가게 찾기. 설정 "우리 가게 다시 찾기"(?again=1)에서도 쓴다. 검토용 ?q=가게이름 */
export function StoreSearchScreen() {
  const params = useLocalSearchParams<{ again?: string; q?: string }>();
  const again = param(params.again) === "1";
  const [query, setQuery] = useState(param(params.q) ?? "");
  const [searched, setSearched] = useState(query.trim());
  const [picked, setPicked] = useState<SearchedPlace | null>(null);
  const input = useRef<ComponentRef<typeof TextInput>>(null);

  // 쓰는 동안 매번 찾지 않고, 쓰기를 멈추면 찾는다
  useEffect(() => {
    const t = setTimeout(() => setSearched(query.trim()), 400);
    return () => clearTimeout(t);
  }, [query]);
  const results = useQuery({ queryKey: ["naver-search", searched], queryFn: () => api.naverSearch(searched), enabled: searched.length >= 2, staleTime: 60 * 1000 });
  const items = searched.length >= 2 ? (results.data?.items ?? []) : [];
  const chosenIndex = items.findIndex((p) => samePlace(picked, p));
  const chosen = chosenIndex >= 0 ? items[chosenIndex] : null;
  const center = chosen ?? items[0] ?? CHUNCHEON;
  const mapUri = USE_MOCK
    ? null
    : storeMapUrl({ lat: center.lat, lng: center.lng, level: chosen ? 16 : items.length > 1 ? 14 : items.length ? 16 : 13, markers: items, numbered: true, selected: chosen ? chosenIndex : items.length === 1 ? 0 : -2, w: 720, h: 400 });

  const confirm = () => {
    if (!chosen) return;
    pickedPlace.write({ value: chosen });
    go(again ? "/start/store-confirm?again=1" : "/start/store-confirm");
  };

  return (
    <SubPage
      progress={again ? undefined : { total: STEPS, done: 1 }}
      onBack={() => back(again ? "/settings" : "/start")}
      footer={
        <>
          {chosen ? <Text className="text-center text-label text-ink-2">{`${chosen.name} · ${chosen.address.split(" ").slice(1, 3).join(" ")}`}</Text> : null}
          <PrimaryButton testID="store-search-ok" disabled={!chosen} onPress={confirm}>
            이 가게로 할게요
          </PrimaryButton>
        </>
      }
    >
      <Text className="text-display text-ink" accessibilityRole="header">
        {"우리 가게를\n찾아 주세요"}
      </Text>
      <Text className="mt-1.5 text-body text-ink-2">네이버 지도에 올라 있는 가게에서 찾아요</Text>

      <View className="mt-4 h-14 flex-row items-center gap-2.5 rounded-2xl border border-line bg-surface px-4" style={{ shadowColor: "#000", shadowOpacity: 0.06, shadowRadius: 8, shadowOffset: { width: 0, height: 2 } }}>
        <Icon name="search" size={22} color={C["ink-2"]} />
        <TextInput
          ref={input}
          testID="store-search"
          accessibilityLabel="가게 이름"
          placeholder="가게 이름, 동네 이름"
          value={query}
          onChangeText={setQuery}
          returnKeyType="search"
          onSubmitEditing={() => {
            setSearched(query.trim());
            input.current?.blur();
          }}
          className="flex-1 text-body text-ink"
          placeholderTextColor={C["ink-3"]}
        />
        {query ? (
          <Pressable accessibilityRole="button" accessibilityLabel="지우기" hitSlop={10} onPress={() => setQuery("")} className="h-6 w-6 items-center justify-center rounded-full bg-line">
            <Text className="text-small font-bold text-ink-2">✕</Text>
          </Pressable>
        ) : null}
      </View>

      {searched.length < 2 ? (
        <View className="mt-5 gap-3">
          <MapImage uri={mapUri} label="춘천 지도" />
          <Text className="text-label text-ink-2">이렇게 찾아 보세요</Text>
          <View className="flex-row flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <Pressable key={ex} accessibilityRole="button" onPress={() => setQuery(ex)} className="rounded-full border border-line bg-surface px-3.5 py-2 active:bg-brand-soft">
                <Text className="text-label text-ink">{ex}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      ) : results.isPending ? (
        <View className="mt-5 gap-3">
          <Bone className="h-[200px] w-full rounded-2xl" />
          <Bone className="h-[72px] w-full rounded-2xl" />
          <Bone className="h-[72px] w-full rounded-2xl" />
        </View>
      ) : results.isError ? (
        <View className="mt-5">
          <FailNote title="찾지 못했어요" sub={"네이버 검색이 잠시 안 돼요.\n조금 뒤에 다시 써 주세요"} />
        </View>
      ) : items.length > 0 ? (
        <View testID="store-results" className="mt-5">
          <MapImage uri={mapUri} label={chosen ? `${chosen.name} 위치 지도` : "찾은 가게 위치 지도"} />
          <Text className="mb-1 mt-4 text-label text-ink-2">{`찾은 가게 ${items.length}곳`}</Text>
          <View className="overflow-hidden rounded-2xl border border-line bg-surface">
            {items.map((p, i) => {
              const on = i === chosenIndex;
              return (
                <Pressable
                  key={`${p.name}|${p.address}`}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: on }}
                  accessibilityLabel={`${i + 1}번 ${p.name}, ${p.category}, ${p.address}`}
                  onPress={() => setPicked(p)}
                  className={`flex-row items-center gap-3 px-4 py-3.5 ${i > 0 ? "border-t border-line" : ""} ${on ? "bg-brand-soft" : "active:bg-paper"}`}
                >
                  <NumberBadge n={i + 1} on={on} />
                  <View className="flex-1 gap-0.5">
                    <View className="flex-row items-center gap-2">
                      <Text className="shrink text-body font-bold text-ink" numberOfLines={1}>
                        {p.name}
                      </Text>
                      {p.category ? <Text className="text-small text-ink-3">{p.category}</Text> : null}
                    </View>
                    <Text className="text-label text-ink-2" numberOfLines={1}>
                      {p.address}
                    </Text>
                  </View>
                  <View className={`h-6 w-6 items-center justify-center rounded-full border-2 ${on ? "border-brand bg-brand" : "border-line"}`}>
                    {on ? <Icon name="check" size={14} color={C["brand-ink"]} /> : null}
                  </View>
                </Pressable>
              );
            })}
          </View>
          <Text className="mt-2 text-small text-ink-3">우리 가게를 눌러 고른 뒤 아래 버튼을 눌러 주세요</Text>
        </View>
      ) : (
        <View className="mt-10 items-center" accessibilityRole="summary">
          <Image source={DONNA_IMG["q-shrug"]} style={{ width: 140, height: 140 }} resizeMode="contain" />
          <Text className="mt-3 text-title text-ink">가게를 못 찾았어요</Text>
          <Text className="mt-1 text-center text-body text-ink-2">{"동네 이름과 함께 써 보세요\n예: 춘천 효자동 국수"}</Text>
        </View>
      )}
    </SubPage>
  );
}

function Section({ title, right, children }: { title: string; right?: string; children: React.ReactNode }) {
  return (
    <View className="border-t border-line py-4">
      <View className="mb-2.5 flex-row items-baseline justify-between">
        <Text className="text-body font-bold text-ink">{title}</Text>
        {right ? <Text className="text-small text-ink-3">{right}</Text> : null}
      </View>
      {children}
    </View>
  );
}

/** 06-2s 이 가게가 맞나요? 네이버 지도에서 읽은 가게 정보를 보여 주고, 맞으면 등록한다 */
export function StoreConfirmScreen() {
  const again = param(useLocalSearchParams<{ again?: string }>().again) === "1";
  const picked = pickedPlace.useValue().value;
  const qc = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState<string | null>(null);
  const preview = useQuery({
    queryKey: ["store-preview", picked?.name, picked?.address],
    queryFn: () => api.storePreview(picked as SearchedPlace),
    enabled: !!picked && !USE_MOCK,
    retry: 0,
    staleTime: 10 * 60 * 1000,
  });

  if (!picked) return <Redirect href="/start/store" />;
  const place = USE_MOCK ? mockPlace(picked) : preview.data?.place;
  const backToSearch = () => back(again ? "/start/store?again=1" : "/start/store");
  const map = <MapImage full height={230} uri={storeMapUrl({ lat: picked.lat, lng: picked.lng, level: 17, markers: [picked], selected: 0, w: 720, h: 460 })} label={`${picked.name} 위치 지도`} />;

  const register = async () => {
    if (!place) return;
    setSaving(true);
    setSaveFailed(null);
    try {
      if (!USE_MOCK) {
        const res = await api.storeRegister(place.place_id, ownerKey());
        account.write({ storeId: res.store_id });
        // 앞서 본 다른 가게 데이터는 지우고 이 가게 것으로 새로 받는다
        qc.clear();
      }
      if (again) {
        flashToast("우리 가게를 바꿨어요", place.name);
        back("/settings");
      } else go("/start/naver-confirm");
    } catch (e) {
      setSaveFailed(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  if (!place) {
    return (
      <SubPage
        progress={again ? undefined : { total: STEPS, done: 2 }}
        onBack={backToSearch}
        footer={
          preview.isError ? (
            <>
              <PrimaryButton onPress={() => preview.refetch()}>다시 확인하기</PrimaryButton>
              <SecondaryButton onPress={backToSearch}>다른 가게 찾기</SecondaryButton>
            </>
          ) : null
        }
      >
        <View className="-mt-3">{map}</View>
        <Text className="mt-5 text-title text-ink">{picked.name}</Text>
        <Text className="mt-0.5 text-label text-ink-2">{picked.address}</Text>
        {preview.isError ? (
          <View className="mt-6">
            <FailNote title="가게 정보를 읽지 못했어요" sub={"네이버 지도가 잠시 답하지 않아요.\n다시 확인하거나 다른 가게를 찾아 주세요"} icon="refresh" />
          </View>
        ) : (
          <View className="mt-8 items-center gap-3" accessibilityLiveRegion="polite">
            <ActivityIndicator color={C.brand} size="large" />
            <Text className="text-body text-ink-2">네이버 지도에서 가게 정보를 확인하고 있어요</Text>
          </View>
        )}
      </SubPage>
    );
  }

  const today = JS_DAY[currentNow().getDay()];
  const hasHours = Object.keys(place.weekly_hours).length > 0;
  return (
    <SubPage
      progress={again ? undefined : { total: STEPS, done: 2 }}
      onBack={backToSearch}
      footer={
        <>
          {saveFailed ? (
            <View testID="store-confirm-failed" accessibilityRole="alert" className="flex-row items-center gap-2 rounded-xl bg-urgent-soft px-3 py-2.5">
              <Icon name="refresh" size={18} color={C.urgent} />
              <Text className="flex-1 text-label text-urgent">{`등록하지 못했어요. ${saveFailed}`}</Text>
            </View>
          ) : null}
          <PrimaryButton testID="store-confirm-yes" disabled={saving} onPress={register}>
            {saving ? "등록하는 중" : "네, 우리 가게예요"}
          </PrimaryButton>
          <Pressable testID="store-confirm-no" accessibilityRole="button" onPress={backToSearch} className="h-11 items-center justify-center">
            <Text className="text-label text-ink-2 underline">아니에요, 다시 찾을게요</Text>
          </Pressable>
        </>
      }
    >
      <View className="-mt-3">{map}</View>

      <View testID="store-confirm-info" className="pt-5">
        <Text className="text-label font-medium text-brand">이 가게가 맞나요?</Text>
        <View className="mt-1 flex-row items-center gap-2">
          <Text className="shrink text-display text-ink">{place.name}</Text>
          {place.category ? <Chip>{place.category}</Chip> : null}
        </View>
        <View className="mt-2 gap-1 pb-4">
          <View className="flex-row items-start gap-1.5">
            <Icon name="store" size={18} color={C["ink-2"]} />
            <Text className="flex-1 text-body text-ink">{place.road_address}</Text>
          </View>
          {place.address && place.address !== place.road_address ? <Text className="pl-6 text-small text-ink-3">{`지번 ${place.address}`}</Text> : null}
          {place.review_total ? <Text className="pl-6 text-small text-ink-3">{`네이버 방문자 리뷰 ${place.review_total.toLocaleString("ko-KR")}개`}</Text> : null}
        </View>

        {hasHours ? (
          <Section title="영업시간">
            <View className="gap-1.5">
              {DAYS.map((d) => {
                const h = place.weekly_hours[d];
                const isToday = d === today;
                return (
                  <View key={d} className="flex-row items-center">
                    <Text className={`w-10 text-body ${isToday ? "font-bold text-brand" : "text-ink-2"}`}>{WEEKDAY_KO[d]}</Text>
                    <Text className={`flex-1 text-body ${isToday ? "font-bold text-ink" : h ? "text-ink" : "text-ink-3"}`}>{h ? `${h.open} ~ ${h.close}` : "쉬어요"}</Text>
                    {isToday ? <Text className="text-small font-medium text-brand">오늘</Text> : null}
                  </View>
                );
              })}
              {place.break_time ? <Text className="mt-1 text-label text-ink-2">{`브레이크 타임 ${place.break_time.start} ~ ${place.break_time.end}`}</Text> : null}
              {place.closed_note ? <Text className="text-small text-ink-3">{place.closed_note}</Text> : null}
            </View>
          </Section>
        ) : null}

        <Section title="메뉴" right={place.menus.length ? `${place.menus.length}개` : undefined}>
          {place.menus.length ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -24 }} contentContainerStyle={{ paddingHorizontal: 24, gap: 10 }}>
              {place.menus.map((m) => (
                <View key={m.name} style={{ width: 120 }}>
                  {m.photo ? (
                    <Image source={{ uri: m.photo }} accessibilityLabel={m.name} style={{ width: 120, height: 96, borderRadius: 12, backgroundColor: C.line }} resizeMode="cover" />
                  ) : (
                    <View className="items-center justify-center rounded-xl bg-line" style={{ width: 120, height: 96 }}>
                      <Icon name="image" size={24} color={C["ink-3"]} />
                    </View>
                  )}
                  <Text className="mt-1.5 text-label font-medium text-ink" numberOfLines={1}>
                    {m.name}
                  </Text>
                  <Text className="text-small text-ink-2">{won(m.price)}</Text>
                </View>
              ))}
            </ScrollView>
          ) : (
            <Text className="text-label text-ink-2">네이버 지도에 올린 메뉴가 없어요. 가입한 뒤 네이버 플레이스에서 넣을 수 있어요</Text>
          )}
        </Section>
      </View>

      <View className="mt-2">
        <Note icon="shield">네이버 지도 정보예요. 다른 점은 다음 화면에서 고칠 수 있어요</Note>
      </View>
    </SubPage>
  );
}

const SOURCES: { key: ReviewSource; name: string; icon: IconName }[] = [
  { key: "BAEMIN", name: "배달의민족", icon: "scooter" },
  { key: "NAVER", name: "네이버", icon: "store" },
  { key: "COUPANG", name: "쿠팡이츠", icon: "truck" },
];
type LoadState = { kind: "idle" } | { kind: "loading" } | { kind: "done"; count: number } | { kind: "failed" };
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** 06-2r 리뷰 불러오기. 배민, 네이버, 쿠팡이츠를 하나씩 불러온다. 안 불러오고 넘어가려 하면 한 번 묻는다 */
export function ReviewImportScreen() {
  const qc = useQueryClient();
  const storeId = account.useValue().storeId;
  const [states, setStates] = useState<Partial<Record<ReviewSource, LoadState>>>({});
  const [asking, setAsking] = useState(false);
  // 이미 불러온 플랫폼은 처음부터 "불러왔어요"로 보인다 (다시 들어와도 같은 리뷰를 또 넣지 않는다)
  const counts = useQuery({ queryKey: ["imported-reviews", storeId], queryFn: () => api.importedReviews(storeId as string), enabled: !!storeId && !USE_MOCK });
  const stateOf = (k: ReviewSource): LoadState => {
    const s = states[k];
    if (s) return s;
    const n = counts.data?.imported[k] ?? 0;
    return n > 0 ? { kind: "done", count: n } : { kind: "idle" };
  };

  const load = async (k: ReviewSource) => {
    setStates((s) => ({ ...s, [k]: { kind: "loading" } }));
    try {
      // 시험용: 크롤링하는 것처럼 3초 기다린 뒤 목업 리뷰를 넣는다
      const [res] = await Promise.all([storeId && !USE_MOCK ? api.importReviews(storeId, k) : Promise.resolve({ imported: 12 }), wait(3000)]);
      setStates((s) => ({ ...s, [k]: { kind: "done", count: res.imported } }));
    } catch {
      setStates((s) => ({ ...s, [k]: { kind: "failed" } }));
    }
  };

  const missing = SOURCES.filter((src) => stateOf(src.key).kind !== "done");
  const anyLoading = SOURCES.some((src) => stateOf(src.key).kind === "loading");
  const proceed = async () => {
    setAsking(false);
    await qc.invalidateQueries({ queryKey: ["home"] });
    go("/start/work-hours");
  };

  return (
    <>
      <SubPage
        progress={{ total: STEPS, done: 4 }}
        onBack={() => back("/start/naver-confirm")}
        footer={
          <PrimaryButton testID="reviews-next" disabled={anyLoading} onPress={() => (missing.length ? setAsking(true) : proceed())}>
            다음
          </PrimaryButton>
        }
      >
        <TitleWithDonna title={"리뷰를\n불러와 주세요"} img="b3-1" sub="답글을 쓰고 단골 손님을 찾을 때 써요" />
        <View testID="review-sources" className="mt-5 overflow-hidden rounded-2xl border border-line bg-surface">
          {SOURCES.map((src, i) => {
            const st = stateOf(src.key);
            return (
              <View key={src.key} className={`min-h-[76px] flex-row items-center gap-3 px-4 py-3 ${i > 0 ? "border-t border-line" : ""}`}>
                <View className={`h-11 w-11 items-center justify-center rounded-xl ${st.kind === "done" ? "bg-done-soft" : "bg-brand-soft"}`}>
                  <Icon name={src.icon} size={24} color={st.kind === "done" ? C.done : C.brand} />
                </View>
                <View className="flex-1">
                  <Text className="text-body font-bold text-ink">{src.name}</Text>
                  <Text className={`text-label ${st.kind === "done" ? "text-done" : st.kind === "failed" ? "text-urgent" : "text-ink-2"}`}>
                    {st.kind === "done" ? `리뷰 ${st.count}개를 불러왔어요` : st.kind === "loading" ? "불러오는 중이에요" : st.kind === "failed" ? "불러오지 못했어요" : "아직 안 불러왔어요"}
                  </Text>
                </View>
                {st.kind === "loading" ? (
                  <ActivityIndicator color={C.brand} />
                ) : st.kind === "done" ? (
                  <View className="h-8 w-8 items-center justify-center rounded-full bg-done-soft">
                    <Icon name="check" size={18} color={C.done} />
                  </View>
                ) : (
                  <Pressable testID={`reviews-load-${src.key}`} accessibilityRole="button" accessibilityLabel={`${src.name} 리뷰 불러오기`} onPress={() => load(src.key)} className="h-10 items-center justify-center rounded-xl border border-brand px-3.5 active:bg-brand-soft">
                    <Text className="text-label font-bold text-brand">{st.kind === "failed" ? "다시" : "불러오기"}</Text>
                  </Pressable>
                )}
              </View>
            );
          })}
        </View>
        <View className="mt-4">
          <Note icon="shield">사장님 계정으로 리뷰만 읽어 와요. 답글은 사장님이 누르기 전엔 올리지 않아요</Note>
        </View>
      </SubPage>
      <Sheet open={asking} onClose={() => setAsking(false)} title="리뷰를 아직 불러오지 않았어요">
        <Text className="text-body text-ink-2">{`${missing.map((m) => m.name).join(", ")} 리뷰 데이터를 불러오지 않았어요.\n리뷰 데이터를 먼저 불러올까요?`}</Text>
        <View className="mt-5 gap-2.5">
          <PrimaryButton testID="reviews-ask-load" onPress={() => setAsking(false)}>
            먼저 불러올게요
          </PrimaryButton>
          <SecondaryButton testID="reviews-ask-skip" onPress={proceed}>
            불러오지 않고 넘어갈게요
          </SecondaryButton>
        </View>
      </Sheet>
    </>
  );
}

/** "1030" → "10:30". 숫자만 남기고 두 자리 뒤에 쌍점을 넣는다 */
function formatTime(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 4);
  return d.length > 2 ? `${d.slice(0, 2)}:${d.slice(2)}` : d;
}
const validTime = (t: string) => /^([01]\d|2[0-3]):[0-5]\d$/.test(t);

/** 시각을 키보드로 적는 칸 (숫자 4개, 예: 1030) */
function TimeField({ label, value, onChange, testID }: { label: string; value: string; onChange: (v: string) => void; testID: string }) {
  const bad = value.length === 5 && !validTime(value);
  return (
    <View className="flex-row items-center gap-3">
      <Text className="w-12 text-body font-medium text-ink">{label}</Text>
      <TextInput
        testID={testID}
        accessibilityLabel={`${label} 시간`}
        value={value}
        onChangeText={(t) => onChange(formatTime(t))}
        keyboardType="number-pad"
        inputMode="numeric"
        maxLength={5}
        placeholder="10:30"
        placeholderTextColor={C["ink-3"]}
        selectTextOnFocus
        className={`h-14 flex-1 rounded-2xl border bg-surface px-4 text-center text-title text-ink ${bad ? "border-urgent" : "border-line"}`}
      />
    </View>
  );
}

const DAYPART_KO: Record<string, string> = { LUNCH: "점심", DINNER: "저녁", NIGHT: "밤" };

/** 06-2w 출근·퇴근 시간. 처음에는 여는 시간·닫는 시간으로 채워 두고 사장님이 키보드로 고친다.
 *  알림 시각은 여기서 도나가 정한다 (출근 후, 브레이크, 퇴근 전). 알림이 바쁜 장사 시간에 걸리면 막지 않고 사장님께 묻는다. */
export function WorkHoursScreen() {
  const qc = useQueryClient();
  const { data, error, refetch } = useHome();
  const [start, setStart] = useState<string | null>(null);
  const [end, setEnd] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // 바쁜 시간에 걸리는 알림: 사장님께 이때 받아도 되는지 묻는다
  const [clash, setClash] = useState<string[] | null>(null);

  if (!data) {
    const problem = startProblem(error, () => refetch(), () => back("/start/reviews"));
    if (problem) return problem;
    return (
      <SubPage progress={{ total: STEPS, done: 5 }}>
        <Bone className="h-60 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const st = start ?? s.work_hours?.start ?? s.open_time;
  const en = end ?? s.work_hours?.end ?? s.close_time;
  const lines = weekLines(weekStateOf(s));
  const work = { start: st, end: en };
  const sug = validTime(st) && validTime(en) ? suggestSlots({ ...s, work_hours: work }) : null;

  const save = async (allowBusy: boolean) => {
    if (!validTime(st) || !validTime(en)) {
      setErr("시간을 10:30 처럼 적어 주세요");
      return;
    }
    if (toMin(st) >= toMin(en)) {
      setErr("퇴근 시간이 출근 시간보다 늦어야 해요");
      return;
    }
    if (!sug) return;
    // 알림이 바쁜 장사 시간에 걸리는지 먼저 본다. 걸리면 사장님께 묻는다
    if (!allowBusy) {
      const hits: string[] = [];
      for (const k of ["OPENING", "AFTERNOON", "CLOSING"] as const) {
        for (const d of s.busy_dayparts) {
          const r = s.dayparts[d];
          if (r.start <= sug[k].time && sug[k].time < r.end) hits.push(`${sug[k].label} ${sug[k].time} (${DAYPART_KO[d] ?? d} 손님이 많은 ${r.start}~${r.end})`);
        }
      }
      if (hits.length) {
        setClash(hits);
        return;
      }
    }
    setSaving(true);
    setErr(null);
    try {
      await api.updateSettings({ work_hours: work, slots: { OPENING: sug.OPENING.time, AFTERNOON: sug.AFTERNOON.time, CLOSING: sug.CLOSING.time }, allow_busy_slots: allowBusy });
      await qc.invalidateQueries({ queryKey: ["home"] });
      setClash(null);
      go("/start/notify-on");
    } catch (e) {
      if (e instanceof ApiFailure && e.code === "SLOT_IN_BUSY_DAYPART") setClash([e.message]);
      else setErr(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <SubPage
        progress={{ total: STEPS, done: 5 }}
        onBack={() => back("/start/reviews")}
        footer={
          <PrimaryButton testID="work-hours-next" disabled={saving} onPress={() => save(false)}>
            {saving ? "저장하는 중" : "다음"}
          </PrimaryButton>
        }
      >
        <TitleWithDonna title={"출근하고 퇴근하는\n시간을 적어 주세요"} img="b3-1" sub="이 시간에 맞춰 할 일을 알려 드려요" />
        <View className="mt-5 gap-3">
          <TimeField testID="work-start" label="출근" value={st} onChange={setStart} />
          <TimeField testID="work-end" label="퇴근" value={en} onChange={setEnd} />
        </View>
        <Text className="mt-2 text-small text-ink-3">가게 여는 시간, 닫는 시간으로 먼저 채워 뒀어요. 숫자 4개로 적어요 (예: 1030)</Text>

        <View className="mt-5 gap-1 rounded-2xl bg-brand-soft px-4 py-3.5">
          <Text className="text-label font-bold text-ink">우리 가게 장사 시간</Text>
          {lines.map((l) => (
            <Text key={l} className="text-label text-ink-2">
              {l}
            </Text>
          ))}
        </View>
        {err ? (
          <Text accessibilityRole="alert" className="mt-3 text-label text-urgent">
            {err}
          </Text>
        ) : null}
      </SubPage>
      <Sheet open={clash !== null} onClose={() => setClash(null)} title={"손님이 많은 시간에\n알림이 가요"}>
        <Text className="text-body text-ink-2">이 시간에 알림을 받아도 괜찮을까요?</Text>
        <View className="mt-3 gap-1.5 rounded-xl bg-paper px-3.5 py-3">
          {(clash ?? []).map((c) => (
            <Text key={c} className="text-label text-ink">
              {c}
            </Text>
          ))}
        </View>
        <Text className="mt-2 text-small text-ink-3">바쁜 시간은 설정 › 바쁜 장사 시간에서 바꿀 수 있어요</Text>
        <View className="mt-5 gap-2.5">
          <PrimaryButton testID="work-hours-busy-ok" disabled={saving} onPress={() => save(true)}>
            {saving ? "저장하는 중" : "괜찮아요, 이때 받을게요"}
          </PrimaryButton>
          <SecondaryButton testID="work-hours-busy-change" onPress={() => setClash(null)}>
            출근·퇴근 시간 다시 적을게요
          </SecondaryButton>
        </View>
      </Sheet>
    </>
  );
}

/** 알림 추가 시트에서 처음 보여 줄 시각: 점심 알림과 마감 알림 사이 30분 단위 */
export function extraSuggestion(slots: Record<"OPENING" | "AFTERNOON" | "CLOSING", string>): string {
  const mid = Math.floor((toMin(slots.AFTERNOON) + toMin(slots.CLOSING)) / 2 / 30) * 30;
  return fromMin(mid);
}
