// 설정 (Figma 06-19 모아 보기, 06-19h 장사 시간, 06-19b 알림 받는 시간, 06-20 바쁜 장사 시간, 06-58 네이버 플레이스).
import { useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Pressable, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon, type IconName } from "@/components/icons/Icon";
import { closingNotes, saveWeek, TitleWithDonna, WeeklyEditor, weekStateOf, type WeekState } from "@/components/start/HoursEditor";
import { errorText, NAVER_PLACE_KEY, param, storeName } from "@/components/start/flow";
import { rescheduleIfAllowed } from "@/components/start/notify";
import { SlotChoiceList } from "@/components/start/StartScreens";
import { back, go } from "@/components/ui/nav";
import { Bone, DonnaImage, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Sheet } from "@/components/ui/Sheet";
import { FailNote, ListRow, Note, SubPage, Toggle } from "@/components/ui/sub";
import { ApiFailure, api } from "@/lib/api";
import { hoursLabel, slotChoices, slotInfo, slotLabel } from "@/lib/hours";
import { flashToast, prefs } from "@/lib/localStore";
import { useHome } from "@/lib/useHome";
import { STORE_ADDRESS } from "@/mocks/extras";
import tokens from "@/theme/tokens.json";
import type { Daypart, Slot } from "@/types/contract";


/** 개발 화면 링크를 보일지. 사장님이 쓰는 배포 빌드에서는 숨긴다. */
const SHOW_DEV = __DEV__ || process.env.EXPO_PUBLIC_SHOW_DEV === "true";
const C = tokens.colors;
const DP: { key: Daypart; label: string; icon: IconName }[] = [
  { key: "LUNCH", label: "점심", icon: "sun" },
  { key: "DINNER", label: "저녁", icon: "sunset" },
  { key: "NIGHT", label: "밤", icon: "moon" },
];
const SLOT_ICON: Record<Slot, IconName> = { OPENING: "sunrise", AFTERNOON: "sun", CLOSING: "moon" };
const SLOTS: Slot[] = ["OPENING", "AFTERNOON", "CLOSING"];

/** 06-19 설정 모아 보기 */
export function SettingsScreen() {
  const { data, prefs: p } = useHome();
  const head = (
    <Text className="pt-2 text-display text-ink" accessibilityRole="header">
      설정
    </Text>
  );
  if (!data) {
    return (
      <>
        {head}
        <Bone className="mt-6 h-48 w-full rounded-2xl" />
      </>
    );
  }
  const s = data.settings.settings;
  const busy = DP.filter((d) => s.busy_dayparts.includes(d.key)).map((d) => d.label);
  const right = (t: string, cls = "text-ink-2") => <Text className={`text-label ${cls}`}>{t}</Text>;
  return (
    <>
      {head}
      <View className="mt-4">
        <ListRow icon="store" title={storeName(s.name)} sub={STORE_ADDRESS[s.store_id]} />
        <ListRow testID="settings-hours" icon="clock" title="장사 시간" right={right(hoursLabel(s))} href="/settings/hours" />
        <ListRow testID="settings-notify" icon="bell" title="알림 받는 시간" right={right("하루 3번")} href="/settings/notify-time" />
        <ListRow testID="settings-busy" icon="clock" title="바쁜 장사 시간" right={right(busy.join(", ") || "없음")} href="/settings/busy" />
        <ListRow
          testID="settings-naver"
          icon="link"
          title="네이버 플레이스"
          right={right(p.naverConnected ? "연결됨" : "연결 안 됨", p.naverConnected ? "font-bold text-done" : "text-ink-2")}
          href={p.naverConnected ? "/settings/naver" : "/naver/connect"}
        />
        <ListRow testID="settings-store-again" icon="store" title="우리 가게 다시 찾기" href="/start/store?again=1" />
      </View>
      <View className="flex-1" />
      {/* 검토용 개발 화면 (가상 시각, 실패, 인터넷 끊김). 개발 빌드에서만 보인다. 배포 빌드에서 보려면 EXPO_PUBLIC_SHOW_DEV=true */}
      {SHOW_DEV ? (
        <Pressable testID="settings-dev" accessibilityRole="link" onPress={() => go("/dev")} className="mt-10 self-center px-4 py-2">
          <Text className="text-small text-ink-3">개발 화면</Text>
        </Pressable>
      ) : null}
    </>
  );
}

/** 06-19h 장사 시간 (요일별). ?naver=1 이면 들어오자마자 네이버에서 다시 불러온다(06-58 "장사 시간, 메뉴 다시 불러오기"). */
export function SettingsHoursScreen() {
  const qc = useQueryClient();
  const { data } = useHome();
  const reloadNow = param(useLocalSearchParams<{ naver?: string }>().naver) === "1";
  const [edit, setEdit] = useState<WeekState | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<{ title: string; sub: string } | null>(null);
  const started = useRef(false);

  const reload = async () => {
    if (!prefs.read().naverConnected) {
      go("/naver/connect");
      return;
    }
    setLoading(true);
    setErr(null);
    try {
      const { place } = await qc.fetchQuery({ queryKey: NAVER_PLACE_KEY, queryFn: api.naverPlace, staleTime: 0 });
      setEdit({ weekly: place.weekly_hours, brk: place.break_time });
      flashToast("네이버에서 불러왔어요", "저장하기를 누르면 바뀌어요");
    } catch {
      setErr({ title: "불러오지 못했어요", sub: "인터넷이 끊겼어요.\n다시 눌러 주세요" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!reloadNow || started.current) return;
    started.current = true;
    reload();
  });

  if (!data) {
    return (
      <SubPage title="장사 시간" onBack={() => back("/settings")}>
        <Bone className="h-80 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const week = edit ?? weekStateOf(s);

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      // 사장님이 06-20에서 고른 바쁜 시간대는 그대로 둔다.
      const res = await saveWeek(week, { keepBusy: s.busy_dayparts });
      await qc.invalidateQueries({ queryKey: ["home"] });
      if (!prefs.read().notifyOff) rescheduleIfAllowed(res.settings.slots);
      flashToast("저장했어요", "알림 시간도 장사 시간에 맞췄어요");
      back("/settings");
    } catch (e) {
      setErr({ title: "저장하지 못했어요", sub: errorText(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <SubPage
      onBack={() => back("/settings")}
      footer={
        <>
          <PrimaryButton onPress={save} disabled={saving || loading}>
            {saving ? "저장하는 중" : "저장하기"}
          </PrimaryButton>
          <SecondaryButton testID="settings-hours-naver" outline onPress={reload} disabled={loading || saving}>
            {loading ? "불러오는 중" : "네이버에서 다시 불러오기"}
          </SecondaryButton>
        </>
      }
    >
      <TitleWithDonna title="장사 시간" sub="고치면 알림 시간도 같이 맞춰 드려요" />
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
      {err ? <FailNote title={err.title} sub={err.sub} /> : null}
    </SubPage>
  );
}

/** PATCH 오류 메시지에서 어느 알림 시각 때문인지 찾는다. 예: "AFTERNOON 알림 시각 12:00 이 ..." */
function slotOfError(message: string): Slot | null {
  return SLOTS.find((sl) => message.startsWith(sl)) ?? null;
}

/** 06-19b 알림 받는 시간. 줄을 누르면 06-3t와 같은 시트에서 고르고, 저장하기로 한 번에 보낸다. */
export function NotifyTimeSettingsScreen() {
  const qc = useQueryClient();
  const { data } = useHome();
  const [edit, setEdit] = useState<Partial<Record<Slot, string>>>({});
  const [err, setErr] = useState<{ slot: Slot | null; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [sheetFor, setSheetFor] = useState<Slot | null>(null);
  const [picked, setPicked] = useState(0);
  if (!data) {
    return (
      <SubPage title="알림 받는 시간" onBack={() => back("/settings")}>
        <Bone className="h-60 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const slots = { ...s.slots, ...edit };
  const info = slotInfo({ ...s, slots });
  // 추천 시각 3개 + 지금 고른 시각(추천에 없으면)
  const choicesOf = (slot: Slot) => {
    const base = slotChoices(s, slot);
    return base.some((c) => c.time === slots[slot]) ? base : [...base, { time: slots[slot], recommended: false }];
  };
  const choices = sheetFor ? choicesOf(sheetFor) : [];

  const open = (slot: Slot) => {
    const i = choicesOf(slot).findIndex((c) => c.time === slots[slot]);
    setPicked(i < 0 ? 0 : i);
    setSheetFor(slot);
  };
  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      await api.updateSettings({ slots });
      await qc.invalidateQueries({ queryKey: ["home"] });
      if (!prefs.read().notifyOff) rescheduleIfAllowed(slots);
      flashToast("저장했어요", "고른 시간에만 알려 드려요");
      back("/settings");
    } catch (e) {
      const f = e instanceof ApiFailure ? e : null;
      setErr({ slot: f ? slotOfError(f.message) : null, text: errorText(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <SubPage
        title="알림 받는 시간"
        onBack={() => back("/settings")}
        footer={
          <PrimaryButton onPress={save} disabled={saving}>
            {saving ? "저장하는 중" : "저장하기"}
          </PrimaryButton>
        }
      >
        <View className="flex-row items-center gap-2">
          <Text className="flex-1 text-body text-ink-2">바쁜 장사 시간엔 조용히 기다릴게요</Text>
          <DonnaImage img="b1-1" size={72} />
        </View>
        <View className="mt-4 gap-3">
          {SLOTS.map((slot) => (
            <View key={slot}>
              <Pressable
                testID={`settings-slot-${slot}`}
                accessibilityRole="button"
                accessibilityLabel={`${info[slot].label} ${slots[slot]}, 눌러서 바꾸기`}
                onPress={() => open(slot)}
                className={`min-h-16 flex-row items-center gap-3 rounded-2xl border-2 bg-surface px-4 py-2 active:bg-brand-soft ${err?.slot === slot ? "border-urgent" : "border-brand"}`}
              >
                <Icon name={SLOT_ICON[slot]} size={26} color={C["ink-2"]} />
                <Text className="flex-1 text-body text-ink">{info[slot].label}</Text>
                <Text className="text-title text-ink">{slots[slot]}</Text>
                <View className="h-7 w-7 items-center justify-center rounded-full bg-brand">
                  <Icon name="check" size={18} color={C["brand-ink"]} />
                </View>
              </Pressable>
              {err?.slot === slot ? (
                <Text accessibilityRole="alert" className="mt-1.5 px-1 text-label text-urgent">
                  {err.text}
                </Text>
              ) : null}
            </View>
          ))}
        </View>
        {closingNotes({ ...s, slots }).length > 0 ? (
          <View className="mt-4 gap-2">
            {closingNotes({ ...s, slots }).map((n) => (
              <Note key={n} icon="clock">
                {n}
              </Note>
            ))}
          </View>
        ) : null}
        {err && !err.slot ? (
          <Text accessibilityRole="alert" className="mt-3 text-label text-urgent">
            {err.text}
          </Text>
        ) : null}
      </SubPage>
      <Sheet open={sheetFor !== null} onClose={() => setSheetFor(null)} title={sheetFor ? `${info[sheetFor].label} 알림,\n언제 받을까요?` : ""}>
        <SlotChoiceList choices={choices} picked={picked} onPick={setPicked} />
        <View className="mt-5">
          <PrimaryButton
            testID="slot-sheet-apply"
            onPress={() => {
              if (sheetFor && choices[picked]) {
                setEdit({ ...edit, [sheetFor]: choices[picked].time });
                if (err?.slot === sheetFor) setErr(null);
              }
              setSheetFor(null);
            }}
          >
            이때 받을게요
          </PrimaryButton>
        </View>
      </Sheet>
    </>
  );
}

/** 06-20 바쁜 장사 시간 */
export function BusySettingsScreen() {
  const qc = useQueryClient();
  const { data } = useHome();
  const [busy, setBusy] = useState<Daypart[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // 바쁜 시간에 알림 시각이 걸리면 여기서는 고칠 수 없으니 알림 받는 시간으로 보내 준다.
  const [slotClash, setSlotClash] = useState(false);
  const [saving, setSaving] = useState(false);
  if (!data) {
    return (
      <SubPage onBack={() => back("/settings")}>
        <Bone className="h-60 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const value = busy ?? s.busy_dayparts;

  const save = async () => {
    setErr(null);
    setSlotClash(false);
    setSaving(true);
    try {
      await api.updateSettings({ busy_dayparts: value });
      await qc.invalidateQueries({ queryKey: ["home"] });
      flashToast("저장했어요", "켜 둔 시간에는 알림을 보내지 않아요");
      back("/settings");
    } catch (e) {
      const f = e instanceof ApiFailure ? e : null;
      const slot = f ? slotOfError(f.message) : null;
      if (f?.code === "SLOT_IN_BUSY_DAYPART" && slot) {
        setSlotClash(true);
        setErr(`${slotLabel(s, slot)} 알림(${s.slots[slot]})이 이 시간에 있어요.\n알림 받는 시간을 먼저 바꿔 주세요.`);
      } else setErr(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <SubPage
      onBack={() => back("/settings")}
      footer={
        <PrimaryButton onPress={save} disabled={saving}>
          {saving ? "저장하는 중" : "저장하기"}
        </PrimaryButton>
      }
    >
      <TitleWithDonna title={"바쁜 시간엔\n조용히 할게요"} img="b1-0" sub="켜 둔 시간에는 알림을 보내지 않아요" />
      <View className="mt-4">
        {DP.map((d) => (
          <View key={d.key} className="min-h-16 flex-row items-center gap-3 border-b border-line py-2">
            <Icon name={d.icon} size={26} color={C["ink-2"]} />
            <View className="flex-1">
              <Text className="text-body text-ink">{d.label}</Text>
              <Text className="text-small text-ink-2">
                {s.dayparts[d.key].start} ~ {s.dayparts[d.key].end}
              </Text>
            </View>
            <Toggle
              testID={`busy-${d.key}`}
              label={`${d.label} 바쁜 시간`}
              checked={value.includes(d.key)}
              onChange={(on) => setBusy(on ? [...value, d.key] : value.filter((x) => x !== d.key))}
            />
          </View>
        ))}
      </View>
      {err ? (
        <Text accessibilityRole="alert" className="mt-3 text-label text-urgent">
          {err}
        </Text>
      ) : null}
      {slotClash ? (
        <View className="mt-2">
          <SecondaryButton testID="busy-to-notify" outline href="/settings/notify-time">
            알림 받는 시간 바꾸기
          </SecondaryButton>
        </View>
      ) : null}
    </SubPage>
  );
}

/** 06-58 네이버 플레이스 */
export function NaverSettingsScreen() {
  const { data, prefs: p } = useHome();
  const name = data ? storeName(data.settings.settings.name) : "";
  return (
    <SubPage
      title="네이버 플레이스"
      onBack={() => back("/settings")}
      footer={
        <SecondaryButton
          testID="naver-disconnect"
          outline
          onPress={() => {
            prefs.write({ naverConnected: false, naverAuto: false });
            flashToast("연결을 끊었어요", "메뉴 순서는 직접 바꿔 주세요");
            back("/settings");
          }}
        >
          연결 끊기
        </SecondaryButton>
      }
    >
      <View className="min-h-16 flex-row items-center gap-3 border-b border-line py-3">
        <Icon name="store" size={26} color={C["ink-2"]} />
        <View className="flex-1">
          <Text className="text-body text-ink">{name}</Text>
          <Text className={`text-label ${p.naverConnected ? "font-bold text-done" : "text-ink-2"}`}>{p.naverConnected ? "연결됨" : "연결 안 됨"}</Text>
        </View>
      </View>
      <View className="border-b border-line py-3">
        <View className="min-h-10 flex-row items-center gap-3">
          <Text className="flex-1 text-body text-ink">메뉴 순서 알아서 바꾸기</Text>
          <Toggle testID="naver-auto" label="메뉴 순서 알아서 바꾸기" checked={p.naverAuto} onChange={(v) => prefs.write({ naverAuto: v })} />
        </View>
        <Text className="text-small text-ink-2">켜 두면 바꾼 뒤에 알려 드려요</Text>
      </View>
      <ListRow testID="naver-reload" icon="refresh" title="장사 시간, 메뉴 다시 불러오기" href="/settings/hours?naver=1" />
    </SubPage>
  );
}
