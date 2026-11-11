"use client";
// 아래 탭이 없는 화면(답글, 점검, 포스터, 처음 쓰는 날)이 같이 쓰는 부품.
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/icons/Icon";
import type { Donna } from "@/lib/cards";
import { PLATFORM_KO } from "@/lib/labels";
import { clearToast, peekToast } from "@/lib/localStore";
import type { Review } from "@/types/contract";
import { ProgressSteps, Stars } from "./parts";

/** 뒤로 버튼 + 제목 (04-5 "리뷰 답글"). 처음 쓰는 날 화면은 제목 대신 진행 막대를 둔다. */
export function SubPage({
  title,
  backHref,
  progress,
  children,
  footer,
}: {
  title?: string;
  backHref?: string;
  progress?: { total: number; done: number };
  children: ReactNode;
  footer?: ReactNode;
}) {
  const router = useRouter();
  return (
    <main className="flex flex-1 flex-col px-6 pt-[max(12px,env(safe-area-inset-top))] pb-[max(20px,env(safe-area-inset-bottom))]">
      <div className="flex h-11 items-center gap-2">
        <button
          type="button"
          aria-label="뒤로"
          onClick={() => (backHref ? router.push(backHref) : router.back())}
          className="-ml-2.5 flex h-11 w-11 items-center justify-center rounded-full text-ink active:bg-brand-soft"
        >
          <Icon name="chevL" size={26} />
        </button>
        {title && <h1 className="text-title">{title}</h1>}
        {progress && (
          <div className="flex-1 pr-1">
            <ProgressSteps total={progress.total} done={progress.done} label={`처음 설정 ${progress.total}단계 중 ${progress.done}단계`} />
          </div>
        )}
      </div>
      <div className="flex flex-1 flex-col pt-3">{children}</div>
      {footer && <div className="mt-6 flex flex-col gap-2">{footer}</div>}
    </main>
  );
}

/** 별점, 플랫폼, 리뷰 원문 상자 (04-5 위쪽) */
export function ReviewBox({ review, showPlatform = true }: { review: Review; showPlatform?: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      <Stars rating={review.rating} suffix={showPlatform ? PLATFORM_KO[review.platform] : undefined} />
      <p className="rounded-2xl border border-line bg-surface px-4 py-3.5 text-body text-balance text-ink-2">“{review.text}”</p>
    </div>
  );
}

/** 도나 그림 + 말풍선 (04-5 답글 초안) */
export function DraftBubble({ img = "b3-2", text, busy }: { img?: Donna; text: string; busy?: boolean }) {
  return (
    <div className="flex items-start gap-3">
      <Image loading="eager" src={`/donna/${img}.png`} alt="" width={48} height={48} className="mt-1 shrink-0" />
      <p className={`flex-1 rounded-2xl bg-brand-soft px-4 py-3.5 text-body text-ink ${busy ? "opacity-60" : ""}`} aria-busy={busy}>
        {text}
      </p>
    </div>
  );
}

/** 작은 안내 한 줄 (방패, 시계 아이콘) */
export function Note({ icon, children, center }: { icon: IconName; children: ReactNode; center?: boolean }) {
  return (
    <p className={`flex items-center gap-2 text-small text-ink-2 ${center ? "justify-center text-center" : ""}`}>
      <Icon name={icon} size={20} className={icon === "shield" ? "text-done" : "text-ink-2"} />
      <span className="pre-line">{children}</span>
    </p>
  );
}

/** 켜고 끄는 스위치 (04-20, 04-55, 04-58) */
export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-8 w-14 shrink-0 rounded-full border transition-colors ${checked ? "border-brand bg-brand" : "border-ink-3 bg-line"}`}
    >
      <span className={`absolute top-[3px] h-6 w-6 rounded-full shadow transition-all ${checked ? "left-[27px] bg-brand-ink" : "left-[3px] bg-white"}`} />
    </button>
  );
}

/** 목록 한 줄 (설정, 같이 하면 좋은 일) */
export function ListRow({ icon, title, sub, right, href, onClick }: { icon: IconName; title: string; sub?: string; right?: ReactNode; href?: string; onClick?: () => void }) {
  const inner = (
    <>
      <Icon name={icon} size={26} className="shrink-0 text-ink-2" />
      <span className="flex flex-1 flex-col">
        <span className="text-body text-ink">{title}</span>
        {sub && <span className="text-small text-ink-2">{sub}</span>}
      </span>
      {right}
      {(href || onClick) && <Icon name="chevR" size={20} className="shrink-0 text-ink-2" />}
    </>
  );
  const cls = "flex min-h-14 items-center gap-3 border-b border-line py-3 active:bg-brand-soft";
  if (href)
    return (
      <Link href={href} className={cls}>
        {inner}
      </Link>
    );
  if (onClick)
    return (
      <button type="button" onClick={onClick} className={`${cls} w-full text-left`}>
        {inner}
      </button>
    );
  return <div className={cls}>{inner}</div>;
}

/** "답글을 올렸어요" 띠 (04-5s). 2초 동안 위에 떠 있다. */
export function ToastHost() {
  const [toast, setToast] = useState<{ title: string; sub?: string } | null>(null);
  useEffect(() => {
    let hide: ReturnType<typeof setTimeout> | undefined;
    // 저장된 띠가 있으면 띄우고 2초 뒤에 지운다. 다른 화면에서 넘어올 때와 같은 화면에서 띄울 때 모두 쓴다.
    const pop = () => {
      const t = peekToast();
      if (!t) return;
      clearToast();
      setToast(t);
      if (hide) clearTimeout(hide);
      hide = setTimeout(() => setToast(null), 2200);
    };
    // 개발 모드에서 효과가 두 번 돌아도 띠를 잃지 않게, 한 박자 뒤에 읽는다.
    const first = setTimeout(pop, 0);
    window.addEventListener("dona:toast", pop);
    return () => {
      clearTimeout(first);
      if (hide) clearTimeout(hide);
      window.removeEventListener("dona:toast", pop);
    };
  }, []);
  if (!toast) return null;
  return (
    <div role="status" aria-live="polite" className="fixed inset-x-0 top-[max(12px,env(safe-area-inset-top))] z-50 mx-auto w-[343px] max-w-[calc(100%-32px)]">
      <button
        type="button"
        onClick={() => setToast(null)}
        aria-label={`${toast.title}. 눌러서 닫기`}
        className="flex w-full items-center gap-3 rounded-2xl border-2 border-done/50 bg-surface px-4 py-3 text-left shadow-lg"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-done-soft text-done">
          <Icon name="check" size={22} />
        </span>
        <span className="flex flex-col">
          <span className="text-body font-bold text-ink">{toast.title}</span>
          {toast.sub && <span className="text-small text-ink-2">{toast.sub}</span>}
        </span>
      </button>
    </div>
  );
}

/** 가운데 큰 그림 + 제목 + 설명 (04-52, 04-55, 04-57, 04-66) */
export function CenterMessage({ img, icon, title, sub, children }: { img?: Donna; icon?: IconName; title: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center text-center">
      {img && <Image src={`/donna/${img}.png`} alt="" width={200} height={200} priority />}
      {icon && (
        <span className="flex h-24 w-24 items-center justify-center rounded-full bg-brand-soft text-brand">
          <Icon name={icon} size={48} />
        </span>
      )}
      <h1 className="pre-line mt-4 text-display">{title}</h1>
      {sub && <p className="pre-line mt-2 text-body text-ink-2">{sub}</p>}
      {children}
    </div>
  );
}

/** 목업(나중에 실제 API) 동작이 실패했을 때 화면 아래에 보여 주는 안내 (04-5f 모양). 쓴 내용은 그대로 둔다. */
export function FailNote({ title, sub = "인터넷이 끊겼어요.\n다시 눌러 주세요" }: { title: string; sub?: string }) {
  return (
    <div role="alert" className="mt-6 flex items-start gap-3 rounded-2xl bg-urgent-soft px-4 py-3.5 text-urgent">
      <Icon name="wifiOff" size={26} />
      <span className="flex flex-col">
        <span className="text-body font-bold">{title}</span>
        <span className="pre-line text-small text-ink-2">{sub}</span>
      </span>
    </div>
  );
}
