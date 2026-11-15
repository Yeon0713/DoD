// 인스타 포스터 (Figma 06-61 사진 고르기, 06-62 만드는 중, 06-63 미리 보기, 06-63s 만들어 뒀어요 띠, 06-64 글자 고치기,
// 06-65 올릴 곳 고르기, 06-66 보냈어요). 그림은 네이버 플레이스에서 불러온 매장 사진·메뉴 사진 중에서 고르고, 휴대폰 사진도 고를 수 있다.
// 포스터 아래에는 가게 이름과 주소를 넣고, 로고가 있으면(네이버 플레이스 또는 사장님이 여기서 올린 로고) 모서리에 넣는다.
// 그림 파일: 앱은 미리 보기 포스터를 그대로 찍어(react-native-view-shot) 공유 창을 띄우고, 웹은 캔버스에 다시 그려 공유하거나 내려받는다.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { useLocalSearchParams } from "expo-router";
import { useRef, useState, type ComponentRef } from "react";
import { Image, Platform, Pressable, ScrollView, TextInput, useWindowDimensions, View } from "react-native";
import { Text } from "@/components/ui/Text";
import { Icon, type IconName } from "@/components/icons/Icon";
import { NAVER_PLACE_KEY, param, storeName } from "@/components/start/flow";
import { goHome } from "@/components/ui/nav";
import { DONNA_IMG } from "@/components/ui/donna";
import { Bone, DonnaImage, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Sheet, useSheetClose } from "@/components/ui/Sheet";
import { CenterMessage, FailNote, Note, SubPage } from "@/components/ui/sub";
import { makePoster } from "@/lib/actions";
import { account } from "@/lib/account";
import { api, placeImage, USE_MOCK } from "@/lib/api";
import { happening } from "@/lib/cards";
import { markDone, markPlanDone } from "@/lib/cardState";
import { drafts, flashToast } from "@/lib/localStore";
import { defaultHeadline, LOGO_CHIP, readKept, THEME_STYLE, THEMES, type KeptPoster, type Theme } from "@/lib/poster";
import { clockKo, relativeDay } from "@/lib/time";
import { useHome } from "@/lib/useHome";
import { storeMenus } from "@/mocks/extras";
import tokens from "@/theme/tokens.json";
import { POSTER_W, PosterCard } from "./PosterCard";
import { shareView } from "./shareView";

const C = tokens.colors;
type Step = "pick" | "making" | "preview" | "edit" | "sent";
type Dest = "story" | "feed" | "save";
const GAP = 12;
const PAGE = POSTER_W + GAP;

/** require()로 불러온 그림의 주소 (웹 캔버스용) */
function assetUri(mod: unknown): string | null {
  if (typeof mod === "string") return mod;
  if (mod && typeof mod === "object" && "uri" in mod) return String((mod as { uri: unknown }).uri);
  if (typeof mod === "number") return Image.resolveAssetSource?.(mod)?.uri ?? null;
  return null;
}

/** 웹: 포스터를 1080 × 1350 그림 파일로 그린다 (인스타 게시물 4:5). */
async function renderPosterWeb(o: { photo?: string; menu: string; dateLine: string; headline: string; store: string; theme: Theme; logo?: string; address?: string }): Promise<Blob> {
  const W = 1080;
  const H = 1350;
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const g = c.getContext("2d")!;
  const font = (w: 500 | 700) => (w === 700 ? `${tokens.fonts.bold}, sans-serif` : `${tokens.fonts.medium}, sans-serif`);
  const t = THEME_STYLE[o.theme];
  const load = (src: string) =>
    new Promise<HTMLImageElement>((res, rej) => {
      const im = new window.Image();
      im.crossOrigin = "anonymous";
      im.onload = () => res(im);
      im.onerror = rej;
      im.src = src;
    });
  const photoH = 810;
  g.fillStyle = C["brand-soft"];
  g.fillRect(0, 0, W, photoH);
  if (o.photo) {
    const im = await load(o.photo);
    const sc = Math.max(W / im.width, photoH / im.height);
    g.drawImage(im, (W - im.width * sc) / 2, (photoH - im.height * sc) / 2, im.width * sc, im.height * sc);
  } else {
    g.fillStyle = C["ink-2"];
    g.font = `500 48px ${font(500)}`;
    g.textAlign = "center";
    g.fillText(`${o.menu} 사진`, W / 2, photoH / 2);
  }
  g.fillStyle = t.canvasBg;
  g.fillRect(0, photoH, W, H - photoH);
  g.textAlign = "left";
  g.fillStyle = t.canvasSub;
  g.font = `500 40px ${font(500)}`;
  g.fillText(o.dateLine, 64, photoH + 96);
  g.fillStyle = t.canvasText;
  g.font = `700 76px ${font(700)}`;
  o.headline.split("\n").forEach((line, i) => g.fillText(line, 64, photoH + 210 + i * 100));
  g.fillStyle = t.canvasSub;
  g.font = `700 40px ${font(700)}`;
  g.fillText(o.store, 64, o.address ? H - 112 : H - 64);
  if (o.address) {
    g.font = `500 30px ${font(500)}`;
    g.fillText(o.address, 64, H - 64, W - 380);
  }
  try {
    // 로고가 있으면 로고(바탕을 지운 그림. 어두운 띠에는 밝은 둥근 판 위에), 없으면 도나
    if (o.logo) {
      const im = await load(o.logo);
      const chip = LOGO_CHIP[o.theme];
      if (chip) {
        g.fillStyle = chip;
        g.beginPath();
        g.roundRect(W - 296, H - 296, 232, 232, 36);
        g.fill();
      }
      const sc = Math.min(196 / im.width, 196 / im.height);
      g.drawImage(im, W - 180 - (im.width * sc) / 2, H - 180 - (im.height * sc) / 2, im.width * sc, im.height * sc);
    } else {
      const src = assetUri(DONNA_IMG["b3-0"]);
      if (src) g.drawImage(await load(src), W - 300, H - 300, 240, 240);
    }
  } catch {
    /* 그림이 없어도 포스터는 만든다 */
  }
  return new Promise((res) => c.toBlob((b) => res(b!), "image/png"));
}

/** 웹: 공유할 수 있으면 공유 창, 아니면 내려받기. 사장님이 공유 창을 닫으면 null */
export async function sendWeb(blob: Blob, dest: Dest, title: string): Promise<"shared" | "saved" | null> {
  const f = new File([blob], "dona-poster.png", { type: "image/png" });
  if (dest !== "save" && navigator.canShare?.({ files: [f] })) {
    try {
      await navigator.share({ files: [f], title });
      return "shared";
    } catch {
      return null;
    }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "dona-poster.png";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  return "saved";
}

export function PosterScreen() {
  const params = useLocalSearchParams<{ planId: string; step?: string }>();
  const planId = decodeURIComponent(param(params.planId) ?? "");
  // ?step=share(오늘 화면 포스터 카드, 실행 알림에서), 검토용 ?step=making|preview|edit|sent
  const stepParam = param(params.step);
  const shareFirst = stepParam === "share";
  const initialStep: Step = shareFirst ? "preview" : stepParam === "making" || stepParam === "preview" || stepParam === "edit" || stepParam === "sent" ? stepParam : "pick";
  const { data, now } = useHome();
  const { width: screenW } = useWindowDimensions();
  // 승인 날 만들어 둔 포스터(메뉴, 글자, 색)를 실행 날 그대로 올리려고 이 기기에 저장해 둔다. 서버 PATCH /api/posters가 생기면 옮긴다.
  const draftKey = `poster:${planId}`;
  const [kept] = useState<KeptPoster | null>(() => readKept(drafts.read(), draftKey));
  const [step, setStep] = useState<Step>(initialStep);
  const [menuIdx, setMenuIdx] = useState(kept?.menuIdx ?? 0);
  const [photo, setPhoto] = useState<string | undefined>();
  const [headline, setHeadline] = useState<string | null>(kept?.headline ?? null);
  const [storeLine, setStoreLine] = useState<string | null>(kept?.storeLine ?? null);
  const [sheet, setSheet] = useState(shareFirst);
  const [dest, setDest] = useState<Dest>("story");
  const [theme, setTheme] = useState<Theme>(kept?.theme ?? "dark");
  const [sentKind, setSentKind] = useState<"shared" | "saved">("shared");
  const [failed, setFailed] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendFailed, setSendFailed] = useState(false);
  const [logoBusy, setLogoBusy] = useState(false);
  const [logoFailed, setLogoFailed] = useState<string | null>(null);
  const qc = useQueryClient();
  const storeId = account.useValue().storeId;
  // 네이버 플레이스에서 불러온 매장 사진, 메뉴 사진, 로고, 주소
  const place = useQuery({ queryKey: NAVER_PLACE_KEY, queryFn: api.naverPlace, enabled: !USE_MOCK, staleTime: 5 * 60 * 1000 }).data?.place;
  const shots = useRef<(ComponentRef<typeof View> | null)[]>([]);
  const scroller = useRef<ComponentRef<typeof ScrollView>>(null);
  const placed = useRef(false);
  const sheetClose = useSheetClose();

  if (!data) {
    return (
      <SubPage title="포스터">
        <Bone className="h-80 w-full rounded-2xl" />
      </SubPage>
    );
  }
  const s = data.settings.settings;
  const plan = data.plan.plan_items.find((x) => x.plan_id === planId);
  const h = plan ? happening(data.calendar.cells, plan) : null;
  // 고를 사진: 매장 사진(대표 사진이 앞) → 사진이 있는 메뉴. 네이버 사진이 없으면(목업) 메뉴 이름만
  const choices: { key: string; label: string; menu: string; photo?: string; kind: "store" | "menu" }[] = [
    ...(place?.store_photos ?? []).map((url, i) => ({ key: `store-${i}`, label: i === 0 && url === place?.profile_photo ? "대표 사진" : "매장 사진", menu: storeName(s.name), photo: placeImage(url), kind: "store" as const })),
    ...(place?.menus ?? []).filter((m) => m.photo).map((m, i) => ({ key: `menu-${i}`, label: m.name, menu: m.name, photo: placeImage(m.photo), kind: "menu" as const })),
  ];
  if (choices.length === 0) storeMenus(s.category).forEach((m, i) => choices.push({ key: `mock-${i}`, label: m.name, menu: m.name, kind: "menu" }));
  const choice = choices[menuIdx] ?? choices[0];
  const menu = choice?.menu ?? storeName(s.name);
  const store = storeLine ?? storeName(s.name);
  const head = headline ?? defaultHeadline(h, s);
  const logo = placeImage(place?.logo);
  const address = place?.address || undefined;
  // 포스터 날짜 줄은 한 줄에 들어가게 줄여 쓴다. 예: "11월 21일, 22일 주말"
  const poster = { photo: photo ?? choice?.photo, menu, dateLine: h?.shortLine ?? "", icon: (h?.icon ?? "image") as IconName, headline: head, store, logo, address };

  // 로고 올리기: 휴대폰 사진에서 골라 서버에 둔다. 서버가 바탕을 지우고 여백을 잘라 둔다 (그래서 네모로 자르게 하지 않는다)
  const uploadLogo = async () => {
    if (!storeId || USE_MOCK) return;
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.9, base64: true });
    const asset = !res.canceled ? res.assets[0] : undefined;
    if (!asset?.base64) return;
    setLogoBusy(true);
    setLogoFailed(null);
    try {
      await api.uploadLogo(storeId, `data:${asset.mimeType ?? "image/png"};base64,${asset.base64}`);
      await qc.invalidateQueries({ queryKey: NAVER_PLACE_KEY });
      flashToast("로고를 올렸어요", "배경을 지워 포스터 모서리에 넣을게요");
    } catch (e) {
      setLogoFailed(e instanceof Error ? e.message : "로고를 올리지 못했어요");
    } finally {
      setLogoBusy(false);
    }
  };

  // 승인 알림(전날)에서 들어왔으면 지금 올리지 않고 만들어 둔다. 실행 알림에서 "포스터 올리기"로 보낸다.
  const execAt = plan?.execute_at ?? null;
  const scheduled = !shareFirst && !!execAt && new Date(execAt).getTime() > now.getTime();
  const keep = () => {
    drafts.write({ [draftKey]: JSON.stringify({ menuIdx, headline, storeLine, theme } satisfies KeptPoster) });
    markDone(`APPROVAL_REQUEST:${planId}`, { note: "포스터를 만들어 뒀어요" });
    // 06-63s 띠
    if (execAt) flashToast("포스터를 만들어 뒀어요", `${relativeDay(execAt, now)} ${clockKo(execAt)}에 올리라고 알려 드릴게요`);
    goHome();
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

  const pickPhoto = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.9 });
    const uri = !res.canceled ? res.assets[0]?.uri : undefined;
    if (uri) {
      setPhoto(uri);
      make();
    }
  };

  const send = async () => {
    setSending(true);
    setSendFailed(false);
    if (Platform.OS !== "web") {
      // 시트를 먼저 다 닫고 공유 창을 띄운다 (열린 시트 위에 띄우면 iOS에서 앱이 멈춘다).
      setSheet(false);
      await sheetClose.closed();
    }
    try {
      let kind: "shared" | "saved" | null;
      if (Platform.OS === "web") {
        kind = await sendWeb(await renderPosterWeb({ ...poster, theme }), dest, head.replace(/\n/g, " "));
      } else {
        // 앱: 지금 보이는 색의 포스터를 그대로 찍어 공유 창을 띄운다. "휴대폰에 저장"도 공유 창의 "이미지 저장"으로 한다.
        await shareView(shots.current[THEMES.indexOf(theme)] ?? null, head.replace(/\n/g, " "));
        kind = dest === "save" ? "saved" : "shared";
      }
      if (!kind) return; // 사장님이 공유 창을 닫았다
      setSentKind(kind);
      setSheet(false);
      setStep("sent");
    } catch {
      setSendFailed(true);
      setSheet(true);
    } finally {
      setSending(false);
    }
  };

  if (step === "making") {
    return (
      <SubPage>
        <View className="flex-row items-center gap-3" accessibilityRole="progressbar" accessibilityLabel="포스터를 만들고 있어요">
          <DonnaImage img="b3-2" size={72} />
          <Text className="text-title text-ink">{"포스터를\n만들고 있어요"}</Text>
        </View>
        <View className="mt-4 overflow-hidden rounded-2xl border border-line bg-surface" accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          <Bone className="h-56 w-full rounded-none" />
          <View className="gap-2 p-4">
            <Bone className="h-3.5 w-40" />
            <Bone className="h-3.5 w-32" />
            <Bone className="h-3.5 w-20" />
          </View>
        </View>
      </SubPage>
    );
  }

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
          <CenterMessage img="b4-2" title={"인스타그램으로\n보냈어요"} sub={"인스타그램에서 공유를 누르면\n올라가요"} />
        ) : (
          <CenterMessage img="b4-2" title={"휴대폰에\n저장했어요"} sub={"인스타그램에서 사진을 골라\n직접 올려 주세요"} />
        )}
      </SubPage>
    );
  }

  if (step === "edit") {
    return (
      <SubPage title="글자 고치기" onBack={() => setStep("preview")} footer={<PrimaryButton onPress={() => setStep("preview")}>다 고쳤어요</PrimaryButton>}>
        <Text className="text-label text-ink-2">큰 글자</Text>
        <TextInput
          testID="poster-headline"
          accessibilityLabel="큰 글자"
          multiline
          value={head}
          onChangeText={setHeadline}
          textAlignVertical="top"
          className="mt-1 min-h-[120px] w-full rounded-2xl border-2 border-brand bg-surface px-4 py-3 text-body text-ink"
        />
        <Text className="mt-4 text-label text-ink-2">작은 글자</Text>
        <TextInput
          testID="poster-store"
          accessibilityLabel="작은 글자"
          value={store}
          onChangeText={setStoreLine}
          className="mt-1 h-14 w-full rounded-2xl border-2 border-brand bg-surface px-4 text-body text-ink"
        />
      </SubPage>
    );
  }

  if (step === "preview") {
    const pad = Math.max(GAP, (screenW - POSTER_W) / 2);
    const dests: { k: Dest; icon: IconName; title: string; sub: string }[] = [
      { k: "story", icon: "image", title: "인스타 스토리", sub: "24시간 동안 보여요" },
      { k: "feed", icon: "list", title: "인스타 게시물", sub: "피드에 계속 남아요" },
      { k: "save", icon: "download", title: "휴대폰에 저장", sub: "나중에 직접 올려요" },
    ];
    return (
      <>
        <SubPage
          title="포스터 미리 보기"
          footer={
            <>
              {scheduled ? (
                <PrimaryButton onPress={keep}>이대로 만들어 두기</PrimaryButton>
              ) : (
                <PrimaryButton onPress={() => setSheet(true)}>인스타에 올리기</PrimaryButton>
              )}
              <SecondaryButton testID="poster-edit" outline onPress={() => setStep("edit")}>
                글자 고치기
              </SecondaryButton>
            </>
          }
        >
          <ScrollView
            ref={scroller}
            horizontal
            showsHorizontalScrollIndicator={false}
            snapToInterval={PAGE}
            decelerationRate="fast"
            style={{ marginHorizontal: -24 }}
            contentContainerStyle={{ paddingHorizontal: pad, gap: GAP, paddingBottom: 8 }}
            scrollEventThrottle={32}
            onLayout={() => {
              // 만들어 둔 색으로 처음 보여 준다.
              if (placed.current) return;
              placed.current = true;
              scroller.current?.scrollTo({ x: THEMES.indexOf(theme) * PAGE, animated: false });
            }}
            onScroll={(e) => {
              const i = Math.round(e.nativeEvent.contentOffset.x / PAGE);
              if (THEMES[i] && THEMES[i] !== theme) setTheme(THEMES[i]);
            }}
          >
            {THEMES.map((t, i) => (
              <View
                key={t}
                collapsable={false}
                ref={(el) => {
                  shots.current[i] = el;
                }}
              >
                <PosterCard {...poster} theme={t} />
              </View>
            ))}
          </ScrollView>
          <Text className="mt-2 text-center text-small text-ink-2">3장 중 {THEMES.indexOf(theme) + 1}장, 옆으로 넘겨 보세요</Text>
        </SubPage>
        <Sheet open={sheet} onClose={() => setSheet(false)} onDismiss={sheetClose.onDismiss} title="어디에 올릴까요?">
          <View className="gap-2.5" accessibilityRole="radiogroup" accessibilityLabel="올릴 곳">
            {dests.map((o) => (
              <Pressable
                key={o.k}
                testID={`dest-${o.k}`}
                accessibilityRole="radio"
                accessibilityState={{ checked: dest === o.k }}
                onPress={() => setDest(o.k)}
                className={`min-h-16 flex-row items-center gap-3 rounded-button border px-4 py-2 ${dest === o.k ? "border-brand bg-brand-soft" : "border-line bg-surface"}`}
              >
                <Icon name={o.icon} size={26} color={C["ink-2"]} />
                <View>
                  <Text className="text-body font-medium text-ink">{o.title}</Text>
                  <Text className="text-small text-ink-2">{o.sub}</Text>
                </View>
              </Pressable>
            ))}
          </View>
          {sendFailed ? (
            <Text accessibilityRole="alert" className="mt-3 text-label text-urgent">
              보내지 못했어요. 다시 눌러 주세요.
            </Text>
          ) : null}
          <View className="mt-5">
            <PrimaryButton testID="poster-send" onPress={send} disabled={sending}>
              {dest === "save" ? "휴대폰에 저장하기" : "인스타그램으로 보내기"}
            </PrimaryButton>
          </View>
        </Sheet>
      </>
    );
  }

  // 06-61 사진 고르기: 매장 사진·메뉴 사진 (네이버 플레이스) + 로고
  return (
    <SubPage
      title="포스터 사진 고르기"
      footer={
        <>
          <PrimaryButton onPress={make}>이 사진으로 만들기</PrimaryButton>
          <SecondaryButton testID="poster-pick-photo" onPress={pickPhoto}>
            휴대폰에서 고르기
          </SecondaryButton>
        </>
      }
    >
      <Text className="text-display text-ink" accessibilityRole="header">
        어떤 사진을 보여 줄까요?
      </Text>
      <View className="mt-1">
        <Note icon="store">네이버 플레이스에 올린 사진이에요</Note>
      </View>
      <View className="mt-4 flex-row flex-wrap justify-between gap-y-3" accessibilityRole="radiogroup" accessibilityLabel="포스터 사진">
        {choices.slice(0, 8).map((c, i) => (
          <Pressable
            key={c.key}
            testID={`poster-menu-${i}`}
            accessibilityRole="radio"
            accessibilityState={{ checked: menuIdx === i }}
            accessibilityLabel={c.label}
            onPress={() => setMenuIdx(i)}
            className="gap-1.5"
            style={{ width: "48%" }}
          >
            <View className={`h-[100px] w-full items-center justify-center overflow-hidden rounded-2xl bg-brand-soft ${menuIdx === i ? "border-2 border-brand" : ""}`}>
              {c.photo ? (
                <Image source={{ uri: c.photo }} style={{ width: "100%", height: "100%" }} resizeMode="cover" accessibilityLabel={c.label} />
              ) : (
                <>
                  <Icon name="image" size={28} color={C["ink-2"]} />
                  <Text className="text-small text-ink-2">사진</Text>
                </>
              )}
            </View>
            <View className="flex-row items-center gap-1">
              {menuIdx === i ? (
                <View className="h-5 w-5 items-center justify-center rounded-full bg-brand">
                  <Icon name="check" size={14} color={C["brand-ink"]} />
                </View>
              ) : null}
              <Text className="flex-1 text-body text-ink" numberOfLines={1}>
                {c.label}
              </Text>
            </View>
          </Pressable>
        ))}
      </View>
      {/* 로고: 있으면 포스터 모서리에 넣고, 없으면 도나가 들어가요. 가게 이름과 주소는 늘 들어가요 */}
      {!USE_MOCK ? (
        <View testID="poster-logo-row" className="mt-5 flex-row items-center gap-3 rounded-2xl border border-line bg-surface p-3.5">
          <View className="h-14 w-14 items-center justify-center overflow-hidden rounded-xl bg-paper">
            {logo ? <Image source={{ uri: logo }} style={{ width: 56, height: 56 }} resizeMode="contain" accessibilityLabel="가게 로고" /> : <Icon name="store" size={26} color={C["ink-3"]} />}
          </View>
          <View className="flex-1">
            <Text className="text-body font-bold text-ink">{!logo ? "가게 로고가 없어요" : place?.logo_source === "NAVER" ? "네이버 소식에서 찾은 로고예요" : "가게 로고를 넣어요"}</Text>
            <Text className="text-small text-ink-2" numberOfLines={2}>
              {`${store}${address ? `, ${address}` : ""}`}
            </Text>
          </View>
          <Pressable testID="poster-logo-upload" accessibilityRole="button" disabled={logoBusy} onPress={() => void uploadLogo()} className="h-10 items-center justify-center rounded-xl border border-brand px-3 active:bg-brand-soft">
            <Text className="text-label font-bold text-brand">{logoBusy ? "올리는 중" : logo ? "바꾸기" : "올리기"}</Text>
          </Pressable>
        </View>
      ) : null}
      {logoFailed ? <FailNote title="로고를 올리지 못했어요" sub={logoFailed} icon="refresh" /> : null}
      {failed ? <FailNote title="포스터를 못 만들었어요" /> : null}
    </SubPage>
  );
}
