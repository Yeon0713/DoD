// 처음 쓰는 날 (Figma 06-1 소개, 06-2 가게 찾기, 06-2b 못 찾았을 때, 06-2n 네이버 연결, 06-2c 불러왔어요, 06-2e 장사 시간 고치기,
// 06-2i 직접 적기, 06-3 알림 시간, 06-3t 알림 시간 바꾸기, 06-3e 저녁 장사 예시, 06-3b 알림 켜기).
// 06: 장사 모양 고르기(05-2h)를 없애고, 네이버 플레이스에서 요일별 장사 시간, 메뉴, 사진을 불러와 사장님은 고치기만 한다.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Redirect } from "expo-router";
import { useState } from "react";
import { Pressable, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { SafeAreaView } from "react-native-safe-area-context";
import { Icon, type IconName } from "@/components/icons/Icon";
import { back, go } from "@/components/ui/nav";
import { Bone, DonnaImage, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Sheet } from "@/components/ui/Sheet";
import { FailNote, Note, SubPage } from "@/components/ui/sub";
import { api } from "@/lib/api";
import { hoursLabel, PATTERNS, patternOf, slotChoices, slotInfo } from "@/lib/hours";
import { flashToast, prefs } from "@/lib/localStore";
import { openSmartPlace } from "@/lib/smartplace";
import { useHome } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";
import type { Slot } from "@/types/contract";
import { AskLink, NaverButton, startProblem, StoreNotReady } from "./AccountScreens";
import { DemoMenuBar } from "./DemoMenu";
import { closingNotes, saveWeek, TimeStepper, TitleWithDonna, weekLines, WeeklyEditor, weekStateOf, type WeekState } from "./HoursEditor";
import { extraSuggestion } from "./StoreRegister";
import { errorText, enterApp, NAVER_PLACE_KEY, PLATFORM_ORDER, PLATFORM_SHORT, STEPS } from "./flow";
import { turnOnNotifications } from "./notify";

const C = tokens.colors;
const SLOT_ICON: Record<Slot, IconName> = { OPENING: "sunrise", AFTERNOON: "sun", CLOSING: "moon" };

/** 06-1, 08-1 왜 도나인가. 08-1: 시작하기 대신 네이버로 시작하기, 휴대폰 번호로 시작하기, 로그인 */
export function IntroScreen() {
  const reasons: { icon: IconName; text: string }[] = [
    { icon: "message", text: "배달앱 리뷰에 답글을 써 둬요" },
    { icon: "calendar", text: "축제, 경기, 날씨를 미리 알려요" },
    { icon: "trendUp", text: "다시 온 손님 수까지 알려요" },
  ];
  return (
    <SafeAreaView edges={["top", "bottom"]} style={{ flex: 1, backgroundColor: C.paper }}>
      <DemoMenuBar />
      <View className="flex-1 px-6 pb-5 pt-2">
        <View className="items-center">
          <DonnaImage img="b4-0" size={180} />
          <Text className="mt-2 text-center text-display text-ink" accessibilityRole="header">
            {"손님이 다시 오게,\n도나가 먼저 챙겨요"}
          </Text>
          <Text className="mt-2 text-center text-body text-ink-2">사장님은 보고 누르기만 하세요</Text>
        </View>
        <View className="flex-1" />
        <View className="mb-5">
          {reasons.map((r) => (
            <View key={r.text} className="h-12 flex-row items-center gap-3">
              <Icon name={r.icon} size={28} color={C.brand} />
              <Text className="text-body font-medium text-ink">{r.text}</Text>
            </View>
          ))}
        </View>
        <View className="gap-2.5">
          <NaverButton testID="start-naver" onPress={() => go("/start/naver-login")}>
            네이버로 시작하기
          </NaverButton>
          <SecondaryButton testID="start-phone" outline onPress={() => go("/start/phone")}>
            휴대폰 번호로 시작하기
          </SecondaryButton>
          <AskLink ask="이미 쓰고 계세요?" label="로그인" testID="start-login" onPress={() => go("/login")} />
        </View>
      </View>
    </SafeAreaView>
  );
}

/** 06-2n 네이버 플레이스 연결. 따로 묻지 않고 가게 정보 확인(06-2c)으로 바로 보낸다.
 * 네이버 로그인을 하고 가게까지 고른 사장님에게 네이버를 한 번 더 연결하라고 하지 않는다. 예전 주소로 들어와도 같은 곳으로 간다. */
export function NaverStartScreen() {
  return <Redirect href="/start/naver-confirm" />;
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
  const { data, error, refetch } = useHome();
  // 네이버 플레이스에서 메뉴를 고치고 돌아오면 다시 불러온다
  const placeQ = useQuery({ queryKey: NAVER_PLACE_KEY, queryFn: api.naverPlace, staleTime: Infinity, refetchOnWindowFocus: "always" });
  const [edit, setEdit] = useState<WeekState | null>(null);
  const [sheet, setSheet] = useState<WeekState | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const place = placeQ.data?.place;
  if (!data) {
    const problem = startProblem(error, () => refetch(), () => back("/start/naver-store"), place?.name);
    if (problem) return problem;
  }
  if (!place || !data) {
    return (
      <SubPage progress={{ total: STEPS, done: 3 }} onBack={() => back("/start/naver-store")}>
        {placeQ.isError ? (
          <FailNote title="불러오지 못했어요" sub={"인터넷이 끊겼어요.\n뒤로 가서 다시 연결해 주세요"} />
        ) : (
          <Bone className="h-64 w-full rounded-2xl" />
        )}
      </SubPage>
    );
  }
  // 자정을 넘겨 여는 가게는 아직 알림 계획을 만들지 못해서 저장하기 전에 알린다 (저장하면 서버가 받지 않는다)
  if (Object.values(place.weekly_hours).some((d) => d && d.close <= d.open)) {
    return <StoreNotReady name={place.name} onBack={() => back("/start/naver-store")} />;
  }
  const week: WeekState = edit ?? { weekly: place.weekly_hours, brk: place.break_time };
  const platforms = PLATFORM_ORDER.filter((p) => data.reviews.reviews.some((r) => r.platform === p));
  const menuNames = place.menus.map((m) => m.name);
  const menuLine = `${menuNames.slice(0, 3).join(", ")}${menuNames.length > 3 ? ` 외 ${menuNames.length - 3}개` : ""}`;
  // 메뉴와 사진은 네이버 플레이스(스마트플레이스)에서 고친다. 도나는 바꾸지 않는다. 돌아오면 다시 불러온다.
  const naverOnly = () => {
    openSmartPlace();
    flashToast("네이버 플레이스를 열었어요", "고치고 돌아오면 다시 불러올게요");
  };

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      // 고치지 않았으면 네이버가 알려 준 바쁜 시간대를 그대로 쓴다.
      await saveWeek(week, { parts: edit ? undefined : { dayparts: place.dayparts, busy_dayparts: place.busy_dayparts } });
      await qc.invalidateQueries({ queryKey: ["home"] });
      go("/start/reviews");
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
        onBack={() => back("/start/naver-store")}
        footer={
          <PrimaryButton onPress={save} disabled={saving}>
            {saving ? "저장하는 중" : "이대로 좋아요"}
          </PrimaryButton>
        }
      >
        <TitleWithDonna title={"가게 정보를\n확인해 주세요"} sub="다르면 눌러서 고쳐 주세요" />
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
  const { data, error, refetch } = useHome();
  const [edit, setEdit] = useState<WeekState | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!data) {
    const problem = startProblem(error, () => refetch(), () => back("/start/naver-confirm"));
    if (problem) return problem;
    return (
      <SubPage progress={{ total: STEPS, done: 3 }} onBack={() => back("/start/naver-confirm")}>
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
      go("/start/reviews");
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <SubPage
      progress={{ total: STEPS, done: 3 }}
      onBack={() => back("/start/naver-confirm")}
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
  const { data, error, refetch } = useHome();
  const [sheetFor, setSheetFor] = useState<Slot | null>(null);
  const [picked, setPicked] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // 알림 추가: 시트에서 시각을 고른다
  const [adding, setAdding] = useState<string | null>(null);

  if (!data) {
    const problem = startProblem(error, () => refetch(), () => back("/start"));
    if (problem) return problem;
    return (
      <SubPage progress={{ total: STEPS, done: 6 }}>
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
  const extras = s.extra_slots ?? [];
  const work = s.work_hours ?? null;
  const saveExtras = async (next: string[]) => {
    setSaving(true);
    setErr(null);
    try {
      await api.updateSettings({ extra_slots: next });
      await qc.invalidateQueries({ queryKey: ["home"] });
      setAdding(null);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setSaving(false);
    }
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
      <SubPage progress={{ total: STEPS, done: 6 }} footer={<PrimaryButton onPress={() => go("/start/notify-on")}>이대로 좋아요</PrimaryButton>}>
        <TitleWithDonna title={"장사 시간에 맞춰\n골랐어요"} sub="누르면 원하는 시간으로 바꿀 수 있어요" />
        {work ? (
          <Pressable testID="work-hours-change" accessibilityRole="button" onPress={() => back("/start/work-hours")} className="mt-2 flex-row items-center gap-1.5 self-start rounded-full bg-brand-soft px-3 py-1.5 active:opacity-80">
            <Icon name="clock" size={16} color={C.brand} />
            <Text className="text-label text-ink">{`출근 ${work.start} · 퇴근 ${work.end} 기준`}</Text>
            <Text className="text-label font-bold text-brand underline">바꾸기</Text>
          </Pressable>
        ) : null}
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
        {extras.length > 0 ? (
          <View testID="extra-slots" className="mt-3 gap-3">
            {extras.map((t) => (
              <View key={t} className="min-h-16 flex-row items-center gap-3 rounded-2xl border border-line bg-surface px-4 py-2">
                <Icon name="bell" size={24} color={C["ink-2"]} />
                <View className="flex-1">
                  <Text className="text-body text-ink">추가 알림</Text>
                  <Text className="text-small text-ink-2">남은 할 일을 다시 알려 드려요</Text>
                </View>
                <Text className="text-title text-ink">{t}</Text>
                <Pressable accessibilityRole="button" accessibilityLabel={`${t} 알림 빼기`} hitSlop={8} disabled={saving} onPress={() => saveExtras(extras.filter((x) => x !== t))} className="h-9 justify-center rounded-xl border border-line px-3 active:bg-brand-soft">
                  <Text className="text-label text-ink-2">빼기</Text>
                </Pressable>
              </View>
            ))}
          </View>
        ) : null}
        <Pressable
          testID="extra-slot-add"
          accessibilityRole="button"
          onPress={() => {
            setErr(null);
            setAdding(extraSuggestion(s.slots));
          }}
          className="mt-3 h-14 flex-row items-center justify-center gap-2 rounded-2xl border-[1.5px] border-dashed border-ink-3 active:bg-brand-soft"
        >
          <Text className="text-title text-brand">+</Text>
          <Text className="text-body font-medium text-brand">알림 추가하기</Text>
        </Pressable>
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
      <Sheet open={adding !== null} onClose={() => setAdding(null)} title={"언제 더\n알려 드릴까요?"}>
        <Text className="mb-4 text-body text-ink-2">이 시간에 남은 할 일이 있으면 다시 알려 드려요</Text>
        {adding ? <TimeStepper id="extra-slot" label="알림 시간" value={adding} onChange={setAdding} step={10} /> : null}
        {adding && (extras.includes(adding) || Object.values(s.slots).includes(adding)) ? <Text className="mt-3 text-label text-urgent">이미 이 시간에 알림이 있어요</Text> : null}
        {err ? (
          <Text accessibilityRole="alert" className="mt-3 text-label text-urgent">
            {err}
          </Text>
        ) : null}
        <View className="mt-5">
          <PrimaryButton
            testID="extra-slot-apply"
            disabled={saving || !adding || extras.includes(adding) || Object.values(s.slots).includes(adding)}
            onPress={() => adding && saveExtras([...extras, adding])}
          >
            {saving ? "넣는 중" : "이때도 받을게요"}
          </PrimaryButton>
        </View>
      </Sheet>
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
    enterApp();
  };
  const turnOn = async () => {
    setBusy(true);
    const granted = s ? await turnOnNotifications(s.slots, s.extra_slots ?? []) : false;
    setBusy(false);
    finish(!granted);
  };
  return (
    <SubPage
      progress={{ total: STEPS, done: 7 }}
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

