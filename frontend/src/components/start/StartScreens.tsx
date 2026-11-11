"use client";
// 처음 쓰는 날 (Figma 04-1 소개, 04-2 가게 찾기, 04-2b 못 찾았을 때, 04-3 알림 시간, 04-3b 알림 켜기).
// 세 걸음이면 첫 할 일 카드가 나온다.
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { Icon, type IconName } from "@/components/icons/Icon";
import { Bone, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { SubPage } from "@/components/ui/sub";
import { prefs } from "@/lib/localStore";
import { useHome } from "@/lib/useHome";
import { STORE_ADDRESS } from "@/mocks/extras";
import type { Platform } from "@/types/contract";

const STEPS = 4;

export function IntroScreen() {
  const reasons: { icon: IconName; text: string }[] = [
    { icon: "message", text: "배달앱 리뷰에 답글을 써 둬요" },
    { icon: "calendar", text: "축제, 경기, 날씨를 미리 알려요" },
    { icon: "trendUp", text: "다시 온 손님 수까지 알려요" },
  ];
  return (
    <main className="flex flex-1 flex-col px-6 pt-16 pb-[max(20px,env(safe-area-inset-bottom))]">
      <div className="flex flex-col items-center text-center">
        <Image src="/donna/b4-0.png" alt="" width={220} height={220} priority />
        <h1 className="mt-2 text-display">
          손님이 다시 오게,
          <br />
          도나가 먼저 챙겨요
        </h1>
        <p className="mt-2 text-body text-ink-2">사장님은 보고 누르기만 하세요</p>
      </div>
      <div className="flex-1" />
      <ul className="mb-6 flex flex-col">
        {reasons.map((r) => (
          <li key={r.text} className="flex h-12 items-center gap-3 text-body font-medium">
            <Icon name={r.icon} size={28} className="text-brand" />
            {r.text}
          </li>
        ))}
      </ul>
      <PrimaryButton href="/start/store">시작하기</PrimaryButton>
    </main>
  );
}

const PLATFORM_SHORT: Record<Platform, string> = { BAEMIN: "배민", COUPANG: "쿠팡이츠", YOGIYO: "요기요", NAVER: "네이버" };

function TitleWithDonna({ title, img, sub }: { title: string; img: string; sub?: string }) {
  return (
    <>
      <div className="flex items-start justify-between gap-2">
        <h1 className="pre-line pt-3 text-display">{title}</h1>
        <Image loading="eager" src={`/donna/${img}.png`} alt="" width={88} height={88} />
      </div>
      {sub && <p className="text-body text-ink-2">{sub}</p>}
    </>
  );
}

export function StoreSearchScreen() {
  const router = useRouter();
  const search = useSearchParams();
  const again = search.get("again") === "1";
  // 검토용 ?q=가게이름 (04-2b 못 찾았을 때)
  const initialQ = search.get("q");
  const { data } = useHome();
  const [query, setQuery] = useState<string | null>(initialQ);
  const input = useRef<HTMLInputElement>(null);

  if (!data) {
    return (
      <SubPage progress={{ total: STEPS, done: 1 }}>
        <Bone className="h-16 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const name = s.name.replace(/\s*\(.*\)\s*/g, "").trim();
  const q = query ?? name;
  // 쓰는 대로 바로 찾는다. 다 쓰고 나서 버튼을 눌러야만 바뀌면, 바뀌기 전 결과의 "우리 가게 맞아요"를 누를 수 있다.
  const searched = q.trim();
  const norm = (x: string) => x.replace(/\s/g, "");
  const found = searched.length >= 2 && (norm(name).includes(norm(searched)) || norm(searched).includes(norm(name)));
  const platforms = (["BAEMIN", "COUPANG", "YOGIYO", "NAVER"] as Platform[]).filter((p) => data.reviews.reviews.some((r) => r.platform === p));

  return (
    <SubPage
      progress={again ? undefined : { total: STEPS, done: 1 }}
      backHref={again ? "/settings" : "/start"}
      footer={
        found ? (
          <PrimaryButton onClick={() => router.push(again ? "/settings" : "/start/hours")}>우리 가게 맞아요</PrimaryButton>
        ) : (
          <PrimaryButton
            onClick={() => {
              setQuery("");
              input.current?.focus();
            }}
          >
            다시 찾기
          </PrimaryButton>
        )
      }
    >
      <TitleWithDonna title={"우리 가게를\n찾아 주세요"} img="b3-1" />
      <form
        className="mt-4"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          input.current?.blur();
        }}
      >
        <label className="flex h-[60px] items-center gap-2.5 rounded-[14px] border border-ink-3 bg-surface px-4 focus-within:border-brand focus-within:ring-2 focus-within:ring-brand-soft">
          <Icon name="search" size={24} className="text-ink-2" />
          <span className="sr-only">가게 이름</span>
          <input
            ref={input}
            value={q}
            onChange={(e) => setQuery(e.target.value)}
            enterKeyHint="search"
            className="flex-1 bg-transparent text-body text-ink outline-none"
          />
        </label>
      </form>

      {found ? (
        <>
          <div className="mt-4 flex items-center gap-3 rounded-2xl border-2 border-brand bg-brand-soft px-4 py-4" aria-label="찾은 가게, 골라 둠">
            <Icon name="store" size={32} className="text-brand" />
            <span className="flex flex-1 flex-col">
              <span className="text-body font-bold text-ink">{name}</span>
              <span className="text-label text-ink-2">{STORE_ADDRESS[s.store_id] ?? ""}</span>
            </span>
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand text-brand-ink">
              <Icon name="check" size={18} />
            </span>
          </div>
          <p className="mt-4 flex items-start gap-3 text-body font-medium text-ink">
            <Icon name="messages" size={28} className="text-brand" />
            <span>
              {platforms.map((p) => PLATFORM_SHORT[p]).join(", ")}
              <br />
              리뷰 {data.reviews.reviews.length}개를 함께 찾았어요
            </span>
          </p>
        </>
      ) : (
        <div className="mt-10 flex flex-col items-center text-center" role="status">
          <Image loading="eager" src="/donna/question.png" alt="" width={100} height={147} />
          <p className="mt-3 text-title">가게를 못 찾았어요</p>
          <p className="mt-1 text-body text-ink-2">
            가게 이름을 짧게 써 보세요
            <br />
            예: {name.split(" ")[0]}
          </p>
        </div>
      )}
    </SubPage>
  );
}

export function NotifyOnScreen() {
  const router = useRouter();
  const { data } = useHome();
  const time = data?.settings.settings.slots.AFTERNOON ?? "14:00";
  const finish = (notifyOff: boolean) => {
    prefs.write({ onboarded: true, notifyOff, firstDayPending: true });
    router.replace("/");
  };
  const turnOn = async () => {
    const res = typeof Notification === "undefined" ? "denied" : await Notification.requestPermission();
    finish(res !== "granted");
  };
  return (
    <SubPage
      progress={{ total: STEPS, done: 4 }}
      footer={
        <>
          <PrimaryButton onClick={turnOn}>알림 켜기</PrimaryButton>
          <SecondaryButton onClick={() => finish(true)}>나중에 켤게요</SecondaryButton>
        </>
      }
    >
      <TitleWithDonna title={"알림을\n켜 주세요"} img="b1-1" sub="하루 3번, 고른 시간에만 알려 드려요" />
      <div className="mt-5 rounded-2xl border border-line bg-surface px-4 py-3.5 shadow-sm" aria-label="알림 예시">
        <div className="flex items-center gap-1.5 text-small text-ink-2">
          <Icon name="bell" size={18} />
          <span className="flex-1">도나</span>
          <span>{time}</span>
        </div>
        <p className="mt-1 text-body font-medium text-ink">배달이 늦었다는 리뷰가 왔어요</p>
        <p className="text-small text-ink-2">사과 답글을 써 뒀어요</p>
      </div>
      <p className="mt-2 text-center text-small text-ink-3">이렇게 알려 드려요</p>
    </SubPage>
  );
}
