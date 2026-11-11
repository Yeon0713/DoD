"use client";
// 04-24 같은 불만 점검 목록. 근거 리뷰는 같은 화면에서 펼친다 (리뷰 화면을 따로 두지 않는다).
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Icon } from "@/components/icons/Icon";
import { Bone, PrimaryButton } from "@/components/ui/parts";
import { Note, SubPage } from "@/components/ui/sub";
import { markDone } from "@/lib/cardState";
import { COMPLAINT_ICON, COMPLAINT_SHORT, PLATFORM_KO } from "@/lib/labels";
import { flashToast } from "@/lib/localStore";
import { addDays, monthDay } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import { CHECKLIST } from "@/mocks/extras";
import type { ComplaintType } from "@/types/contract";

export function CheckScreen() {
  const planId = decodeURIComponent(useParams<{ planId: string }>().planId ?? "");
  const router = useRouter();
  const { data } = useHome();
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const [open, setOpen] = useState(false);

  if (!data) {
    return (
      <SubPage title="점검">
        <Bone className="h-24 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const p = data.plan.plan_items.find((x) => x.plan_id === planId);
  const target = p?.target_date ?? "";
  const from = addDays(target, -7);
  const recent = data.reviews.reviews.filter(
    (r) => r.label?.complaint_types.length && r.written_at.slice(0, 10) > from && r.written_at.slice(0, 10) <= target,
  );
  const counts = new Map<ComplaintType, number>();
  for (const r of recent) for (const t of r.label!.complaint_types) counts.set(t, (counts.get(t) ?? 0) + 1);
  const type = ([...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "SERVICE") as ComplaintType;
  const same = recent.filter((r) => r.label!.complaint_types.includes(type)).sort((a, b) => a.written_at.localeCompare(b.written_at));
  const group = same[0]?.label?.complaint_groups[0] ?? "SERVICE";
  const by = p?.deadline_at ?? `${addDays(target, 1)}T12:00:00+09:00`;
  const items = CHECKLIST[type];

  const done = () => {
    markDone(`APPROVAL_REQUEST:${planId}`);
    flashToast("점검을 마쳤어요", "일주일 뒤 결과를 알려 드릴게요");
    router.push("/");
  };

  return (
    <SubPage
      title={`${COMPLAINT_SHORT[type]} 점검`}
      footer={
        <>
          <div className="mb-2">
            <Note icon="clock" center>{`${monthDay(by)} 전까지`}</Note>
          </div>
          <PrimaryButton onClick={done}>다 점검했어요</PrimaryButton>
        </>
      }
    >
      <div className="flex items-center gap-3">
        <span className="flex gap-1 text-urgent" aria-hidden>
          {same.map((r) => (
            <Icon key={r.review_id} name={COMPLAINT_ICON[group]} size={26} />
          ))}
        </span>
        <p className="text-body font-medium text-ink">
          {same.length ? `${monthDay(same[0].written_at)}부터 ${Number(same[same.length - 1].written_at.slice(8, 10))}일까지` : ""}
          <br />
          같은 말이 {same.length}번 나왔어요
        </p>
      </div>

      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="mt-3 flex min-h-12 items-center gap-2 border-b border-line text-body text-ink-2"
      >
        <Icon name="message" size={22} />
        <span className="flex-1 text-left">손님 리뷰 {same.length}개 {open ? "접기" : "보기"}</span>
        <Icon name="chevR" size={20} className={open ? "rotate-90" : ""} />
      </button>
      {open && (
        <ul className="flex flex-col gap-2 py-3">
          {same.map((r) => (
            <li key={r.review_id} className="rounded-2xl border border-line bg-surface px-4 py-3">
              <p className="text-small text-ink-3">
                {PLATFORM_KO[r.platform]}, {r.rating}점, {monthDay(r.written_at)}
              </p>
              <p className="text-body text-ink-2">“{r.text}”</p>
            </li>
          ))}
        </ul>
      )}

      <h2 className="mt-6 mb-1 text-title">이렇게 점검해 봐요</h2>
      <ul>
        {items.map((it, i) => (
          <li key={it}>
            <label className="flex min-h-14 cursor-pointer items-center gap-3 border-b border-line py-2 text-body text-ink">
              <input type="checkbox" className="peer sr-only" checked={!!checked[i]} onChange={(e) => setChecked({ ...checked, [i]: e.target.checked })} />
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border-2 border-ink-3 text-brand-ink peer-checked:border-brand peer-checked:bg-brand peer-focus-visible:outline-3 peer-focus-visible:outline-brand">
                {checked[i] && <Icon name="check" size={20} />}
              </span>
              {it}
            </label>
          </li>
        ))}
      </ul>
    </SubPage>
  );
}
