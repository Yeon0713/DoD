// 처음 쓰는 날 (Figma 06-1 소개, 06-2 가게 찾기, 06-2b 못 찾았을 때, 06-2n 네이버 연결, 06-2c 불러왔어요, 06-2e 장사 시간 고치기,
// 06-2i 직접 적기, 06-3 알림 시간, 06-3t 알림 시간 바꾸기, 06-3e 저녁 장사 예시, 06-3b 알림 켜기).
// 06: 장사 모양 고르기(05-2h)를 없애고, 네이버 플레이스에서 요일별 장사 시간, 메뉴, 사진을 불러와 사장님은 고치기만 한다.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { useRef, useState, type ComponentRef } from "react";
import { Image, Pressable, TextInput, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { SafeAreaView } from "react-native-safe-area-context";
import { Icon, type IconName } from "@/components/icons/Icon";
import { DONNA_IMG } from "@/components/ui/donna";
import { back, go } from "@/components/ui/nav";
import { Bone, DonnaImage, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Sheet } from "@/components/ui/Sheet";
import { FailNote, Note, SubPage } from "@/components/ui/sub";
import { connectNaver } from "@/lib/actions";
import { api } from "@/lib/api";
import { hoursLabel, PATTERNS, patternOf, slotChoices, slotInfo } from "@/lib/hours";
import { flashToast, prefs } from "@/lib/localStore";
import { useHome } from "@/lib/useHome";
import { STORE_ADDRESS } from "@/mocks/extras";
import tokens from "@/theme/tokens.json";
import type { Slot } from "@/types/contract";
import { closingNotes, saveWeek, TitleWithDonna, weekLines, WeeklyEditor, weekStateOf, type WeekState } from "./HoursEditor";
import { errorText, goHome, NAVER_PLACE_KEY, param, PLATFORM_ORDER, PLATFORM_SHORT, STEPS, storeName } from "./flow";
import { turnOnNotifications } from "./notify";

const C = tokens.colors;
const SLOT_ICON: Record<Slot, IconName> = { OPENING: "sunrise", AFTERNOON: "sun", CLOSING: "moon" };

/** 06-1 왜 도나인가 */
export function IntroScreen() {
  const reasons: { icon: IconName; text: string }[] = [
    { icon: "message", text: "배달앱 리뷰에 답글을 써 둬요" },
    { icon: "calendar", text: "축제, 경기, 날씨를 미리 알려요" },
    { icon: "trendUp", text: "다시 온 손님 수까지 알려요" },
  ];
  return (
    <SafeAreaView edges={["top", "bottom"]} style={{ flex: 1, backgroundColor: C.paper }}>
      <View className="flex-1 px-6 pb-5 pt-16">
        <View className="items-center">
          <DonnaImage img="b4-0" size={220} />
          <Text className="mt-2 text-center text-display text-ink" accessibilityRole="header">
            {"손님이 다시 오게,\n도나가 먼저 챙겨요"}
          </Text>
          <Text className="mt-2 text-center text-body text-ink-2">사장님은 보고 누르기만 하세요</Text>
        </View>
        <View className="flex-1" />
        <View className="mb-6">
          {reasons.map((r) => (
            <View key={r.text} className="h-12 flex-row items-center gap-3">
              <Icon name={r.icon} size={28} color={C.brand} />
              <Text className="text-body font-medium text-ink">{r.text}</Text>
            </View>
          ))}
        </View>
        <PrimaryButton href="/start/store">시작하기</PrimaryButton>
      </View>
    </SafeAreaView>
  );
}

/** 06-2 우리 가게 찾기, 06-2b 못 찾았을 때. 설정 "우리 가게 다시 찾기"(?again=1)에서도 쓴다. */
export function StoreSearchScreen() {
  const params = useLocalSearchParams<{ again?: string; q?: string }>();
  const again = param(params.again) === "1";
  const { data } = useHome();
  // 검토용 ?q=가게이름 (06-2b 못 찾았을 때)
  const [query, setQuery] = useState<string | null>(param(params.q));
  const input = useRef<ComponentRef<typeof TextInput>>(null);

  if (!data) {
    return (
      <SubPage progress={again ? undefined : { total: STEPS, done: 1 }}>
        <Bone className="h-16 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const name = storeName(s.name);
  const q = query ?? name;
  // 쓰는 대로 바로 찾는다. 다 쓰고 나서 버튼을 눌러야만 바뀌면, 바뀌기 전 결과의 "우리 가게 맞아요"를 누를 수 있다.
  const searched = q.trim();
  const norm = (x: string) => x.replace(/\s/g, "");
  const found = searched.length >= 2 && (norm(name).includes(norm(searched)) || norm(searched).includes(norm(name)));
  const platforms = PLATFORM_ORDER.filter((p) => data.reviews.reviews.some((r) => r.platform === p));

  return (
    <SubPage
      progress={again ? undefined : { total: STEPS, done: 1 }}
      onBack={() => back(again ? "/settings" : "/start")}
      footer={
        found ? (
          <PrimaryButton onPress={() => (again ? back("/settings") : go("/start/naver"))}>우리 가게 맞아요</PrimaryButton>
        ) : (
          <PrimaryButton
            onPress={() => {
              setQuery("");
              input.current?.focus();
            }}
          >
            다시 찾기
          </PrimaryButton>
        )
      }
    >
      <TitleWithDonna title={"우리 가게를\n찾아 주세요"} img="b3-1" />
      <View className="mt-4 h-[60px] flex-row items-center gap-2.5 rounded-button border border-ink-3 bg-surface px-4">
        <Icon name="search" size={24} color={C["ink-2"]} />
        <TextInput
          ref={input}
          testID="store-search"
          accessibilityLabel="가게 이름"
          value={q}
          onChangeText={setQuery}
          returnKeyType="search"
          onSubmitEditing={() => input.current?.blur()}
          className="flex-1 text-body text-ink"
          placeholderTextColor={C["ink-3"]}
        />
      </View>

      {found ? (
        <>
          <View className="mt-4 flex-row items-center gap-3 rounded-2xl border-2 border-brand bg-brand-soft p-4" accessibilityLabel="찾은 가게, 골라 둠">
            <Icon name="store" size={32} color={C.brand} />
            <View className="flex-1">
              <Text className="text-body font-bold text-ink">{name}</Text>
              <Text className="text-label text-ink-2">{STORE_ADDRESS[s.store_id] ?? ""}</Text>
            </View>
            <View className="h-7 w-7 items-center justify-center rounded-full bg-brand">
              <Icon name="check" size={18} color={C["brand-ink"]} />
            </View>
          </View>
          <View className="mt-4 flex-row items-start gap-3">
            <Icon name="messages" size={28} color={C.brand} />
            <Text className="flex-1 text-body font-medium text-ink">
              {`${platforms.map((p) => PLATFORM_SHORT[p]).join(", ")}\n리뷰 ${data.reviews.reviews.length}개를 함께 찾았어요`}
            </Text>
          </View>
        </>
      ) : (
        <View className="mt-10 items-center" accessibilityRole="summary">
          <Image source={DONNA_IMG.question} style={{ width: 100, height: 147 }} resizeMode="contain" />
          <Text className="mt-3 text-title text-ink">가게를 못 찾았어요</Text>
          <Text className="mt-1 text-center text-body text-ink-2">{`가게 이름을 짧게 써 보세요\n예: ${name.split(" ")[0]}`}</Text>
        </View>
      )}
    </SubPage>
  );
}

/** 06-2n 네이버 플레이스 연결 (불러오기) */
export function NaverStartScreen() {
  const qc = useQueryClient();
  const [state, setState] = useState<"idle" | "connecting" | "failed">("idle");
  const items: { icon: IconName; text: string }[] = [
    { icon: "clock", text: "요일별 장사 시간" },
    { icon: "image", text: "메뉴와 메뉴 사진" },
    { icon: "messages", text: "리뷰 수와 별점" },
  ];
  const connect = async () => {
    setState("connecting");
    try {
      await connectNaver();
      await qc.fetchQuery({ queryKey: NAVER_PLACE_KEY, queryFn: api.naverPlace, staleTime: 0 });
      prefs.write({ naverConnected: true });
      setState("idle");
      go("/start/naver-confirm");
    } catch {
      setState("failed");
    }
  };
  return (
    <SubPage
      progress={{ total: STEPS, done: 2 }}
      onBack={() => back("/start/store")}
      footer={
        <>
          <PrimaryButton testID="start-naver-connect" onPress={connect} disabled={state === "connecting"}>
            {state === "connecting" ? "연결하는 중" : state === "failed" ? "다시 연결하기" : "네이버로 연결하기"}
          </PrimaryButton>
          <SecondaryButton testID="start-manual" onPress={() => go("/start/hours")} disabled={state === "connecting"}>
            직접 적을게요
          </SecondaryButton>
        </>
      }
    >
      <TitleWithDonna title={"네이버 플레이스를\n연결해 주세요"} sub="장사 시간, 메뉴, 사진을 불러올게요" />
      <View className="mt-5 gap-1">
        {items.map((it) => (
          <View key={it.text} className="h-11 flex-row items-center gap-3">
            <Icon name={it.icon} size={24} color={C.brand} />
            <Text className="text-body text-ink">{it.text}</Text>
          </View>
        ))}
      </View>
      <View className="mt-3">
        <Note icon="shield">사장님이 누르기 전엔 아무것도 바꾸지 않아요</Note>
      </View>
      {state === "failed" ? (
        <Text accessibilityRole="alert" className="mt-4 text-label text-urgent">
          연결하지 못했어요. 인터넷을 확인하고 다시 눌러 주세요.
        </Text>
      ) : null}
    </SubPage>
  );
}

/** 06-2c 불러온 것 한 칸 */
function ImportedCard({ icon, title, onEdit, editId, children }: { icon: IconName; title: string; onEdit?: () => void; editId?: string; children: React.ReactNode }) {
  return (
    <View className="gap-1 rounded-2xl border border-line bg-surface px-[18px] py-3.5">
      <View className="flex-row items-center gap-3">
        <Icon name={icon} size={26} color={C["ink-2"]} />
        <Text className="flex-1 text-body font-bold text-ink">{title}</Text>
        {onEdit ? (
          <Pressable testID={editId} accessibilityRole="button" accessibilityLabel={`${title} 고치기`} hitSlop={10} onPress={onEdit}>
            <Text className="text-label font-bold text-brand underline">고치기</Text>
          </Pressable>
        ) : null}
      </View>
      <View className="pl-[38px]">{children}</View>
    </View>
  );
}

/** 06-2c 네이버에서 불러왔어요 + 06-2e 장사 시간 고치기 (아래 시트) */
export function ImportedScreen() {
  const qc = useQueryClient();
  const { data } = useHome();
  const placeQ = useQuery({ queryKey: NAVER_PLACE_KEY, queryFn: api.naverPlace, staleTime: Infinity });
  const [edit, setEdit] = useState<WeekState | null>(null);
  const [sheet, setSheet] = useState<WeekState | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const place = placeQ.data?.place;
  if (!place || !data) {
    return (
      <SubPage progress={{ total: STEPS, done: 3 }} onBack={() => back("/start/naver")}>
        {placeQ.isError ? (
          <FailNote title="불러오지 못했어요" sub={"인터넷이 끊겼어요.\n뒤로 가서 다시 연결해 주세요"} />
        ) : (
          <Bone className="h-64 w-full rounded-2xl" />
        )}
      </SubPage>
    );
  }
  const week: WeekState = edit ?? { weekly: place.weekly_hours, brk: place.break_time };
  const platforms = PLATFORM_ORDER.filter((p) => data.reviews.reviews.some((r) => r.platform === p));
  const menuNames = place.menus.map((m) => m.name);
  const menuLine = `${menuNames.slice(0, 3).join(", ")}${menuNames.length > 3 ? ` 외 ${menuNames.length - 3}개` : ""}`;
  // 메뉴와 사진은 네이버 플레이스에서 고친다. 도나는 바꾸지 않는다.
  const naverOnly = () => flashToast("네이버 플레이스에서 고쳐 주세요", "고친 뒤 설정에서 다시 불러오면 돼요");

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      // 고치지 않았으면 네이버가 알려 준 바쁜 시간대를 그대로 쓴다.
      await saveWeek(week, { parts: edit ? undefined : { dayparts: place.dayparts, busy_dayparts: place.busy_dayparts } });
      await qc.invalidateQueries({ queryKey: ["home"] });
      go("/start/notify-time");
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <SubPage
        progress={{ total: STEPS, done: 3 }}
        onBack={() => back("/start/naver")}
        footer={
          <PrimaryButton onPress={save} disabled={saving}>
            {saving ? "저장하는 중" : "이대로 좋아요"}
          </PrimaryButton>
        }
      >
        <TitleWithDonna title={"네이버에서\n불러왔어요"} sub="다르면 눌러서 고쳐 주세요" />
        <View className="mt-5 gap-2.5">
          <ImportedCard icon="clock" title="장사 시간" editId="hours-edit" onEdit={() => setSheet(week)}>
            {weekLines(week).map((l) => (
              <Text key={l} className="text-body text-ink-2">
                {l}
              </Text>
            ))}
          </ImportedCard>
          <ImportedCard icon="list" title={`메뉴 ${place.menus.length}개`} editId="menus-edit" onEdit={naverOnly}>
            <Text className="text-body text-ink-2">{menuLine}</Text>
          </ImportedCard>
          <ImportedCard icon="image" title={`메뉴 사진 ${place.photo_count}장`} editId="photos-edit" onEdit={naverOnly}>
            <Text className="text-body text-ink-2">포스터 만들 때 써요</Text>
          </ImportedCard>
          <ImportedCard icon="messages" title={`리뷰 ${place.review_count}개`}>
            <Text className="text-body text-ink-2">{platforms.map((p) => PLATFORM_SHORT[p]).join(", ")}</Text>
          </ImportedCard>
        </View>
        {err ? <FailNote title="저장하지 못했어요" sub={err} /> : null}
      </SubPage>
      <Sheet open={sheet !== null} onClose={() => setSheet(null)} title="장사 시간 고치기">
        {sheet ? <WeeklyEditor value={sheet} onChange={setSheet} /> : null}
        <View className="mt-5">
          <PrimaryButton
            testID="hours-sheet-done"
            onPress={() => {
              if (sheet) setEdit(sheet);
              setSheet(null);
              setErr(null);
            }}
          >
            다 고쳤어요
          </PrimaryButton>
        </View>
      </Sheet>
    </>
  );
}

/** 06-2i 장사 시간 직접 적기 (네이버 연결을 건너뛰었을 때) */
export function ManualHoursScreen() {
  const qc = useQueryClient();
  const { data } = useHome();
  const [edit, setEdit] = useState<WeekState | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!data) {
    return (
      <SubPage progress={{ total: STEPS, done: 3 }} onBack={() => back("/start/naver")}>
        <Bone className="h-80 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const week = edit ?? weekStateOf(data.settings.settings);
  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      await saveWeek(week);
      await qc.invalidateQueries({ queryKey: ["home"] });
      go("/start/notify-time");
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <SubPage
      progress={{ total: STEPS, done: 3 }}
      onBack={() => back("/start/naver")}
      footer={
        <PrimaryButton onPress={save} disabled={saving}>
          {saving ? "저장하는 중" : "이대로 좋아요"}
        </PrimaryButton>
      }
    >
      <TitleWithDonna title={"장사 시간을\n적어 주세요"} sub="요일마다 달라도 괜찮아요" />
      <View className="mt-5">
        <WeeklyEditor
          value={week}
          onChange={(v) => {
            setEdit(v);
            // 고치기 시작하면 앞선 저장 오류는 지운다.
            setErr(null);
          }}
        />
      </View>
      {err ? <FailNote title="저장하지 못했어요" sub={err} /> : null}
    </SubPage>
  );
}

/** 06-3 장사 시간에 맞춰 골랐어요 + 06-3t 알림 시간 바꾸기 (아래 시트). 06-3e는 저녁, 밤 장사일 때의 모양. */
export function NotifyTimeScreen() {
  const qc = useQueryClient();
  const { data } = useHome();
  const [sheetFor, setSheetFor] = useState<Slot | null>(null);
  const [picked, setPicked] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!data) {
    return (
      <SubPage progress={{ total: STEPS, done: 4 }}>
        <Bone className="h-60 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const info = slotInfo(s);
  const pattern = patternOf(s);
  const choices = sheetFor ? slotChoices(s, sheetFor) : [];
  const notes = closingNotes(s);

  const open = (slot: Slot) => {
    const i = slotChoices(s, slot).findIndex((c) => c.time === s.slots[slot]);
    setPicked(i < 0 ? 0 : i);
    setErr(null);
    setSheetFor(slot);
  };
  const apply = async () => {
    if (!sheetFor) return;
    setSaving(true);
    setErr(null);
    try {
      await api.updateSettings({ slots: { ...s.slots, [sheetFor]: choices[picked].time } });
      await qc.invalidateQueries({ queryKey: ["home"] });
      setSheetFor(null);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <SubPage progress={{ total: STEPS, done: 4 }} footer={<PrimaryButton onPress={() => go("/start/notify-on")}>이대로 좋아요</PrimaryButton>}>
        <TitleWithDonna title={"장사 시간에 맞춰\n골랐어요"} sub="누르면 원하는 시간으로 바꿀 수 있어요" />
        {pattern === "EVENING_NIGHT" ? (
          <View className="mt-1 self-start rounded-2xl bg-brand-soft px-3 py-1">
            <Text className="text-label text-ink">{`${PATTERNS.EVENING_NIGHT.label}  ${hoursLabel(s)}`}</Text>
          </View>
        ) : null}
        <View className="mt-5 gap-3">
          {(["OPENING", "AFTERNOON", "CLOSING"] as Slot[]).map((slot) => (
            <Pressable
              key={slot}
              testID={`slot-${slot}`}
              accessibilityRole="button"
              accessibilityLabel={`${info[slot].label} ${info[slot].time}, 눌러서 바꾸기`}
              onPress={() => open(slot)}
              className="min-h-16 flex-row items-center gap-3 rounded-2xl border-2 border-brand bg-surface px-4 py-2 active:bg-brand-soft"
            >
              <Icon name={SLOT_ICON[slot]} size={26} color={C["ink-2"]} />
              <View className="flex-1">
                <Text className="text-body text-ink">{info[slot].label}</Text>
                <Text className="text-small text-ink-2">{info[slot].reason}</Text>
              </View>
              <Text className="text-title text-ink">{info[slot].time}</Text>
              <View className="h-7 w-7 items-center justify-center rounded-full bg-brand">
                <Icon name="check" size={18} color={C["brand-ink"]} />
              </View>
            </Pressable>
          ))}
        </View>
        {notes.length > 0 ? (
          <View className="mt-4 gap-2">
            {notes.map((n) => (
              <Note key={n} icon="clock">
                {n}
              </Note>
            ))}
          </View>
        ) : null}
      </SubPage>
      <Sheet open={sheetFor !== null} onClose={() => setSheetFor(null)} title={sheetFor ? `${info[sheetFor].label} 알림,\n언제 받을까요?` : ""}>
        <SlotChoiceList choices={choices} picked={picked} onPick={setPicked} />
        {err ? (
          <Text accessibilityRole="alert" className="mt-3 text-label text-urgent">
            {err}
          </Text>
        ) : null}
        <View className="mt-5">
          <PrimaryButton testID="slot-sheet-apply" onPress={apply} disabled={saving}>
            {saving ? "바꾸는 중" : "이때 받을게요"}
          </PrimaryButton>
        </View>
      </Sheet>
    </>
  );
}

/** 06-3t, 06-19b 시트 안의 시각 고르기 */
export function SlotChoiceList({ choices, picked, onPick }: { choices: { time: string; recommended: boolean }[]; picked: number; onPick: (i: number) => void }) {
  return (
    <View className="gap-2.5" accessibilityRole="radiogroup" accessibilityLabel="알림 시각">
      {choices.map((c, i) => (
        <Pressable
          key={c.time}
          testID={`slot-choice-${i}`}
          accessibilityRole="radio"
          accessibilityState={{ checked: picked === i }}
          onPress={() => onPick(i)}
          className={`min-h-16 flex-row items-center gap-3 rounded-button border px-4 ${picked === i ? "border-brand bg-brand-soft" : "border-line bg-surface"}`}
        >
          <Text className="flex-1 text-body font-medium text-ink">{c.time}</Text>
          {c.recommended ? <Text className="text-label text-brand">추천</Text> : null}
        </Pressable>
      ))}
    </View>
  );
}

/** 06-3b 알림을 켜 주세요 */
export function NotifyOnScreen() {
  const { data } = useHome();
  const [busy, setBusy] = useState(false);
  const s = data?.settings.settings;
  const time = s?.slots.AFTERNOON ?? "14:00";
  const finish = (notifyOff: boolean) => {
    prefs.write({ onboarded: true, notifyOff, firstDayPending: true });
    goHome();
  };
  const turnOn = async () => {
    setBusy(true);
    const granted = s ? await turnOnNotifications(s.slots) : false;
    setBusy(false);
    finish(!granted);
  };
  return (
    <SubPage
      progress={{ total: STEPS, done: 5 }}
      footer={
        <>
          <PrimaryButton onPress={turnOn} disabled={busy || !s}>
            알림 켜기
          </PrimaryButton>
          <SecondaryButton testID="notify-later" onPress={() => finish(true)}>
            나중에 켤게요
          </SecondaryButton>
        </>
      }
    >
      <TitleWithDonna title={"알림을\n켜 주세요"} sub="하루 3번, 고른 시간에만 알려 드려요" />
      <View className="mt-5 rounded-2xl border border-line bg-surface px-4 py-3.5" accessibilityLabel="알림 예시">
        <View className="flex-row items-center gap-1.5">
          <Icon name="bell" size={18} color={C["ink-2"]} />
          <Text className="flex-1 text-small text-ink-2">도나</Text>
          <Text className="text-small text-ink-2">{time}</Text>
        </View>
        <Text className="mt-1 text-body font-medium text-ink">배달이 늦었다는 리뷰가 왔어요</Text>
        <Text className="text-small text-ink-2">사과 답글을 써 뒀어요</Text>
      </View>
      <Text className="mt-2 text-center text-small text-ink-3">이렇게 알려 드려요</Text>
    </SubPage>
  );
}

