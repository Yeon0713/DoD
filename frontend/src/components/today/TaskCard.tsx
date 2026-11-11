// 오늘 화면의 할 일 카드 한 장 (Figma 04-4 할 일 카드). 내용은 lib/cards.ts가 만든다.
import { Icon } from "@/components/icons/Icon";
import { Stars, StatusPill } from "@/components/ui/parts";
import type { CardBlock, CardView } from "@/lib/cards";
import { PosterThumb } from "@/components/poster/PosterCard";

function Block({ b }: { b: CardBlock }) {
  switch (b.type) {
    case "stars":
      return <Stars rating={b.rating} />;
    case "quote":
      return <p className="pre-line text-body text-balance text-ink-2">“{b.text}”</p>;
    case "text":
      return <p className="pre-line text-body text-ink-2">{b.text}</p>;
    case "iconLine":
      return (
        <div className="flex items-center gap-2.5 text-ink">
          <span className="flex shrink-0 gap-1 text-brand">
            {b.icons.map((i) => (
              <Icon key={i} name={i} size={28} />
            ))}
          </span>
          <span className="pre-line text-body font-medium">{b.text}</span>
        </div>
      );
    case "iconRow":
      return (
        <div className="flex gap-2 text-brand" aria-hidden>
          {Array.from({ length: b.count }, (_, i) => (
            <Icon key={i} name={b.icon} size={28} />
          ))}
        </div>
      );
    case "weekStrip": {
      // 월~일 순서. day는 0=일요일
      const order = [1, 2, 3, 4, 5, 6, 0];
      const names = ["일", "월", "화", "수", "목", "금", "토"];
      return (
        <div className="flex gap-1.5" aria-label={`매주 ${names[b.day]}요일`}>
          {order.map((d) => (
            <span
              key={d}
              className={`flex h-9 flex-1 items-center justify-center rounded-lg text-label ${d === b.day ? "bg-brand font-bold text-brand-ink" : "bg-paper text-ink-3"}`}
            >
              {names[d]}
            </span>
          ))}
        </div>
      );
    }
    case "menuPreview":
      return (
        <div className="flex flex-col gap-1 rounded-[14px] border border-line bg-paper p-3">
          <span className="text-small text-ink-2">{b.header}</span>
          <ol className="flex flex-col gap-1">
            {b.rows.map((r, i) => (
              <li key={r.name} className={`flex h-10 items-center gap-2.5 rounded-[10px] px-2.5 ${r.from ? "bg-brand-soft" : ""}`}>
                <span className={`w-4 text-title ${r.from ? "text-brand" : "text-ink-3"}`}>{i + 1}</span>
                <span className={`flex-1 text-body ${r.from ? "font-medium text-ink" : "text-ink-2"}`}>{r.name}</span>
                {r.from && (
                  <span className="flex items-center gap-1 text-small text-brand">
                    <Icon name="arrowUp" size={18} />
                    {r.from}번째에서
                  </span>
                )}
              </li>
            ))}
          </ol>
        </div>
      );
    case "posterRow":
      return (
        <div className="flex items-center gap-3.5">
          <PosterThumb {...b.poster} />
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <span className="flex items-start gap-2 text-ink">
              <Icon name={b.icon} size={26} className="shrink-0 text-brand" />
              <span className="pre-line text-body font-medium">{b.when}</span>
            </span>
            <span className="pre-line text-body text-ink-2">{b.text}</span>
          </div>
        </div>
      );
    case "bars":
      return (
        <div className="flex flex-col gap-2">
          {b.rows.map((r) => (
            <div key={r.label} className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between">
                <span className="text-label text-ink-2">{r.label}</span>
                <span className={`text-body font-bold ${r.accent ? "text-calm" : "text-ink-2"}`}>{r.value}</span>
              </div>
              <div className="h-3 overflow-hidden rounded-full bg-line">
                <div className={`h-full rounded-full ${r.accent ? "bg-calm" : "bg-ink-3"}`} style={{ width: `${Math.max(3, Math.min(100, r.percent))}%` }} />
              </div>
            </div>
          ))}
        </div>
      );
  }
}

export function TaskCard({ card }: { card: CardView }) {
  return (
    <article className="flex flex-col gap-3.5 rounded-[20px] border border-line bg-surface px-5 pt-5 pb-[22px]" aria-labelledby={`t-${card.id}`}>
      <StatusPill tone={card.tone} icon={card.pill.icon}>
        {card.pill.text}
      </StatusPill>
      <h2 id={`t-${card.id}`} className="pre-line text-title text-ink">
        {card.title}
      </h2>
      {card.blocks.map((b, i) => (
        <Block key={i} b={b} />
      ))}
    </article>
  );
}
