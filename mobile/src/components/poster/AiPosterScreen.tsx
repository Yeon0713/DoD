// AI 포스터 (인스타 스토리 1080 × 1920). 서버를 쓸 때의 포스터 화면이다 (목업일 때는 PosterScreens.tsx 의 그려 만드는 포스터).
// 1) 사진 고르기: 네이버 매장·메뉴 사진(최대 3장) + 로고  2) 어떻게 만들까요: 그날 상황, CLOVA 추천 멘트, 포스터 느낌, 더 넣을 말
// 3) 그리는 중 (30초~2분, 서버가 뒤에서 그린다)  4) 다 된 포스터 → 인스타 스토리에 올리기 / 휴대폰에 저장 / 다시 만들기
// 그림은 서버가 ChatGPT 그림 모델(지금은 Codex 의 gpt-image-2, 구독제)로 만든다. 설명: docs/poster-ai.md
import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { useLocalSearchParams } from "expo-router";
import { useRef, useState, type ComponentRef } from "react";
import { Image, Platform, Pressable, TextInput, useWindowDimensions, View } from "react-native";
import { Icon } from "@/components/icons/Icon";
import { NAVER_PLACE_KEY, param } from "@/components/start/flow";
import { goHome } from "@/components/ui/nav";
import { PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { CenterMessage, FailNote, Note, SubPage } from "@/components/ui/sub";
import { Text } from "@/components/ui/Text";
import { account } from "@/lib/account";
import { api, ApiFailure, placeImage, type PosterJob, type PosterMent } from "@/lib/api";
import { markDone, markPlanDone } from "@/lib/cardState";
import { drafts, flashToast } from "@/lib/localStore";
import { readKept, type KeptPoster } from "@/lib/poster";
import { clockKo, relativeDay } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";
import { sendWeb } from "./PosterScreens";
import { PosterMaking } from "./PosterMaking";
import { shareView } from "./shareView";

const C = tokens.colors;
const MAX_PHOTOS = 3;
type Step = "pick" | "how" | "making" | "preview" | "sent";
type Choice = { key: string; label: string; url: string; kind: "store" | "menu" | "phone" };

export function AiPosterScreen() {
  const params = useLocalSearchParams<{ planId: string; step?: string }>();
  const planId = decodeURIComponent(param(params.planId) ?? "");
  const shareFirst = param(params.step) === "share";
  const draftKey = `poster:${planId}`;
  const jobKey = `poster-job:${planId}`;
  const [kept] = useState<KeptPoster | null>(() => readKept(drafts.read(), draftKey));
  // 만들던 그림이 있으면(다른 화면에 다녀왔을 때) 이어서 기다린다
  const [jobId, setJobId] = useState<string | null>(() => (shareFirst ? (kept?.jobId ?? null) : (drafts.read()[jobKey] ?? null)));
  const [stepState, setStep] = useState<Step>(() => (shareFirst && kept?.jobId ? "preview" : jobId ? "making" : "pick"));
  const [picked, setPicked] = useState<string[] | null>(null); // null: 아직 안 골랐다 (첫 메뉴 사진을 골라 둔 것으로 본다)
  const [phone, setPhone] = useState<Choice[]>([]);
  const [useLogo, setUseLogo] = useState(true);
  const [mentIdx, setMentIdx] = useState(0);
  const [ownHead, setOwnHead] = useState("");
  const [ownLine, setOwnLine] = useState("");
  const [style, setStyle] = useState("PHOTO");
  const [extra, setExtra] = useState("");
  const [startFailed, setStartFailed] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [sending, setSending] = useState(false);
  const [logoBusy, setLogoBusy] = useState(false);
  const [logoFailed, setLogoFailed] = useState<string | null>(null);
  const [sendFailed, setSendFailed] = useState(false);
  const [sentKind, setSentKind] = useState<"shared" | "saved">("shared");
  const shot = useRef<ComponentRef<typeof View> | null>(null);
  const qc = useQueryClient();
  const { width: screenW } = useWindowDimensions();
  const { data, now } = useHome();
  const storeId = account.useValue().storeId;

  const place = useQuery({ queryKey: NAVER_PLACE_KEY, queryFn: api.naverPlace, staleTime: 5 * 60 * 1000 }).data?.place;
  // CLOVA 멘트는 몇 초 걸려서 사진을 고르는 동안 미리 받는다
  const suggest = useQuery({ queryKey: ["poster-suggest", planId, storeId], queryFn: () => api.posterSuggest(planId), staleTime: 10 * 60 * 1000, retry: 1 });
  const job = useQuery({
    queryKey: ["poster-job", jobId],
    queryFn: async () => {
      const j = await api.posterJob(jobId!);
      if (j.status !== "RUNNING") drafts.write({ [jobKey]: "" }); // 다 됐으면 "만들던 그림" 표시를 지운다
      return j;
    },
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data?.status === "RUNNING" || !q.state.data ? 3000 : false),
  });

  // 그리는 중에 다 되면 바로 미리 보기로
  const step: Step = stepState === "making" && job.data?.status === "DONE" ? "preview" : stepState;
  const plan = data?.plan.plan_items.find((x) => x.plan_id === planId);
  // 사장님이 올린 사진이 맨 앞, 그다음 네이버 매장 사진·메뉴 사진
  const choices: Choice[] = [
    ...phone,
    ...(place?.store_photos ?? []).map((url, i) => ({ key: `store-${i}`, label: i === 0 && url === place?.profile_photo ? "대표 사진" : "매장 사진", url, kind: "store" as const })),
    ...(place?.menus ?? []).filter((m) => m.photo).map((m, i) => ({ key: `menu-${i}`, label: m.name, url: m.photo!, kind: "menu" as const })),
  ];
  // 처음에는 첫 메뉴 사진을 골라 둔다
  const chosen = picked ?? choices.filter((c) => c.kind === "menu").slice(0, 1).map((c) => c.key);
  const logo = placeImage(place?.logo);
  const sg = suggest.data;
  const ments: PosterMent[] = sg?.ments ?? [];
  const own = mentIdx === ments.length;
  const ment = own ? null : ments[mentIdx];
  const headline = own ? ownHead.trim() : (ment?.headline ?? "");
  const line = own ? ownLine.trim() : (ment?.line ?? "");

  const toggle = (key: string) => {
    const now_ = chosen.includes(key) ? chosen.filter((k) => k !== key) : chosen.length >= MAX_PHOTOS ? chosen : [...chosen, key];
    setPicked(now_);
  };

  const pickPhone = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.8, base64: true });
    const a = !res.canceled ? res.assets[0] : undefined;
    if (!a?.base64) return;
    const c: Choice = { key: `phone-${Date.now()}`, label: "올린 사진", url: `data:${a.mimeType ?? "image/jpeg"};base64,${a.base64}`, kind: "phone" };
    setPhone((p) => [c, ...p]);
    setPicked([...chosen.slice(0, MAX_PHOTOS - 1), c.key]);
  };

  // 로고 올리기·바꾸기: 서버가 바탕을 지우고 여백을 잘라 둔다 (사장님이 올린 로고가 네이버에서 찾은 로고보다 앞선다)
  const uploadLogo = async () => {
    if (!storeId) return;
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.9, base64: true });
    const a = !res.canceled ? res.assets[0] : undefined;
    if (!a?.base64) return;
    setLogoBusy(true);
    setLogoFailed(null);
    try {
      await api.uploadLogo(storeId, `data:${a.mimeType ?? "image/png"};base64,${a.base64}`);
      await qc.invalidateQueries({ queryKey: NAVER_PLACE_KEY });
      setUseLogo(true);
      flashToast("로고를 올렸어요", "배경을 지워 포스터에 넣을게요");
    } catch (e) {
      setLogoFailed(e instanceof ApiFailure ? e.message : "로고를 올리지 못했어요");
    } finally {
      setLogoBusy(false);
    }
  };

  const start = async () => {
    setStarting(true);
    setStartFailed(null);
    try {
      const photos = chosen.map((k) => choices.find((c) => c.key === k)).filter((c): c is Choice => !!c).map((c) => ({ label: c.kind === "menu" ? c.label : c.kind === "store" ? "매장 사진" : "가게 사진", url: c.url }));
      const j = await api.startPoster({ plan_id: planId, photos, use_logo: useLogo && !!logo, headline, line, extra: extra.trim(), style, menu: ment?.menu ?? "" });
      drafts.write({ [jobKey]: j.job_id });
      qc.setQueryData(["poster-job", j.job_id], j);
      setJobId(j.job_id);
      setStep("making");
    } catch (e) {
      setStartFailed(e instanceof ApiFailure ? e.message : "잠시 뒤 다시 해 주세요");
    } finally {
      setStarting(false);
    }
  };

  // 승인 알림(전날)에서 들어왔으면 지금 올리지 않고 만들어 둔다. 실행 알림에서 "인스타에 올리기"로 보낸다.
  const execAt = plan?.execute_at ?? null;
  const scheduled = !shareFirst && !!execAt && new Date(execAt).getTime() > now.getTime();
  const done = job.data?.status === "DONE" ? job.data : null;
  const image = placeImage(done?.image ?? kept?.image);

  const keep = (j: PosterJob) => {
    drafts.write({ [draftKey]: JSON.stringify({ menuIdx: 0, headline: j.headline, storeLine: null, theme: "dark", jobId: j.job_id, image: j.image ?? undefined } satisfies KeptPoster) });
    markDone(`APPROVAL_REQUEST:${planId}`, { note: "포스터를 만들어 뒀어요" });
    if (execAt) flashToast("포스터를 만들어 뒀어요", `${relativeDay(execAt, now)} ${clockKo(execAt)}에 올리라고 알려 드릴게요`);
    goHome();
  };

  const send = async (dest: "story" | "save") => {
    if (!image) return;
    setSending(true);
    setSendFailed(false);
    try {
      let kind: "shared" | "saved" | null;
      if (Platform.OS === "web") {
        const blob = await (await fetch(image)).blob();
        kind = await sendWeb(blob, dest, headline || "포스터");
      } else {
        await shareView(shot.current, "포스터", { width: 1080, height: 1920 });
        kind = dest === "save" ? "saved" : "shared";
      }
      if (!kind) return;
      setSentKind(kind);
      setStep("sent");
    } catch {
      setSendFailed(true);
    } finally {
      setSending(false);
    }
  };

  if (step === "sent") {
    return (
      <SubPage
        footer={
          <PrimaryButton
            onPress={() => {
              markPlanDone(planId, { note: "포스터를 올렸어요" });
              goHome();
            }}
          >
            확인했어요
          </PrimaryButton>
        }
      >
        {sentKind === "shared" ? (
          <CenterMessage img="b4-2" title={"인스타그램으로\n보냈어요"} sub={"스토리에 올리기를 누르면\n올라가요"} />
        ) : (
          <CenterMessage img="b4-2" title={"휴대폰에\n저장했어요"} sub={"인스타그램 스토리에서 사진을 골라\n직접 올려 주세요"} />
        )}
      </SubPage>
    );
  }

  if (step === "making") {
    const j = job.data;
    const failed = j?.status === "FAILED";
    return (
      <SubPage
        title="포스터 만들기"
        footer={
          failed ? (
            <>
              <PrimaryButton onPress={() => void start()} disabled={starting}>
                {starting ? "다시 시작하는 중" : "다시 그려 볼게요"}
              </PrimaryButton>
              <SecondaryButton
                onPress={() => {
                  drafts.write({ [jobKey]: "" });
                  setJobId(null);
                  setStep("how");
                }}
              >
                문구 다시 고르기
              </SecondaryButton>
            </>
          ) : (
            <SecondaryButton testID="poster-wait-home" onPress={goHome}>
              홈에서 기다릴게요
            </SecondaryButton>
          )
        }
      >
        {failed ? (
          <>
            <CenterMessage img="b2-0" title={"포스터를\n못 그렸어요"} sub={j?.fail_reason ?? "다시 해 주세요"} />
            {startFailed ? <FailNote title="다시 시작하지 못했어요" sub={startFailed} icon="refresh" /> : null}
          </>
        ) : (
          <PosterMaking key={jobId ?? "none"} seconds={j?.seconds ?? 0} headline={j?.headline ?? headline} />
        )}
      </SubPage>
    );
  }

  if (step === "preview") {
    const w = Math.min(screenW - 48, 300);
    return (
      <SubPage
        title="포스터 미리 보기"
        footer={
          <>
            {scheduled && done ? (
              <PrimaryButton testID="poster-keep" onPress={() => keep(done)}>
                이대로 만들어 두기
              </PrimaryButton>
            ) : (
              <PrimaryButton testID="poster-send" onPress={() => void send("story")} disabled={sending || !image}>
                {sending ? "보내는 중" : "인스타 스토리에 올리기"}
              </PrimaryButton>
            )}
            <SecondaryButton
              testID="poster-again"
              onPress={() => {
                setJobId(null);
                setStep("how");
              }}
            >
              다시 만들기
            </SecondaryButton>
          </>
        }
      >
        <View className="items-center">
          <View ref={shot} collapsable={false} className="overflow-hidden rounded-2xl border border-line" style={{ width: w, height: (w * 16) / 9 }}>
            {image ? <Image testID="poster-image" source={{ uri: image }} style={{ width: "100%", height: "100%" }} resizeMode="cover" accessibilityLabel={`포스터: ${headline}`} /> : null}
          </View>
          {!scheduled ? (
            <Pressable testID="poster-save" accessibilityRole="button" onPress={() => void send("save")} hitSlop={8} className="mt-3">
              <Text className="text-label font-bold text-brand underline">휴대폰에 저장하기</Text>
            </Pressable>
          ) : null}
          {sendFailed ? (
            <Text accessibilityRole="alert" className="mt-3 text-label text-urgent">
              보내지 못했어요. 다시 눌러 주세요.
            </Text>
          ) : null}
        </View>
      </SubPage>
    );
  }

  if (step === "how") {
    const kind = sg?.situation.kind;
    const extraHint = kind === "GAME" ? "예: 응원하는 팀을 리뷰에 남겨 주시면 쿠폰을 문자로 보내 드려요" : kind === "EVENT" ? "예: 축제 손목띠를 보여 주시면 음료를 드려요" : "예: 평일 오전 10시 30분부터 열어요";
    const ready = !!headline && sg?.engine.ready !== false;
    return (
      <SubPage
        title="포스터 만들기"
        onBack={() => setStep("pick")}
        footer={
          <>
            {startFailed ? (
              <Text accessibilityRole="alert" className="text-center text-label text-urgent">{`포스터를 시작하지 못했어요. ${startFailed}`}</Text>
            ) : null}
            <PrimaryButton testID="poster-make" onPress={() => void start()} disabled={!ready || starting}>
              {starting ? "시작하는 중" : "이대로 그려 주세요"}
            </PrimaryButton>
          </>
        }
      >
        <Text className="text-display text-ink" accessibilityRole="header">
          어떤 포스터를 만들까요?
        </Text>
        {sg ? (
          <View testID="poster-situation" className="mt-3 gap-1 rounded-2xl bg-brand-soft px-4 py-3">
            {sg.situation.lines.map((l) => (
              <Text key={l} className="text-body text-ink">
                {l}
              </Text>
            ))}
          </View>
        ) : null}

        <Text className="mt-5 text-body font-bold text-ink">{sg?.ment_source === "BASIC" ? "이런 문구는 어떠세요?" : "도나가 고른 문구"}</Text>
        {suggest.isLoading ? <Text className="mt-2 text-small text-ink-2">상황에 맞는 문구를 고르고 있어요</Text> : null}
        {suggest.error ? <FailNote title="문구를 못 받았어요" sub="직접 써 주시거나 잠시 뒤 다시 들어와 주세요" icon="refresh" /> : null}
        <View className="mt-2 gap-2" accessibilityRole="radiogroup" accessibilityLabel="포스터 문구">
          {ments.map((m, i) => (
            <Pressable
              key={`${m.kind}-${i}`}
              testID={`poster-ment-${i}`}
              accessibilityRole="radio"
              accessibilityState={{ checked: mentIdx === i }}
              onPress={() => setMentIdx(i)}
              className={`gap-1 rounded-2xl border px-4 py-3 ${mentIdx === i ? "border-2 border-brand bg-brand-soft" : "border-line bg-surface"}`}
            >
              <Text className="text-small font-bold text-brand">{m.label}</Text>
              <Text className="text-body font-bold text-ink">{m.headline.replace(/\n/g, " ")}</Text>
              <Text className="text-small text-ink-2">{m.line}</Text>
            </Pressable>
          ))}
          <Pressable
            testID="poster-ment-own"
            accessibilityRole="radio"
            accessibilityState={{ checked: own }}
            onPress={() => setMentIdx(ments.length)}
            className={`gap-2 rounded-2xl border px-4 py-3 ${own ? "border-2 border-brand bg-brand-soft" : "border-line bg-surface"}`}
          >
            <Text className="text-body font-bold text-ink">직접 쓸게요</Text>
            {own ? (
              <>
                <TextInput testID="poster-own-head" accessibilityLabel="큰 글자" value={ownHead} onChangeText={setOwnHead} maxLength={30} placeholder="큰 글자 (예: 축제 가는 길에)" placeholderTextColor={C["ink-3"]} className="h-12 rounded-xl border border-line bg-surface px-3 text-body text-ink" />
                <TextInput testID="poster-own-line" accessibilityLabel="작은 글자" value={ownLine} onChangeText={setOwnLine} maxLength={60} placeholder="작은 글자 (예: 따뜻한 옹심이 한 그릇 하고 가세요)" placeholderTextColor={C["ink-3"]} className="h-12 rounded-xl border border-line bg-surface px-3 text-body text-ink" />
              </>
            ) : null}
          </Pressable>
        </View>

        <Text className="mt-5 text-body font-bold text-ink">포스터 느낌</Text>
        <View className="mt-2 flex-row flex-wrap gap-2" accessibilityRole="radiogroup" accessibilityLabel="포스터 느낌">
          {(sg?.styles ?? []).map((o) => (
            <Pressable key={o.key} testID={`poster-style-${o.key}`} accessibilityRole="radio" accessibilityState={{ checked: style === o.key }} onPress={() => setStyle(o.key)} className={`h-11 items-center justify-center rounded-full border px-4 ${style === o.key ? "border-brand bg-brand" : "border-line bg-surface"}`}>
              <Text className={`text-label font-bold ${style === o.key ? "text-brand-ink" : "text-ink-2"}`}>{o.label}</Text>
            </Pressable>
          ))}
        </View>

        <Text className="mt-5 text-body font-bold text-ink">더 넣고 싶은 말 (없어도 돼요)</Text>
        <TextInput testID="poster-extra" accessibilityLabel="더 넣고 싶은 말" value={extra} onChangeText={setExtra} maxLength={60} multiline placeholder={extraHint} placeholderTextColor={C["ink-3"]} className="mt-2 min-h-[56px] rounded-xl border border-line bg-surface px-3 py-3 text-body text-ink" />
        <View className="mt-3">
          <Note icon="store">{`가게 이름과 주소는 늘 넣어요${useLogo && logo ? ", 로고도 넣어요" : ""}`}</Note>
        </View>
        {sg && !sg.engine.ready ? <FailNote title="지금은 그림을 그릴 수 없어요" sub={sg.engine.note} icon="refresh" /> : null}
      </SubPage>
    );
  }

  // 1) 사진 고르기
  return (
    <SubPage
      title="포스터 만들기"
      footer={
        <>
          <PrimaryButton testID="poster-next" onPress={() => setStep("how")} disabled={chosen.length === 0}>
            {`사진 ${chosen.length}장으로 다음`}
          </PrimaryButton>
        </>
      }
    >
      <Text className="text-display text-ink" accessibilityRole="header">
        어떤 사진을 넣을까요?
      </Text>
      {/* 가게 로고 (맨 위): 줄을 누르면 넣을지 켜고 끄고, 로고 그림을 누르면 바꾼다 (마우스를 올리거나 누르면 바꾸기 표시) */}
      <View className={`mt-4 flex-row items-center gap-3 rounded-2xl border p-3.5 ${logo && useLogo ? "border-brand bg-brand-soft" : "border-line bg-surface"}`}>
        <LogoPicker logo={logo} busy={logoBusy} onPick={() => void uploadLogo()} />
        <Pressable
          testID="poster-logo-toggle"
          accessibilityRole="checkbox"
          accessibilityState={{ checked: !!logo && useLogo, disabled: !logo }}
          onPress={() => (logo ? setUseLogo(!useLogo) : void uploadLogo())}
          className="flex-1 flex-row items-center gap-3"
        >
          <Text className="flex-1 text-body font-bold text-ink">{logoBusy ? "로고를 올리는 중" : logo ? "가게 로고 넣기" : "가게 로고 올리기"}</Text>
          {logo ? <View className={`h-7 w-7 items-center justify-center rounded-full ${useLogo ? "bg-brand" : "border-2 border-line"}`}>{useLogo ? <Icon name="check" size={16} color={C["brand-ink"]} /> : null}</View> : null}
        </Pressable>
      </View>
      {logoFailed ? <FailNote title="로고를 올리지 못했어요" sub={logoFailed} icon="refresh" /> : null}
      <View className="mt-4">
        <Note icon="image">{`${MAX_PHOTOS}장까지 고를 수 있어요`}</Note>
      </View>
      <View className="mt-2.5 flex-row flex-wrap justify-between gap-y-3" accessibilityLabel="포스터 사진">
        {/* 맨 위 한 줄: 사장님이 직접 사진 올리기 */}
        <Pressable testID="poster-pick-photo" accessibilityRole="button" accessibilityLabel="사진 올리기" onPress={() => void pickPhone()} className="h-[72px] w-full flex-row items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-brand bg-surface active:bg-brand-soft">
          <Text className="text-display font-bold text-brand">+</Text>
          <Text className="text-body font-bold text-brand">사진 올리기</Text>
        </Pressable>
        {choices.slice(0, 12 + phone.length).map((c, i) => {
          const on = chosen.includes(c.key);
          return (
            <Pressable key={c.key} testID={`poster-photo-${i}`} accessibilityRole="checkbox" accessibilityState={{ checked: on }} accessibilityLabel={c.label} onPress={() => toggle(c.key)} className="gap-1.5" style={{ width: "48%" }}>
              <View className={`h-[100px] w-full overflow-hidden rounded-2xl bg-brand-soft ${on ? "border-[3px] border-brand" : ""}`}>
                <Image source={{ uri: placeImage(c.url) ?? c.url }} style={{ width: "100%", height: "100%" }} resizeMode="cover" accessibilityLabel={c.label} />
                {on ? (
                  <View className="absolute right-1.5 top-1.5 h-7 w-7 items-center justify-center rounded-full bg-brand">
                    <Text className="text-label font-bold text-brand-ink">{chosen.indexOf(c.key) + 1}</Text>
                  </View>
                ) : null}
              </View>
              <Text className="text-body text-ink" numberOfLines={1}>
                {c.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </SubPage>
  );
}

/** 로고 그림: 누르면 휴대폰에서 로고를 골라 바꾼다. 마우스를 올리거나 누르고 있으면 바꾸기(연필) 표시가 뜬다 */
function LogoPicker({ logo, busy, onPick }: { logo?: string; busy: boolean; onPick: () => void }) {
  const [hover, setHover] = useState(false);
  return (
    <Pressable
      testID="poster-logo-upload"
      accessibilityRole="button"
      accessibilityLabel={logo ? "로고 바꾸기" : "로고 올리기"}
      disabled={busy}
      onPress={onPick}
      onHoverIn={() => setHover(true)}
      onHoverOut={() => setHover(false)}
      className="h-14 w-14 items-center justify-center overflow-hidden rounded-xl bg-paper"
    >
      {({ pressed }) => (
        <>
          {logo ? <Image source={{ uri: logo }} style={{ width: 52, height: 52 }} resizeMode="contain" accessibilityLabel="가게 로고" /> : <Icon name="store" size={26} color={C["ink-3"]} />}
          {hover || pressed || !logo ? (
            <View className={`absolute inset-0 items-center justify-center ${logo ? "bg-ink/45" : ""}`}>
              <View className={`h-7 w-7 items-center justify-center rounded-full ${logo ? "bg-surface" : "bg-brand"}`}>
                <Icon name="pencil" size={15} color={logo ? C.brand : C["brand-ink"]} />
              </View>
            </View>
          ) : null}
        </>
      )}
    </Pressable>
  );
}
