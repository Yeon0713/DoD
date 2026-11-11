"use client";
// 아래 탭 4개 (오늘, 이번 주, 매출, 설정). Figma 05: 아이콘과 글자를 위아래 가운데에 둔다 (위아래 여백 10).
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "@/components/icons/Icon";

const TABS: { href: string; label: string; icon: IconName; match: (p: string) => boolean }[] = [
  { href: "/", label: "오늘", icon: "home", match: (p) => p === "/" },
  { href: "/week", label: "이번 주", icon: "calendar", match: (p) => p.startsWith("/week") },
  { href: "/sales", label: "매출", icon: "chart", match: (p) => p.startsWith("/sales") },
  { href: "/settings", label: "설정", icon: "sliders", match: (p) => p.startsWith("/settings") },
];

export function BottomTabs() {
  const path = usePathname();
  return (
    <nav aria-label="아래 탭" className="sticky bottom-0 z-10 flex border-t border-line bg-surface pt-2.5 pb-[max(10px,env(safe-area-inset-bottom))]">
      {TABS.map((t) => {
        const on = t.match(path);
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={on ? "page" : undefined}
            className={`flex flex-1 flex-col items-center gap-1 py-1.5 text-small ${on ? "font-bold text-brand" : "text-ink-3"}`}
          >
            <Icon name={t.icon} size={28} />
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
