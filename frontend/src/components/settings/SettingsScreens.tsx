"use client";
// 설정 (Figma 04-19 모아 보기, 04-19b 알림 받는 시간, 04-20 바쁜 장사 시간, 04-58 네이버 플레이스).
import Image from "next/image";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Icon, type IconName } from "@/components/icons/Icon";
import { Bone, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { ListRow, SubPage, Toggle } from "@/components/ui/sub";
import { ApiFailure, api } from "@/lib/api";
import { hoursLabel, slotInfo, slotLabel } from "@/lib/hours";
import { flashToast, prefs } from "@/lib/localStore";
import { useHome } from "@/lib/useHome";
import { STORE_ADDRESS } from "@/mocks/extras";
import type { Daypart, Slot } from "@/types/contract";

const DP: { key: Daypart; label: string; icon: IconName }[] = [
  { key: "LUNCH", label: "점심", icon: "sun" },
  { key: "DINNER", label: "저녁", icon: "sunset" },
  { key: "NIGHT", label: "밤", icon: "moon" },
];
const SLOT_ICON: Record<Slot, IconName> = { OPENING: "sunrise", AFTERNOON: "sun", CLOSING: "moon" };

function storeName(name: string) {
  return name.replace(/\s*\(.*\)\s*/g, "").trim();
}

export function SettingsScreen() {
  const { data, prefs: p } = useHome();
  if (!data) {
    return (
      <>
        <h1 className="pt-2 text-display">설정</h1>
        <Bone className="mt-6 h-48 w-full rounded-2xl" />
      </>
    );
  }
  const s = data.settings.settings;
  const busy = DP.filter((d) => s.busy_dayparts.includes(d.key)).map((d) => d.label);
  return (
    <>
      <h1 className="pt-2 text-display">설정</h1>
      <div className="mt-4">
        <ListRow icon="store" title={storeName(s.name)} sub={STORE_ADDRESS[s.store_id]} />
        <ListRow icon="clock" title="장사 시간" right={<span className="text-label text-ink-2">{hoursLabel(s)}</span>} href="/settings/hours" />
        <ListRow icon="bell" title="알림 받는 시간" right={<span className="text-label text-ink-2">하루 3번</span>} href="/settings/notify-time" />
        <ListRow icon="clock" title="바쁜 장사 시간" right={<span className="text-label text-ink-2">{busy.join(", ") || "없음"}</span>} href="/settings/busy" />
        <ListRow
          icon="link"
          title="네이버 플레이스"
          right={<span className={`text-label ${p.naverConnected ? "font-bold text-done" : "text-ink-2"}`}>{p.naverConnected ? "연결됨" : "연결 안 됨"}</span>}
          href={p.naverConnected ? "/settings/naver" : "/naver/connect"}
        />
        <ListRow icon="store" title="우리 가게 다시 찾기" href="/start/store?again=1" />
      </div>
    </>
  );
}

/** PATCH 오류 메시지에서 어느 알림 시각 때문인지 찾는다. 예: "AFTERNOON 알림 시각 12:00 이 ..." */
function slotOfError(message: string): Slot | null {
  return (["OPENING", "AFTERNOON", "CLOSING"] as Slot[]).find((sl) => message.startsWith(sl)) ?? null;
}

function friendly(e: ApiFailure): string {
  if (e.code === "SLOT_IN_BUSY_DAYPART") return "바쁜 장사 시간에 걸려요. 다른 시간을 골라 주세요.";
  if (e.code === "SLOT_OUTSIDE_OPEN_HOURS") return "가게 문을 연 시간 안으로 골라 주세요.";
  if (e.offline) return "인터넷이 끊겨서 저장하지 못했어요.";
  return e.message;
}

export function NotifyTimeSettingsScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data } = useHome();
  const [edit, setEdit] = useState<Partial<Record<Slot, string>>>({});
  const [err, setErr] = useState<{ slot: Slot | null; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  if (!data) return <SubPage title="알림 받는 시간">{null}</SubPage>;
  const slots = { ...data.settings.settings.slots, ...edit };
  const info = slotInfo({ ...data.settings.settings, slots });

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      await api.updateSettings({ slots });
      await qc.invalidateQueries({ queryKey: ["home"] });
      flashToast("저장했어요", "고른 시간에만 알려 드려요");
      router.push("/settings");
    } catch (e) {
      const f = e instanceof ApiFailure ? e : new ApiFailure("UNKNOWN", "잠시 뒤 다시 해 주세요.");
      setErr({ slot: slotOfError(f.message), text: friendly(f) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <SubPage
      title="알림 받는 시간"
      backHref="/settings"
      footer={
        <PrimaryButton onClick={save} disabled={saving}>
          {saving ? "저장하는 중" : "저장하기"}
        </PrimaryButton>
      }
    >
      <p className="text-body text-ink-2">바쁜 장사 시간엔 조용히 기다릴게요</p>
      <ul className="mt-5 flex flex-col gap-3">
        {(["OPENING", "AFTERNOON", "CLOSING"] as Slot[]).map((slot) => (
          <li key={slot}>
            <label className={`flex min-h-16 items-center gap-3 rounded-2xl border-2 bg-surface px-4 py-2 ${err?.slot === slot ? "border-urgent" : "border-brand"}`}>
              <Icon name={SLOT_ICON[slot]} size={26} className="shrink-0 text-ink-2" />
              {/* 긴 이름("점심 장사 끝나고")은 두 줄로 내려 쓰고, 시각 칸은 줄이지 않는다. 한 줄로 두면 시각이 잘린다. */}
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-body leading-snug">{info[slot].label}</span>
                <span className="text-small text-ink-2">{info[slot].reason}</span>
              </span>
              <input
                type="time"
                value={slots[slot]}
                step={600}
                onChange={(e) => setEdit({ ...edit, [slot]: e.target.value })}
                aria-invalid={err?.slot === slot}
                className="w-[152px] shrink-0 rounded-lg bg-brand-soft px-2 py-1 text-body font-bold text-ink tabular-nums"
              />
            </label>
            {err?.slot === slot && (
              <p role="alert" className="mt-1.5 px-1 text-label text-urgent">
                {err.text}
              </p>
            )}
          </li>
        ))}
      </ul>
      {err && !err.slot && (
        <p role="alert" className="mt-3 text-label text-urgent">
          {err.text}
        </p>
      )}
    </SubPage>
  );
}

export function BusySettingsScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data } = useHome();
  const [busy, setBusy] = useState<Daypart[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // 바쁜 시간에 알림 시각이 걸리면 여기서는 고칠 수 없으니 알림 받는 시간으로 보내 준다.
  const [slotClash, setSlotClash] = useState(false);
  const [saving, setSaving] = useState(false);
  if (!data) return <SubPage>{null}</SubPage>;
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
      router.push("/settings");
    } catch (e) {
      const f = e instanceof ApiFailure ? e : null;
      const slot = f ? slotOfError(f.message) : null;
      if (f?.code === "SLOT_IN_BUSY_DAYPART" && slot) {
        setSlotClash(true);
        setErr(`${slotLabel(s, slot)} 알림(${s.slots[slot]})이 이 시간에 있어요.\n알림 받는 시간을 먼저 바꿔 주세요.`);
      } else setErr(f ? friendly(f) : "잠시 뒤 다시 해 주세요.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SubPage
      backHref="/settings"
      footer={
        <PrimaryButton onClick={save} disabled={saving}>
          {saving ? "저장하는 중" : "저장하기"}
        </PrimaryButton>
      }
    >
      <div className="flex items-start justify-between">
        <h1 className="pt-3 text-display">
          바쁜 시간엔
          <br />
          조용히 할게요
        </h1>
        <Image loading="eager" src="/donna/b4-1.png" alt="" width={88} height={88} />
      </div>
      <p className="text-body text-ink-2">켜 둔 시간에는 알림을 보내지 않아요</p>
      <ul className="mt-4">
        {DP.map((d) => (
          <li key={d.key} className="flex min-h-16 items-center gap-3 border-b border-line py-2">
            <Icon name={d.icon} size={26} className="text-ink-2" />
            <span className="flex flex-1 flex-col">
              <span className="text-body">{d.label}</span>
              <span className="text-small text-ink-2">
                {s.dayparts[d.key].start} ~ {s.dayparts[d.key].end}
              </span>
            </span>
            <Toggle
              label={`${d.label} 바쁜 시간`}
              checked={value.includes(d.key)}
              onChange={(on) => setBusy(on ? [...value, d.key] : value.filter((x) => x !== d.key))}
            />
          </li>
        ))}
      </ul>
      {err && (
        <p role="alert" className="pre-line mt-3 text-label text-urgent">
          {err}
        </p>
      )}
      {slotClash && (
        <div className="mt-2">
          <SecondaryButton outline href="/settings/notify-time">
            알림 받는 시간 바꾸기
          </SecondaryButton>
        </div>
      )}
    </SubPage>
  );
}

export function NaverSettingsScreen() {
  const router = useRouter();
  const { data, prefs: p } = useHome();
  const name = data ? storeName(data.settings.settings.name) : "";
  return (
    <SubPage
      title="네이버 플레이스"
      backHref="/settings"
      footer={
        <SecondaryButton
          outline
          onClick={() => {
            prefs.write({ naverConnected: false, naverAuto: false });
            flashToast("연결을 끊었어요", "메뉴 순서는 직접 바꿔 주세요");
            router.push("/settings");
          }}
        >
          연결 끊기
        </SecondaryButton>
      }
    >
      <ListRow
        icon="store"
        title={name}
        right={<span className={`text-label ${p.naverConnected ? "font-bold text-done" : "text-ink-2"}`}>{p.naverConnected ? "연결됨" : "연결 안 됨"}</span>}
      />
      <div className="flex min-h-16 items-center gap-3 border-b border-line py-2">
        <span className="flex flex-1 flex-col">
          <span className="text-body">메뉴 순서 알아서 바꾸기</span>
          <span className="text-small text-ink-2">켜 두면 바꾼 뒤에 알려 드려요</span>
        </span>
        <Toggle label="메뉴 순서 알아서 바꾸기" checked={p.naverAuto} onChange={(v) => prefs.write({ naverAuto: v })} />
      </div>
    </SubPage>
  );
}
