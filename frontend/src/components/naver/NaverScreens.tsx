"use client";
// 네이버 플레이스 (Figma 04-51 연결 안내, 04-52 연결됐어요, 04-53 바꿀 순서, 04-54 바꾸는 중, 04-55 바꿨어요, 04-57 되돌렸어요).
// 처음 한 번은 바꿀 순서를 보여 주고 사장님이 누르면 바꾼다. "다음부터는 알아서"를 켜면 그 뒤로는 바꾼 뒤에 알린다.
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon, type IconName } from "@/components/icons/Icon";
import { Bone, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { CenterMessage, FailNote, Note, SubPage, Toggle } from "@/components/ui/sub";
import { applyMenuOrder, connectNaver } from "@/lib/actions";
import { menuOrderFor } from "@/lib/menuOrder";
import { markDone } from "@/lib/cardState";
import { withObject } from "@/lib/labels";
import { flashToast, prefs } from "@/lib/localStore";
import { clockKo, relativeDay } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import { storeMenus } from "@/mocks/extras";
import Image from "next/image";

export function NaverConnectScreen() {
  const router = useRouter();
  const plan = useSearchParams().get("plan");
  const { data } = useHome();
  // 검토용 ?view=done 이면 04-52 연결됐어요를 바로 본다.
  const [step, setStep] = useState<"intro" | "connecting" | "done" | "failed">(useSearchParams().get("view") === "done" ? "done" : "intro");
  const name = data?.settings.settings.name.replace(/\s*\(.*\)\s*/g, "").trim() ?? "";
  const next = plan ? `/menu-order/${encodeURIComponent(plan)}` : "/settings/naver";

  if (step === "done") {
    return (
      <SubPage footer={<PrimaryButton onClick={() => router.replace(next)}>{plan ? "바꿀 순서 보기" : "확인했어요"}</PrimaryButton>}>
        <CenterMessage img="b1-2" title="연결됐어요" sub={`${name}의\n메뉴를 불러왔어요`} />
      </SubPage>
    );
  }

  const items: { icon: IconName; text: string }[] = [
    { icon: "link", text: "처음 한 번만 연결해요" },
    { icon: "list", text: "바꿀 순서를 먼저 보여 드려요" },
    { icon: "check", text: "누르시면 도나가 바꿔요" },
  ];
  const connect = async () => {
    setStep("connecting");
    try {
      await connectNaver();
      prefs.write({ naverConnected: true });
      setStep("done");
    } catch {
      setStep("failed");
    }
  };
  return (
    <SubPage
      footer={
        <>
          <PrimaryButton onClick={connect} disabled={step === "connecting"}>
            {step === "connecting" ? "연결하는 중" : step === "failed" ? "다시 연결하기" : "네이버로 연결하기"}
          </PrimaryButton>
          <SecondaryButton onClick={() => router.back()}>나중에 할게요</SecondaryButton>
        </>
      }
    >
      <div className="flex items-start justify-between">
        <h1 className="pt-3 text-display">
          네이버 플레이스를
          <br />
          연결해 주세요
        </h1>
        <Image loading="eager" src="/donna/b1-1.png" alt="" width={80} height={80} />
      </div>
      <p className="text-body text-ink-2">메뉴 순서를 도나가 대신 바꿔 드려요</p>
      <ul className="mt-5 flex flex-col gap-1">
        {items.map((it) => (
          <li key={it.text} className="flex h-11 items-center gap-3 text-body">
            <Icon name={it.icon} size={24} className="text-brand" />
            {it.text}
          </li>
        ))}
      </ul>
      <div className="mt-3">
        <Note icon="shield">가격과 사진은 건드리지 않아요</Note>
      </div>
      {step === "failed" && (
        <p role="alert" className="mt-4 text-label text-urgent">
          연결하지 못했어요. 인터넷을 확인하고 다시 눌러 주세요.
        </p>
      )}
    </SubPage>
  );
}

export function MenuOrderScreen() {
  const planId = decodeURIComponent(useParams<{ planId: string }>().planId ?? "");
  const router = useRouter();
  const search = useSearchParams();
  const startRevert = search.get("step") === "revert";
  // 검토용 ?view=applying|done|reverted (04-54, 04-55, 04-57)
  const view = search.get("view");
  const viewStep = view === "applying" || view === "done" || view === "reverted" ? view : null;
  const { data, now, prefs: p, mounted } = useHome();
  const applyNow = search.get("apply") === "1";
  const [step, setStep] = useState<"preview" | "applying" | "done" | "reverted">(viewStep ?? (startRevert || applyNow ? "applying" : "preview"));
  const [failed, setFailed] = useState<null | "apply" | "revert">(null);
  const [reverting, setReverting] = useState(startRevert);

  // 05-12n 카드의 "네이버에 바꿔 두기"로 들어오면 미리 보기 없이 바로 바꾼다(실행 시각 전이면 예약).
  useEffect(() => {
    if (!applyNow || !mounted) return;
    if (!p.naverConnected) {
      router.replace(`/naver/connect?plan=${encodeURIComponent(planId)}`);
      return;
    }
    let alive = true;
    applyMenuOrder(planId).then(
      () => {
        if (!alive) return;
        markDone(`APPROVAL_REQUEST:${planId}`);
        setStep("done");
      },
      () => {
        if (!alive) return;
        setFailed("apply");
        setStep("preview");
      },
    );
    return () => {
      alive = false;
    };
  }, [applyNow, mounted, planId, p.naverConnected, router]);

  // 04-56에서 "원래대로 되돌리기"를 누르고 들어오면 바로 되돌린다.
  useEffect(() => {
    if (!startRevert) return;
    let alive = true;
    applyMenuOrder(planId).then(
      () => {
        if (!alive) return;
        prefs.write({ naverAuto: false });
        markDone(`EXECUTE_REMINDER:${planId}`);
        setStep("reverted");
      },
      () => {
        if (!alive) return;
        setFailed("revert");
        setStep("done");
      },
    );
    return () => {
      alive = false;
    };
  }, [startRevert, planId]);

  if (!data) {
    return (
      <SubPage title="메뉴 순서">
        <Bone className="h-64 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const plan = data.plan.plan_items.find((x) => x.plan_id === planId);
  const mo = plan ? menuOrderFor(plan, data.calendar.cells, data.settings.settings.category) : null;
  const tag = mo?.tag ?? null;
  const order = mo?.order ?? storeMenus(data.settings.settings.category);
  const top = order[0];
  const from = mo?.from ?? 1;
  const when = plan ? relativeDay(plan.execute_at ?? plan.target_date, now) : "";
  // 승인(전날 오후)과 실행(당일 출근 후) 시각이 다르면 지금 바꾸지 않고 실행 시각에 바꿔 둔다.
  const scheduled = !!plan?.execute_at && new Date(plan.execute_at).getTime() > now.getTime();
  const at = scheduled && plan?.execute_at ? `${relativeDay(plan.execute_at, now)} ${clockKo(plan.execute_at)}` : "";
  const why =
    tag === "SEASON"
      ? `${when}부터 추워져서 ${withObject(top.name)} 맨 위로`
      : tag === "GAME"
        ? `경기 날이라 ${withObject(top.name)} 맨 위로`
        : tag === "EVENT"
          ? `축제 손님을 위해 ${withObject(top.name)} 맨 위로`
          : "행사가 끝나서 원래 순서로";

  if (step === "applying") {
    return (
      <SubPage>
        <CenterMessage img="b1-1" title={reverting ? (scheduled ? "바꾸지 않게\n돌려 두고 있어요" : "원래대로\n되돌리고 있어요") : scheduled ? "바꿀 시간을\n맞춰 두고 있어요" : "네이버 플레이스에\n바꾸고 있어요"}>
          <div className="mt-6 flex w-48 flex-col gap-2" aria-hidden>
            <Bone className="h-3" />
            <Bone className="h-3 w-40" />
            <Bone className="h-3 w-44" />
          </div>
        </CenterMessage>
      </SubPage>
    );
  }
  if (step === "reverted") {
    return (
      <SubPage footer={<PrimaryButton onClick={() => router.push("/")}>확인했어요</PrimaryButton>}>
        <CenterMessage icon="undo" title={scheduled ? "이번엔\n바꾸지 않을게요" : "원래대로\n되돌렸어요"} sub="다음 알림부터는 다시 여쭤볼게요" />
      </SubPage>
    );
  }
  if (step === "done") {
    return (
      <SubPage
        footer={
          <>
            <div className="mb-2 flex items-center gap-3 border-y border-line py-3">
              <span className="flex-1 text-body">다음부터는 알아서 바꿔 주세요</span>
              <Toggle label="다음부터는 알아서 바꿔 주세요" checked={p.naverAuto} onChange={(v) => prefs.write({ naverAuto: v })} />
            </div>
            <PrimaryButton
              onClick={() => {
                if (scheduled) flashToast(`${at}에 바꿔 둘게요`, "그때 네이버 플레이스에 보여요");
                else flashToast("메뉴 순서를 바꿨어요", "네이버 플레이스에서 바로 보여요");
                router.push("/");
              }}
            >
              확인했어요
            </PrimaryButton>
            <SecondaryButton
              outline
              onClick={async () => {
                setReverting(true);
                setStep("applying");
                setFailed(null);
                try {
                  await applyMenuOrder(planId);
                } catch {
                  setFailed("revert");
                  setStep("done");
                  return;
                }
                prefs.write({ naverAuto: false });
                // 사장님이 되돌렸으니 실행 날의 메뉴판 알림도 보내지 않는다.
                markDone(`EXECUTE_REMINDER:${planId}`);
                setStep("reverted");
              }}
            >
              {scheduled ? "바꾸지 말아 주세요" : "원래대로 되돌리기"}
            </SecondaryButton>
          </>
        }
      >
        {scheduled ? (
          <CenterMessage img="b4-2" title={`${at}에\n바꿔 둘게요`} sub="그때 네이버 플레이스에 보여요" />
        ) : (
          <CenterMessage img="b4-2" title={"메뉴 순서를\n바꿨어요"} sub="네이버 플레이스에서 바로 보여요" />
        )}
        {failed === "revert" && <FailNote title={scheduled ? "취소하지 못했어요" : "되돌리지 못했어요"} />}
      </SubPage>
    );
  }

  const apply = async () => {
    setReverting(false);
    setStep("applying");
    setFailed(null);
    try {
      await applyMenuOrder(planId);
    } catch {
      setFailed("apply");
      setStep("preview");
      return;
    }
    markDone(`APPROVAL_REQUEST:${planId}`);
    setStep("done");
  };

  return (
    <SubPage
      title="메뉴 순서"
      footer={
        <>
          <PrimaryButton onClick={p.naverConnected ? apply : () => router.push(`/naver/connect?plan=${encodeURIComponent(planId)}`)}>
            {p.naverConnected ? "이대로 바꿔 주세요" : "네이버 연결하고 바꾸기"}
          </PrimaryButton>
          <SecondaryButton onClick={() => router.back()}>이번엔 안 할래요</SecondaryButton>
        </>
      }
    >
      <h2 className="text-display">이렇게 바꿀게요</h2>
      <p className="text-body text-ink-2">{why}</p>
      <ol className="mt-4 flex flex-col">
        {order.map((m, i) => (
          <li key={m.name} className={`flex h-14 items-center gap-3 rounded-xl px-3 ${i === 0 && tag ? "bg-brand-soft" : ""}`}>
            <span className="w-5 text-title text-brand">{i + 1}</span>
            <span className="flex-1 text-body">{m.name}</span>
            {i === 0 && tag && from > 1 && (
              <span className="flex items-center gap-1 text-label text-brand">
                <Icon name="arrowUp" size={18} />
                {from}번째에서
              </span>
            )}
          </li>
        ))}
      </ol>
      <div className="mt-3">
        <Note icon="shield">가격과 사진은 그대로예요</Note>
      </div>
      {failed === "apply" && <FailNote title="메뉴 순서를 못 바꿨어요" />}
    </SubPage>
  );
}
