// 포스터 한 장 (Figma 04-63 게시물 4:5). 미리 보기 화면과 오늘 카드(05-31n) 썸네일이 같이 쓴다.
import Image from "next/image";
import { Icon, type IconName } from "@/components/icons/Icon";
import { THEME_STYLE, type Theme } from "@/lib/poster";

export type PosterProps = { photo?: string; menu: string; dateLine: string; icon: IconName; headline: string; store: string; theme: Theme };

export function PosterCard({ photo, menu, dateLine, icon, headline, store, theme }: PosterProps) {
  const t = THEME_STYLE[theme];
  return (
    <figure className="w-[300px] shrink-0 snap-center overflow-hidden rounded-2xl border border-line" aria-label={`포스터: ${headline.replace("\n", " ")}`}>
      <div className="relative flex h-[225px] items-center justify-center bg-brand-soft">
        {photo ? (
          // 사장님이 고른 사진(blob 주소)이라 next/image 최적화를 쓰지 않는다.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={photo} alt={menu} className="h-full w-full object-cover" />
        ) : (
          <span className="flex flex-col items-center gap-1 text-ink-2">
            <Icon name="image" size={44} />
            <span className="text-small">{menu} 사진</span>
          </span>
        )}
      </div>
      <figcaption className={`flex min-h-[150px] items-end justify-between gap-2 px-4 py-4 ${t.bg}`}>
        <span className="flex flex-col gap-1">
          <span className={`flex items-center gap-1 text-small ${t.sub}`}>
            <Icon name={icon} size={16} />
            {dateLine}
          </span>
          <span className={`pre-line text-title ${t.text}`}>{headline}</span>
          <span className={`text-small ${t.sub}`}>{store}</span>
        </span>
        <Image loading="eager" src="/donna/b3-0.png" alt="" width={64} height={64} className="shrink-0" />
      </figcaption>
    </figure>
  );
}

/** 오늘 카드 안의 작은 포스터 (300 × 375를 0.44배) */
export function PosterThumb(p: PosterProps) {
  return (
    <div className="h-[165px] w-[132px] shrink-0 overflow-hidden rounded-xl" aria-hidden>
      <div className="origin-top-left scale-[0.44]">
        <PosterCard {...p} />
      </div>
    </div>
  );
}
