// 여러 화면이 같이 쓰는 작은 부품. 크기와 색은 Figma 04 시안(docs/frontend_plan_v4.md 3장)을 따른다.
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { Icon, type IconName } from "@/components/icons/Icon";
import type { Donna, Tone } from "@/lib/cards";

const TONE: Record<Tone, string> = {
  urgent: "bg-urgent-soft text-urgent",
  brand: "bg-brand-soft text-brand",
  calm: "bg-calm-soft text-calm",
  done: "bg-done-soft text-done",
};

export function StatusPill({ tone, icon, children }: { tone: Tone; icon: IconName; children: ReactNode }) {
  return (
    <span className={`inline-flex h-8 items-center gap-1.5 self-start rounded-full pr-3 pl-2.5 text-label ${TONE[tone]}`}>
      <Icon name={icon} size={18} />
      {children}
    </span>
  );
}

export function Stars({ rating, suffix }: { rating: number; suffix?: string }) {
  return (
    <div className="flex items-center gap-0.5 text-busy" aria-label={`별점 ${rating}점`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Icon key={i} name={i <= rating ? "starFill" : "star"} size={22} />
      ))}
      <span className="ml-1.5 text-label text-ink-2">
        {rating}점{suffix ? `, ${suffix}` : ""}
      </span>
    </div>
  );
}

export function DonnaSays({ img, size = 72, children }: { img: Donna; size?: number; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <Image loading="eager" src={`/donna/${img}.png`} alt="" width={size} height={size} className="shrink-0" />
      <p className="pre-line text-body font-medium text-ink">{children}</p>
    </div>
  );
}

export function ProgressSteps({ total, done, label }: { total: number; done: number; label?: string }) {
  return (
    <div
      className="flex gap-1.5"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={done}
      aria-label={label ?? `오늘 할 일 ${total}개 중 ${done}개 끝냄`}
    >
      {Array.from({ length: Math.max(total, 1) }, (_, i) => (
        <span key={i} className={`h-1.5 flex-1 rounded-[3px] ${i < done ? "bg-brand" : "bg-line"}`} />
      ))}
    </div>
  );
}

type ButtonProps = { children: ReactNode; href?: string; onClick?: () => void; disabled?: boolean };

/** 화면마다 하나뿐인 주 버튼. 높이 56, 둥글기 14 */
export function PrimaryButton({ children, href, onClick, disabled }: ButtonProps) {
  const cls =
    "flex h-14 w-full items-center justify-center rounded-[14px] bg-brand text-button text-brand-ink active:opacity-90 disabled:opacity-50 focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brand";
  return href ? (
    <Link href={href} className={cls} onClick={onClick}>
      {children}
    </Link>
  ) : (
    <button type="button" className={cls} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

/** "나중에 할게요" 같은 보조 버튼. 높이 48, 테두리 없음. outline이면 "고쳐 쓰기"처럼 테두리가 있다. */
export function SecondaryButton({ children, href, onClick, outline }: ButtonProps & { outline?: boolean }) {
  const cls = `flex w-full items-center justify-center rounded-[14px] text-body font-medium ${
    outline ? "h-14 border border-brand bg-surface text-button text-brand" : "h-12 text-ink-2"
  } active:bg-brand-soft focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brand`;
  return href ? (
    <Link href={href} className={cls} onClick={onClick}>
      {children}
    </Link>
  ) : (
    <button type="button" className={cls} onClick={onClick}>
      {children}
    </button>
  );
}

/** 불러오는 중 뼈대. 0.3초부터 보이고 빛이 왼쪽에서 오른쪽으로 지나간다 (04-8, 컴포넌트 03/뼈대 빛). */
export function Bone({ className = "" }: { className?: string }) {
  return (
    <span className={`relative block overflow-hidden rounded-lg bg-skeleton ${className}`}>
      <span className="animate-shimmer absolute inset-0 bg-gradient-to-r from-transparent via-white/45 to-transparent" />
    </span>
  );
}
