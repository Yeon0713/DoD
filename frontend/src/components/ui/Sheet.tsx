"use client";
// 아래에서 올라오는 시트 (04-22 나중에, 04-65 올릴 곳). 뒤 화면은 어둡게 덮고 누를 수 없다.
import { useEffect, useRef, type ReactNode } from "react";

export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      aria-label={title}
      className="mx-auto mt-auto mb-0 w-full max-w-[375px] rounded-t-[24px] bg-surface p-0 text-ink backdrop:bg-ink/40"
    >
      <div className="px-6 pt-3 pb-[max(24px,env(safe-area-inset-bottom))]">
        <div className="mx-auto mb-5 h-1.5 w-10 rounded-full bg-line" aria-hidden />
        <h2 className="pre-line mb-4 text-title">{title}</h2>
        {children}
      </div>
    </dialog>
  );
}
