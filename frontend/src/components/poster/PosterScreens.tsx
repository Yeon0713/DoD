"use client";
// 인스타 포스터 (Figma 04-61 사진 고르기, 04-62 만드는 중, 04-63 미리 보기, 04-64 글자 고치기,
// 04-65 올릴 곳 고르기, 04-66 보냈어요). 그림은 메뉴 사진 중심이고, 휴대폰 사진도 고를 수 있다.
import Image from "next/image";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { Icon, type IconName } from "@/components/icons/Icon";
import { Bone, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Sheet } from "@/components/ui/Sheet";
import { CenterMessage, FailNote, Note, SubPage } from "@/components/ui/sub";
import { makePoster } from "@/lib/actions";
import { happening } from "@/lib/cards";
import { defaultHeadline, readKept, THEME_STYLE, THEMES, type KeptPoster, type Theme } from "@/lib/poster";
import { PosterCard } from "./PosterCard";
import { markDone } from "@/lib/cardState";
import { drafts, flashToast } from "@/lib/localStore";
import { clockKo, relativeDay } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import { storeMenus } from "@/mocks/extras";

type Step = "pick" | "making" | "preview" | "edit" | "sent";
/** 포스터를 1080 × 1350 그림 파일로 그린다 (인스타 게시물 4:5). */
async function renderPoster(o: { photo?: string; menu: string; dateLine: string; headline: string; store: string; theme: Theme }): Promise<Blob> {
  const W = 1080;
  const H = 1350;
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const g = c.getContext("2d")!;
  const font = getComputedStyle(document.body).fontFamily;
  const t = THEME_STYLE[o.theme];
  const load = (src: string) =>
    new Promise<HTMLImageElement>((res, rej) => {
      const im = new window.Image();
      im.onload = () => res(im);
      im.onerror = rej;
      im.src = src;
    });
  const photoH = 810;
  g.fillStyle = "#f2e4d4";
  g.fillRect(0, 0, W, photoH);
  if (o.photo) {
    const im = await load(o.photo);
    const sc = Math.max(W / im.width, photoH / im.height);
    g.drawImage(im, (W - im.width * sc) / 2, (photoH - im.height * sc) / 2, im.width * sc, im.height * sc);
  } else {
    g.fillStyle = "#5c4533";
    g.font = `500 48px ${font}`;
    g.textAlign = "center";
    g.fillText(`${o.menu} 사진`, W / 2, photoH / 2);
  }
  g.fillStyle = t.canvasBg;
  g.fillRect(0, photoH, W, H - photoH);
  g.textAlign = "left";
  g.fillStyle = t.canvasText;
  g.font = `500 40px ${font}`;
  g.fillText(o.dateLine, 64, photoH + 96);
  g.font = `700 76px ${font}`;
  o.headline.split("\n").forEach((line, i) => g.fillText(line, 64, photoH + 210 + i * 100));
  g.font = `500 40px ${font}`;
  g.fillText(o.store, 64, H - 64);
  try {
    const donna = await load("/donna/b3-0.png");
    g.drawImage(donna, W - 300, H - 300, 240, 240);
  } catch {
    /* 그림이 없어도 포스터는 만든다 */
  }
  return new Promise((res) => c.toBlob((b) => res(b!), "image/png"));
}

export function PosterScreen() {
  const planId = decodeURIComponent(useParams<{ planId: string }>().planId ?? "");
  const router = useRouter();
  // ?step=share(실행 알림에서), 검토용 ?step=making|preview|edit|sent
  const stepParam = useSearchParams().get("step");
  const shareFirst = stepParam === "share";
  const initialStep: Step = shareFirst ? "preview" : stepParam === "making" || stepParam === "preview" || stepParam === "edit" || stepParam === "sent" ? stepParam : "pick";
  const { data, now } = useHome();
  // 승인 날 만들어 둔 포스터(메뉴, 글자, 색)를 실행 날 그대로 올리려고 이 기기에 저장해 둔다. 서버 PATCH /api/posters가 생기면 옮긴다.
  const draftKey = `poster:${planId}`;
  const [kept] = useState<KeptPoster | null>(() => readKept(drafts.read(), draftKey));
  const [step, setStep] = useState<Step>(initialStep);
  const [menuIdx, setMenuIdx] = useState(kept?.menuIdx ?? 0);
  const [photo, setPhoto] = useState<string | undefined>();
  const [headline, setHeadline] = useState<string | null>(kept?.headline ?? null);
  const [storeLine, setStoreLine] = useState<string | null>(kept?.storeLine ?? null);
  const [sheet, setSheet] = useState(shareFirst);
  const [dest, setDest] = useState<"story" | "feed" | "save">("story");
  const [theme, setTheme] = useState<Theme>(kept?.theme ?? "dark");
  const [sentKind, setSentKind] = useState<"shared" | "saved">("shared");
  const [failed, setFailed] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  if (!data) {
    return (
      <SubPage title="포스터">
        <Bone className="h-80 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const plan = data.plan.plan_items.find((x) => x.plan_id === planId);
  const h = plan ? happening(data.calendar.cells, plan) : { dateLine: "", shortLine: "", icon: "image" as IconName, kind: null };
  const menus = storeMenus(s.category).map((m) => m.name);
  const menu = menus[menuIdx];
  const store = storeLine ?? s.name.replace(/\s*\(.*\)\s*/g, "").trim();
  const head = headline ?? defaultHeadline(plan ? happening(data.calendar.cells, plan) : null, s);
  // 포스터 날짜 줄은 한 줄에 들어가게 줄여 쓴다. 예: "11월 21일, 22일 주말"
  const poster = { photo, menu, dateLine: h.shortLine, icon: h.icon, headline: head, store };

  // 승인 알림(전날)에서 들어왔으면 지금 올리지 않고 만들어 둔다. 실행 알림(04-31)에서 "포스터 올리기"로 보낸다.
  const execAt = plan?.execute_at ?? null;
  const scheduled = !shareFirst && !!execAt && new Date(execAt).getTime() > now.getTime();
  const keep = () => {
    drafts.write({ [draftKey]: JSON.stringify({ menuIdx, headline, storeLine, theme } satisfies KeptPoster) });
    markDone(`APPROVAL_REQUEST:${planId}`);
    if (execAt) flashToast("포스터를 만들어 뒀어요", `${relativeDay(execAt, now)} ${clockKo(execAt)}에 올리라고 알려 드릴게요`);
    router.push("/");
  };

  const make = async () => {
    setStep("making");
    setFailed(false);
    try {
      await makePoster();
    } catch {
      setFailed(true);
      setStep("pick");
      return;
    }
    setStep("preview");
  };

  const send = async () => {
    const blob = await renderPoster({ ...poster, theme });
    const f = new File([blob], "dona-poster.png", { type: "image/png" });
    let kind: "shared" | "saved" = "saved";
    if (dest !== "save" && navigator.canShare?.({ files: [f] })) {
      try {
        await navigator.share({ files: [f], title: head.replaceAll("\n", " ") });
        kind = "shared";
      } catch {
        return; // 사장님이 공유 창을 닫았다
      }
    } else {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "dona-poster.png";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }
    setSentKind(kind);
    setSheet(false);
    setStep("sent");
  };

  if (step === "making") {
    return (
      <SubPage>
        <div className="flex items-center gap-3" role="status">
          <Image loading="eager" src="/donna/b3-2.png" alt="" width={72} height={72} />
          <p className="text-title">
            포스터를
            <br />
            만들고 있어요
          </p>
        </div>
        <div className="mt-4 overflow-hidden rounded-2xl border border-line bg-surface" aria-hidden>
          <Bone className="h-56 w-full rounded-none" />
          <div className="flex flex-col gap-2 p-4">
            <Bone className="h-3.5 w-40" />
            <Bone className="h-3.5 w-32" />
            <Bone className="h-3.5 w-20" />
          </div>
        </div>
      </SubPage>
    );
  }

  if (step === "sent") {
    return (
      <SubPage
        footer={
          <PrimaryButton
            onClick={() => {
              markDone(`APPROVAL_REQUEST:${planId}`);
              markDone(`EXECUTE_REMINDER:${planId}`);
              router.push("/");
            }}
          >
            확인했어요
          </PrimaryButton>
        }
      >
        {sentKind === "shared" ? (
          <CenterMessage img="b4-2" title={"인스타그램으로\n보냈어요"} sub={"인스타그램에서 공유를 누르면\n올라가요"} />
        ) : (
          <CenterMessage img="b4-2" title={"휴대폰에\n저장했어요"} sub={"인스타그램에서 사진을 골라\n직접 올려 주세요"} />
        )}
      </SubPage>
    );
  }

  if (step === "edit") {
    return (
      <SubPage title="글자 고치기" footer={<PrimaryButton onClick={() => setStep("preview")}>다 고쳤어요</PrimaryButton>}>
        <label className="text-label text-ink-2" htmlFor="big">
          큰 글자
        </label>
        <textarea
          id="big"
          rows={Math.max(3, head.split("\n").length)}
          value={head}
          onChange={(e) => setHeadline(e.target.value)}
          className="mt-1 w-full resize-none rounded-2xl border-2 border-brand bg-surface px-4 py-3 text-body outline-none"
        />
        <label className="mt-4 text-label text-ink-2" htmlFor="small">
          작은 글자
        </label>
        <input
          id="small"
          value={store}
          onChange={(e) => setStoreLine(e.target.value)}
          className="mt-1 h-14 w-full rounded-2xl border-2 border-brand bg-surface px-4 text-body outline-none"
        />
      </SubPage>
    );
  }

  if (step === "preview") {
    return (
      <>
        <SubPage
          title="포스터 미리 보기"
          footer={
            <>
              {scheduled ? (
                <PrimaryButton onClick={keep}>이대로 만들어 두기</PrimaryButton>
              ) : (
                <PrimaryButton onClick={() => setSheet(true)}>인스타에 올리기</PrimaryButton>
              )}
              <SecondaryButton outline onClick={() => setStep("edit")}>
                글자 고치기
              </SecondaryButton>
            </>
          }
        >
          <div
            ref={(el) => {
              // 만들어 둔 색으로 처음 보여 준다.
              if (el && el.dataset.ready !== "1") {
                el.dataset.ready = "1";
                el.scrollLeft = THEMES.indexOf(theme) * 312;
              }
            }}
            className="-mx-6 flex snap-x snap-mandatory gap-3 overflow-x-auto px-[37px] pb-2 [scrollbar-width:none]"
            onScroll={(e) => {
              const i = Math.round(e.currentTarget.scrollLeft / 312);
              if (THEMES[i] && THEMES[i] !== theme) setTheme(THEMES[i]);
            }}
          >
            {THEMES.map((t) => (
              <PosterCard key={t} {...poster} theme={t} />
            ))}
          </div>
          <p className="mt-2 text-center text-small text-ink-2">3장 중 {THEMES.indexOf(theme) + 1}장, 옆으로 넘겨 보세요</p>
        </SubPage>
        <Sheet open={sheet} onClose={() => setSheet(false)} title="어디에 올릴까요?">
          <fieldset className="flex flex-col gap-2.5">
            <legend className="sr-only">올릴 곳</legend>
            {(
              [
                { k: "story", icon: "image", title: "인스타 스토리", sub: "24시간 동안 보여요" },
                { k: "feed", icon: "list", title: "인스타 게시물", sub: "피드에 계속 남아요" },
                { k: "save", icon: "download", title: "휴대폰에 저장", sub: "나중에 직접 올려요" },
              ] as const
            ).map((o) => (
              <label
                key={o.k}
                className={`flex min-h-16 cursor-pointer items-center gap-3 rounded-[14px] border px-4 py-2 ${dest === o.k ? "border-brand bg-brand-soft" : "border-line bg-surface"}`}
              >
                <input type="radio" name="dest" className="sr-only" checked={dest === o.k} onChange={() => setDest(o.k)} />
                <Icon name={o.icon} size={26} className="text-ink-2" />
                <span className="flex flex-col">
                  <span className="text-body font-medium">{o.title}</span>
                  <span className="text-small text-ink-2">{o.sub}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <div className="mt-5">
            <PrimaryButton onClick={send}>{dest === "save" ? "휴대폰에 저장하기" : "인스타그램으로 보내기"}</PrimaryButton>
          </div>
        </Sheet>
      </>
    );
  }

  // 04-61 사진 고르기
  return (
    <SubPage
      title="메뉴 사진 고르기"
      footer={
        <>
          <PrimaryButton onClick={make}>이 사진으로 만들기</PrimaryButton>
          <SecondaryButton onClick={() => file.current?.click()}>휴대폰에서 고르기</SecondaryButton>
          <input
            ref={file}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) {
                setPhoto(URL.createObjectURL(f));
                make();
              }
            }}
          />
        </>
      }
    >
      <h2 className="text-display">
        어떤 메뉴를
        <br />
        보여 줄까요?
      </h2>
      <div className="mt-1">
        <Note icon="store">네이버 플레이스에 올린 사진이에요</Note>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-x-3 gap-y-3" role="radiogroup" aria-label="메뉴 사진">
        {menus.slice(0, 4).map((m, i) => (
          <button key={m} type="button" role="radio" aria-checked={menuIdx === i} onClick={() => setMenuIdx(i)} className="flex flex-col items-start gap-1.5 text-left">
            <span
              className={`flex h-[100px] w-full flex-col items-center justify-center rounded-2xl bg-brand-soft text-ink-2 ${menuIdx === i ? "border-2 border-brand" : ""}`}
            >
              <Icon name="image" size={28} />
              <span className="text-small">사진</span>
            </span>
            <span className="flex items-center gap-1 text-body">
              {menuIdx === i && (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand text-brand-ink">
                  <Icon name="check" size={14} />
                </span>
              )}
              {m}
            </span>
          </button>
        ))}
      </div>
      {failed && <FailNote title="포스터를 못 만들었어요" />}
    </SubPage>
  );
}
