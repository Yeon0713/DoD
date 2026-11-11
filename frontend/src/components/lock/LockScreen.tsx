"use client";
// 04-23 잠금 화면에서 시작. 휴대폰 잠금 화면에 도나 알림이 온 모습이다.
// 실제 푸시 발송은 2차(알림톡 포함)라, 지금은 이 화면으로 "알림을 눌러 앱이 열리는" 흐름을 본다.
// 알림 내용은 그 시각 오늘 화면의 맨 앞 카드에서 만든다.
import Image from "next/image";
import Link from "next/link";
import { useMemo } from "react";
import { useCardState } from "@/lib/cardState";
import { buildTodayCards } from "@/lib/todayCards";
import { hhmm, monthDay, weekdayName } from "@/lib/time";
import { useHome } from "@/lib/useHome";

export function LockScreen() {
  const { data, now, mounted, prefs } = useHome();
  const store = useCardState();
  const view = useMemo(() => (data && mounted ? buildTodayCards(data, now, prefs, store) : null), [data, mounted, now, prefs, store]);
  const card = view?.open[0];
  const time = card ? hhmm(view!.slotOf[card.id] ?? now.toISOString()) : mounted ? hhmm(now.toISOString()) : "";

  return (
    <main className="flex min-h-dvh flex-1 flex-col items-center bg-ink px-4 pt-16 text-brand-ink">
      <p className="text-body font-medium">{mounted ? `${monthDay(now)} ${weekdayName(now)}` : ""}</p>
      <p className="mt-1 text-[72px] leading-[84px] font-bold tracking-tight" aria-label={`지금 ${time}`}>
        {time}
      </p>
      {card ? (
        <Link
          href={`/?card=${encodeURIComponent(card.id)}`}
          className="mt-10 flex w-full flex-col gap-1 rounded-2xl bg-surface px-4 py-3.5 text-ink shadow-lg active:opacity-90"
          aria-label={`도나 알림: ${card.title.replace(/\n/g, " ")}. 눌러서 열기`}
        >
          <span className="flex items-center gap-2 text-small text-ink-2">
            <Image loading="eager" src="/donna/b3-2.png" alt="" width={28} height={28} className="rounded-full bg-brand-soft" />
            <span className="flex-1 font-bold text-ink">도나</span>
            <span>지금</span>
          </span>
          <span className="text-body font-bold">{card.title.replace(/\n/g, " ")}</span>
          <span className="text-small text-ink-2">{card.donna.text.replace(/\n/g, " ")}. 눌러서 확인해요</span>
        </Link>
      ) : (
        <p className="mt-10 text-body text-brand-soft">{data ? "지금은 도나 알림이 없어요" : ""}</p>
      )}
      <div className="flex-1" />
      <p className="mb-10 text-small text-brand-soft">알림을 누르면 도나가 열려요</p>
    </main>
  );
}
