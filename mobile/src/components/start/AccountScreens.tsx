// 시작, 가입, 로그인 (Figma 08-1L, 08-1n, 08-1c, 08-1p, 08-1o). 첫 화면 08-1은 StartScreens.tsx의 IntroScreen.
// 비밀번호는 만들지 않는다. 네이버로 시작하거나 휴대폰 번호로 문자 숫자 6개를 받아 시작한다.
// 목업: 네이버 로그인 화면은 네이버가 그리므로 잠깐 기다렸다가 돌아온 것으로 본다. 숫자는 000000만 틀린 것으로 본다.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState, type ComponentRef } from "react";
import { Pressable, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Icon, type IconName } from "@/components/icons/Icon";
import { NaverLogo } from "@/components/icons/NaverLogo";
import { back, go, goHome, replace } from "@/components/ui/nav";
import { DonnaImage, PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Note, SubPage } from "@/components/ui/sub";
import { Text } from "@/components/ui/Text";
import { account, formatPhone, isPhone } from "@/lib/account";
import { naverLogin, sendPhoneCode, verifyPhoneCode } from "@/lib/actions";
import { api, ApiFailure } from "@/lib/api";
import { flashToast, prefs } from "@/lib/localStore";
import { goToNaverLogin, naverErrorText, naverProfile, readNaverResult, useRealNaver } from "@/lib/naverDemo";
import { useHome } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";
import { DemoMenuBar } from "./DemoMenu";
import { TitleWithDonna } from "./HoursEditor";
import { NAVER_PLACE_KEY, param, storeName } from "./flow";

const C = tokens.colors;

/** signup: 처음 가입, login: 다시 왔을 때, link: 설정 › 계정에서 네이버 계정 연결 */
type Mode = "signup" | "login" | "link";
const modeOf = (v: string | string[] | undefined): Mode => {
  const m = param(v);
  return m === "login" || m === "link" ? m : "signup";
};

/** 네이버 로그인 버튼. 네이버 로그인 디자인 가이드: 초록 바탕(#03C75A), 흰 공식 로고와 흰 글자. 높이와 둥글기는 도나 버튼(56, 14). 토큰 밖 색은 이것 하나다. */
export function NaverButton({ children, onPress, testID = "naver-button", disabled }: { children: string; onPress: () => void; testID?: string; disabled?: boolean }) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={children}
      disabled={disabled}
      onPress={onPress}
      className={`h-14 w-full flex-row items-center justify-center gap-3 rounded-button bg-naver active:opacity-90 ${disabled ? "opacity-50" : ""}`}
    >
      <NaverLogo size={16} />
      <Text className="text-button text-white">{children}</Text>
    </Pressable>
  );
}

/** 08-1, 08-1L 아래 글자 링크 ("이미 쓰고 계세요? 로그인") */
export function AskLink({ ask, label, onPress, testID }: { ask: string; label: string; onPress: () => void; testID: string }) {
  return (
    <View className="flex-row items-center justify-center gap-1.5">
      <Text className="text-label text-ink-2">{ask}</Text>
      <Pressable testID={testID} accessibilityRole="link" hitSlop={10} onPress={onPress} className="min-h-11 justify-center">
        <Text className="text-label font-bold text-brand underline">{label}</Text>
      </Pressable>
    </View>
  );
}

/** 로그인이나 가입을 마친 뒤: 처음 설정을 마친 사장님은 홈으로, 아니면 처음 설정을 이어 간다. */
function afterSignIn(next: string) {
  if (prefs.read().onboarded) {
    flashToast("다시 오셨네요", "오늘 할 일을 보여 드릴게요");
    goHome();
  } else replace(next);
}

/** 08-1L 다시 왔을 때 · 로그인 */
export function LoginScreen() {
  return (
    <SafeAreaView edges={["top", "bottom"]} style={{ flex: 1, backgroundColor: C.paper }}>
      <DemoMenuBar
        left={
          <Pressable testID="back" accessibilityRole="button" accessibilityLabel="뒤로" onPress={() => back("/start")} className="h-11 w-11 items-center justify-center rounded-full active:bg-brand-soft">
            <Icon name="chevL" size={26} />
          </Pressable>
        }
      />
      <View className="flex-1 px-6 pb-5">
        <View className="mt-6 items-center">
          <DonnaImage img="b4-0" size={160} />
          <Text className="mt-2 text-center text-display text-ink" accessibilityRole="header">
            다시 오셨네요
          </Text>
          <Text className="mt-1 text-center text-body text-ink-2">처음 가입한 방법으로 들어와 주세요</Text>
        </View>
        <View className="flex-1" />
        <View className="gap-2.5">
          <NaverButton testID="login-naver" onPress={() => go("/start/naver-login?mode=login")}>
            네이버로 로그인
          </NaverButton>
          <SecondaryButton testID="login-phone" outline onPress={() => go("/start/phone?mode=login")}>
            휴대폰 번호로 로그인
          </SecondaryButton>
          <AskLink ask="처음이세요?" label="새로 시작하기" testID="login-to-start" onPress={() => replace("/start")} />
        </View>
      </View>
    </SafeAreaView>
  );
}

/** 08-1n 네이버 화면으로 넘어가요. 실제 네이버 로그인 화면은 네이버가 그린다. 목업은 잠깐 뒤 돌아온다. */
export function NaverLoginScreen() {
  const params = useLocalSearchParams<{ mode?: string; ticket?: string; error?: string }>();
  const mode = modeOf(params.mode);
  const qc = useQueryClient();
  const [tries, setTries] = useState(0);
  const [failText, setFailText] = useState<ReturnType<typeof naverErrorText> | null>(null);
  // 데모 테스트 모드(웹): 네이버 로그인 창으로 바로 갔다가 ?ticket= 또는 ?error= 를 달고 돌아온다.
  // 사장님은 "네이버로 시작하기"를 누르면 곧바로 네이버 화면을 보고, 이 화면은 그 앞뒤로 잠깐 기다리는 동안만 보인다.
  const real = useRealNaver();
  const ticket = param(params.ticket);
  const naverError = param(params.error);
  const returned = real && tries === 0 && !!ticket;

  useEffect(() => {
    let alive = true;
    const signIn = (): Promise<void> => {
      if (!real) return naverLogin();
      // 처음 돌아왔을 때만 돌아온 값을 본다. 다시 하기를 누르면 네이버 화면부터 다시 연다.
      if (tries === 0 && ticket)
        return readNaverResult(ticket).then((value) => {
          naverProfile.write({ value });
          // 이 계정의 가게로 바꾸고, 앞서 본 다른 가게 데이터는 지운다
          account.write({ storeId: value.storeId });
          qc.clear();
        });
      if (tries === 0 && naverError) return Promise.reject(new Error(naverError));
      // 기다리게 하지 않고 바로 네이버 로그인 화면으로 옮긴다 (개발 모드에서 효과가 두 번 돌아도 한 번만 옮기게 다음 틱에)
      return new Promise<void>(() => {
        void Promise.resolve().then(() => {
          if (alive) goToNaverLogin(`/start/naver-login${mode === "signup" ? "" : `?mode=${mode}`}`);
        });
      });
    };
    signIn()
      .then(async () => {
        if (!alive) return;
        const name = real ? naverProfile.read().value?.received.name : undefined;
        // 네이버 계정을 연결하면 네이버 플레이스(장사 시간, 메뉴, 사진)도 함께 연결된다.
        prefs.write({ naverConnected: true, naverDeclined: false });
        if (mode === "link") {
          flashToast("네이버 계정을 연결했어요", "메뉴 순서도 바꿀 수 있어요");
          back("/settings/account");
          return;
        }
        if (!account.read().method) account.write({ method: "naver" });
        if (name) flashToast(`${name} 사장님, 반가워요`, "네이버 계정으로 시작했어요");
        await qc.fetchQuery({ queryKey: NAVER_PLACE_KEY, queryFn: api.naverPlace, staleTime: 0 }).catch(() => undefined);
        if (!alive) return;
        // 네이버 로그인만으로는 사장님 가게를 알 수 없다. 데모 테스트 모드에서 등록한 가게가 없으면 가게 찾기부터 한다
        if (real && !account.read().storeId) replace("/start/store");
        else afterSignIn(real ? "/start/naver-confirm" : "/start/naver-store");
      })
      .catch((e: unknown) => {
        if (alive) setFailText(naverErrorText(real && e instanceof Error ? e.message : "NAVER_UNREACHABLE"));
      });
    return () => {
      alive = false;
    };
  }, [mode, qc, tries, real, ticket, naverError]);

  const leave = () => back(mode === "link" ? "/settings/account" : "/start");

  if (failText) {
    return (
      <SubPage
        onBack={leave}
        footer={
          <>
            <PrimaryButton
              testID="naver-retry"
              onPress={() => {
                setFailText(null);
                setTries((n) => n + 1);
              }}
            >
              다시 하기
            </PrimaryButton>
            {mode === "link" ? (
              <SecondaryButton testID="naver-later" onPress={leave}>
                나중에 할게요
              </SecondaryButton>
            ) : (
              <SecondaryButton testID="naver-phone" onPress={() => replace("/start/phone")}>
                휴대폰 번호로 시작하기
              </SecondaryButton>
            )}
          </>
        }
      >
        <View testID="naver-failed" className="flex-1 items-center justify-center px-2">
          <DonnaImage img={failText.img} size={150} />
          <Text className="mt-4 text-center text-display text-ink">{failText.title}</Text>
          <Text className="mt-2 text-center text-body text-ink-2">{failText.sub}</Text>
        </View>
      </SubPage>
    );
  }

  return (
    <SubPage onBack={leave}>
      <View testID="naver-waiting" className="flex-1 items-center justify-center px-2" accessibilityLiveRegion="polite">
        <DonnaImage img="b4-0" size={150} />
        <Text className="mt-4 text-center text-title text-ink">{returned ? "네이버에서 정보를\n받고 있어요" : "네이버 로그인 화면을\n열고 있어요"}</Text>
        <Text className="mt-2 text-center text-body text-ink-2">잠깐만 기다려 주세요</Text>
      </View>
    </SubPage>
  );
}

/** 서버가 이 가게의 알림 계획을 아직 만들지 못한다고 답했는지 (자정을 넘겨 여는 가게) */
export function isStoreNotReady(error: unknown): boolean {
  return error instanceof ApiFailure && error.code === "OVERNIGHT_STORE_NOT_SUPPORTED";
}

/** 서버가 아직 다루지 못하는 가게일 때. 빈 화면 대신 까닭을 알려 주고 다른 가게를 찾게 한다. */
export function StoreNotReady({ name, onBack }: { name?: string; onBack: () => void }) {
  return (
    <SubPage
      onBack={onBack}
      footer={
        <PrimaryButton testID="store-not-ready-home" onPress={() => replace("/start")}>
          처음으로
        </PrimaryButton>
      }
    >
      <View className="flex-1 items-center justify-center">
        <DonnaImage img="q-clipboard" size={160} />
        <Text className="mt-3 text-center text-display text-ink">아직 준비 중이에요</Text>
        <Text className="mt-2 text-center text-body text-ink-2">
          {name ? `${name}처럼 ` : ""}자정을 넘겨 여는 가게는{"\n"}곧 쓸 수 있게 준비하고 있어요
        </Text>
      </View>
    </SubPage>
  );
}

/** 처음 쓰는 날, 서버에서 가게 정보를 받지 못했을 때. 빈 화면 대신 까닭과 다시 불러오기를 보여 준다. */
export function StartLoadFail({ onBack, onRetry }: { onBack: () => void; onRetry: () => void }) {
  return (
    <SubPage
      onBack={onBack}
      footer={
        <PrimaryButton testID="start-retry" onPress={onRetry}>
          다시 불러오기
        </PrimaryButton>
      }
    >
      <View className="flex-1 items-center justify-center">
        <DonnaImage img="q-laptop" size={160} />
        <Text className="mt-3 text-center text-display text-ink">불러오지 못했어요</Text>
        <Text className="mt-2 text-center text-body text-ink-2">{"연결이 잠시 끊겼어요\n조금 뒤에 다시 눌러 주세요"}</Text>
      </View>
    </SubPage>
  );
}

/** 처음 쓰는 날 화면이 가게 정보를 못 받았을 때 대신 보일 화면. 문제가 없으면(받는 중이면) null */
export function startProblem(error: unknown, onRetry: () => void, onBack: () => void, name?: string) {
  if (isStoreNotReady(error)) return <StoreNotReady name={name} onBack={onBack} />;
  if (error) return <StartLoadFail onBack={onBack} onRetry={onRetry} />;
  return null;
}

/** 08-1c 네이버로 가입했어요 · 우리 가게 확인 (06-2 가게 찾기와 06-2n 네이버 플레이스 연결을 한 번에) */
export function NaverStoreScreen() {
  const { data, error, refetch } = useHome();
  // 네이버로 시작할 때 받아 둔 네이버 플레이스 값 (다음 화면 06-2c와 같은 리뷰 수)
  const placeQ = useQuery({ queryKey: NAVER_PLACE_KEY, queryFn: api.naverPlace, staleTime: Infinity });
  const reviewCount = placeQ.data?.place.review_count ?? data?.reviews.reviews.length ?? 0;
  const s = data?.settings.settings;
  // 가게를 못 받았는데 "찾았어요"라고 하지 않는다
  if (!data) {
    const problem = startProblem(error, () => refetch(), () => back("/start"), placeQ.data?.place.name);
    if (problem) return problem;
  }
  // 리뷰를 가져온 곳은 실제로 리뷰가 있는 곳만 적는다
  const PLATFORM_NAMES = { BAEMIN: "배민", COUPANG: "쿠팡이츠", YOGIYO: "요기요", NAVER: "네이버" } as const;
  const platforms = data ? (Object.keys(PLATFORM_NAMES) as (keyof typeof PLATFORM_NAMES)[]).filter((k) => data.reviews.reviews.some((r) => r.platform === k)).map((k) => PLATFORM_NAMES[k]) : [];
  const rows: { icon: IconName; text: string }[] = [
    { icon: "clock", text: "요일별 장사 시간" },
    { icon: "image", text: "메뉴와 메뉴 사진" },
    { icon: "messages", text: `리뷰 ${reviewCount}개${platforms.length ? ` (${platforms.join(", ")})` : ""}` },
  ];
  return (
    <SubPage
      onBack={() => back("/start")}
      footer={
        <>
          <PrimaryButton testID="naver-store-ok" disabled={!s} onPress={() => go("/start/naver-confirm")}>
            이 가게로 시작하기
          </PrimaryButton>
          <SecondaryButton testID="naver-store-other" onPress={() => go("/start/store")}>
            다른 가게예요
          </SecondaryButton>
        </>
      }
    >
      <TitleWithDonna title={"사장님 가게를\n찾았어요"} img="b4-0" sub="네이버 플레이스에 올린 가게예요" />
      {s ? (
        <View className="mt-5 flex-row items-center gap-3 rounded-2xl border-2 border-brand bg-brand-soft p-4" accessibilityLabel="찾은 가게, 골라 둠">
          <Icon name="store" size={32} color={C.brand} />
          <View className="flex-1">
            <Text className="text-body font-bold text-ink">{storeName(s.name)}</Text>
            <Text className="text-label text-ink-2">{placeQ.data?.place.address ?? ""}</Text>
          </View>
          <View className="h-7 w-7 items-center justify-center rounded-full bg-brand">
            <Icon name="check" size={18} color={C["brand-ink"]} />
          </View>
        </View>
      ) : (
        // 가게 이름이 오기 전에는 자리만 잡아 둔다. 어느 가게인지 모른 채 "이 가게로 시작하기"를 누르지 않게 버튼도 잠근다
        <View className="mt-5 h-[76px] rounded-2xl border border-line bg-surface" accessibilityLabel="가게를 불러오고 있어요" />
      )}
      <View className="mt-5 gap-3">
        <Text className="text-label font-bold text-ink">함께 불러올게요</Text>
        {rows.map((r) => (
          <View key={r.text} className="flex-row items-center gap-2.5">
            <Icon name={r.icon} size={24} color={C["ink-2"]} />
            <Text className="flex-1 text-body text-ink">{r.text}</Text>
          </View>
        ))}
      </View>
      <View className="mt-3.5">
        <Note icon="shield">사장님이 누르기 전엔 아무것도 바꾸지 않아요</Note>
      </View>
    </SubPage>
  );
}

/** 08-1p 휴대폰 번호 적기 */
export function PhoneScreen() {
  const mode = modeOf(useLocalSearchParams<{ mode?: string }>().mode);
  const [digits, setDigits] = useState(account.read().phone ?? "");
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState(false);
  const ok = isPhone(digits);
  const send = async () => {
    setSending(true);
    setFailed(false);
    try {
      await sendPhoneCode();
      go(`/start/code?phone=${digits}&mode=${mode}`);
    } catch {
      setFailed(true);
    } finally {
      setSending(false);
    }
  };
  return (
    <SubPage
      onBack={() => back(mode === "login" ? "/login" : "/start")}
      footer={
        <PrimaryButton testID="phone-send" onPress={send} disabled={!ok || sending}>
          {sending ? "보내는 중" : "숫자 받기"}
        </PrimaryButton>
      }
    >
      <Text className="pt-4 text-display text-ink" accessibilityRole="header">
        {"휴대폰 번호를\n적어 주세요"}
      </Text>
      <Text className="mt-2 text-body text-ink-2">문자로 숫자 6개를 보내 드려요</Text>
      <TextInput
        testID="phone-input"
        accessibilityLabel="휴대폰 번호"
        value={formatPhone(digits)}
        onChangeText={(v) => setDigits(v.replace(/\D/g, "").slice(0, 11))}
        keyboardType="phone-pad"
        autoComplete="tel"
        textContentType="telephoneNumber"
        placeholder="010-0000-0000"
        placeholderTextColor={C["ink-3"]}
        autoFocus
        onSubmitEditing={() => ok && void send()}
        className="mt-6 h-16 rounded-button border-2 border-brand bg-surface px-5 text-title text-ink"
      />
      <View className="mt-3">
        <Note icon="shield">가입과 로그인에만 써요. 광고 문자는 보내지 않아요</Note>
      </View>
      {failed ? (
        <Text accessibilityRole="alert" className="mt-3 text-label text-urgent">
          보내지 못했어요. 인터넷을 확인하고 다시 눌러 주세요.
        </Text>
      ) : null}
    </SubPage>
  );
}

const CODE_SECONDS = 180;
const RESEND_AFTER = 30;

/** 08-1o 문자로 온 숫자 6개 적기. 6칸을 다 적으면 바로 확인한다. */
export function CodeScreen() {
  const params = useLocalSearchParams<{ phone?: string; mode?: string }>();
  const mode = modeOf(params.mode);
  const phone = param(params.phone) ?? "";
  const [code, setCode] = useState("");
  const [left, setLeft] = useState(CODE_SECONDS);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<ComponentRef<typeof TextInput>>(null);

  useEffect(() => {
    const h = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(h);
  }, []);

  const expired = left === 0;
  const verify = async (value: string) => {
    setChecking(true);
    setError(null);
    try {
      await verifyPhoneCode(value);
      account.write({ method: account.read().method === "naver" ? "naver" : "phone", phone });
      afterSignIn("/start/store");
    } catch (e) {
      setError(e instanceof Error && e.message === "WRONG_CODE" ? "숫자가 맞지 않아요. 다시 적어 주세요" : "확인하지 못했어요. 인터넷을 확인해 주세요");
      setCode("");
      input.current?.focus();
    } finally {
      setChecking(false);
    }
  };
  const onChange = (v: string) => {
    const next = v.replace(/\D/g, "").slice(0, 6);
    setCode(next);
    if (next.length > 0) setError(null);
    if (next.length === 6 && !expired) void verify(next);
  };
  const resend = async () => {
    await sendPhoneCode().catch(() => undefined);
    setLeft(CODE_SECONDS);
    setCode("");
    setError(null);
    flashToast("숫자를 다시 보냈어요", formatPhone(phone));
  };
  const mm = Math.floor(left / 60);
  const ss = String(left % 60).padStart(2, "0");

  return (
    <SubPage
      onBack={() => back(`/start/phone?mode=${mode}`)}
      footer={
        <PrimaryButton testID="code-confirm" onPress={() => void verify(code)} disabled={code.length < 6 || checking || expired}>
          {checking ? "확인하는 중" : "확인"}
        </PrimaryButton>
      }
    >
      <Text className="pt-4 text-display text-ink" accessibilityRole="header">
        {"문자로 온\n숫자 6개를 적어 주세요"}
      </Text>
      <Text className="mt-2 text-body text-ink-2">{formatPhone(phone)}로 보냈어요</Text>
      <View testID="code-boxes" className="mt-6 flex-row gap-2">
        {Array.from({ length: 6 }, (_, i) => {
          const on = i === Math.min(code.length, 5) && !expired;
          return (
            <View key={i} className={`h-[60px] flex-1 items-center justify-center rounded-xl bg-surface ${on ? "border-2 border-brand" : "border-[1.5px] border-line"}`}>
              <Text className="text-title text-ink">{code[i] ?? ""}</Text>
            </View>
          );
        })}
        {/* 실제 입력 칸은 6칸 위에 투명하게 덮는다. 칸을 누르면 바로 이 칸이 눌리고, 문자 자동 채우기도 받는다. */}
        <TextInput
        ref={input}
        testID="code-input"
        accessibilityLabel="문자로 온 숫자 6개"
        value={code}
        onChangeText={onChange}
        keyboardType="number-pad"
        textContentType="oneTimeCode"
        autoComplete="sms-otp"
        maxLength={6}
        autoFocus
        caretHidden
        style={{ position: "absolute", left: 0, right: 0, top: 0, bottom: 0, opacity: 0, color: "transparent" }}
      />
      </View>
      <View className="mt-3.5 flex-row items-center justify-between">
        <Text className={`text-label ${expired ? "text-urgent" : "text-ink-2"}`}>{expired ? "시간이 지났어요. 다시 받아 주세요" : `${mm}분 ${ss}초 남았어요`}</Text>
        <Pressable testID="code-resend" accessibilityRole="button" hitSlop={10} disabled={left > CODE_SECONDS - RESEND_AFTER} onPress={() => void resend()} className="min-h-11 justify-center">
          <Text className={`text-label font-bold underline ${left > CODE_SECONDS - RESEND_AFTER ? "text-ink-3" : "text-brand"}`}>다시 받기</Text>
        </Pressable>
      </View>
      {error ? (
        <Text accessibilityRole="alert" className="mt-2 text-label text-urgent">
          {error}
        </Text>
      ) : null}
    </SubPage>
  );
}
