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
import { api } from "@/lib/api";
import { flashToast, prefs } from "@/lib/localStore";
import { useHome } from "@/lib/useHome";
import { STORE_ADDRESS } from "@/mocks/extras";
import tokens from "@/theme/tokens.json";
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
      <View className="flex-1 px-6 pb-5 pt-3">
        <Pressable testID="back" accessibilityRole="button" accessibilityLabel="뒤로" onPress={() => back("/start")} className="-ml-2.5 h-11 w-11 items-center justify-center rounded-full active:bg-brand-soft">
          <Icon name="chevL" size={26} />
        </Pressable>
        <View className="mt-10 items-center">
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
  const mode = modeOf(useLocalSearchParams<{ mode?: string }>().mode);
  const qc = useQueryClient();
  const [failed, setFailed] = useState(false);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let alive = true;
    naverLogin()
      .then(async () => {
        if (!alive) return;
        // 네이버 계정을 연결하면 네이버 플레이스(장사 시간, 메뉴, 사진)도 함께 연결된다.
        prefs.write({ naverConnected: true, naverDeclined: false });
        if (mode === "link") {
          flashToast("네이버 계정을 연결했어요", "메뉴 순서도 바꿀 수 있어요");
          back("/settings/account");
          return;
        }
        if (!account.read().method) account.write({ method: "naver" });
        await qc.fetchQuery({ queryKey: NAVER_PLACE_KEY, queryFn: api.naverPlace, staleTime: 0 }).catch(() => undefined);
        if (alive) afterSignIn("/start/naver-store");
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [mode, qc, tries]);

  const got: { icon: IconName; text: string }[] = [
    { icon: "check", text: "사장님 이름" },
    { icon: "check", text: "네이버 플레이스에 올린 가게" },
    { icon: "check", text: "장사 시간, 메뉴, 사진" },
  ];
  return (
    <SubPage
      onBack={() => back(mode === "link" ? "/settings/account" : "/start")}
      footer={
        failed ? (
          <PrimaryButton
            testID="naver-retry"
            onPress={() => {
              setFailed(false);
              setTries((n) => n + 1);
            }}
          >
            다시 하기
          </PrimaryButton>
        ) : null
      }
    >
      <TitleWithDonna title={"네이버에서\n확인해 주세요"} sub="네이버 화면이 열려요. 거기서 로그인하고 동의를 누르면 돌아와요" />
      <View testID="naver-handoff" className="mt-6 h-[200px] items-center justify-center gap-2.5 rounded-2xl border-[1.5px] border-dashed border-line bg-surface px-6">
        <View className="h-14 w-14 items-center justify-center rounded-[14px] bg-naver">
          <NaverLogo size={24} />
        </View>
        <Text className="text-label text-ink-2">{failed ? "연결하지 못했어요" : "네이버 로그인 화면"}</Text>
        <Text className="text-center text-small text-ink-3">{failed ? "인터넷을 확인하고 다시 해 주세요" : "이 자리는 네이버가 그려요. 도나가 따로 만들지 않아요"}</Text>
      </View>
      <View className="mt-5 gap-2">
        <Text className="text-label font-bold text-ink">도나가 받는 것</Text>
        {got.map((g) => (
          <View key={g.text} className="flex-row items-center gap-2">
            <Icon name={g.icon} size={18} color={C.done} />
            <Text className="text-body text-ink-2">{g.text}</Text>
          </View>
        ))}
      </View>
      <View className="mt-3">
        <Note icon="shield">비밀번호는 받지 않아요. 연결은 설정에서 언제든 끊을 수 있어요</Note>
      </View>
    </SubPage>
  );
}

/** 08-1c 네이버로 가입했어요 · 우리 가게 확인 (06-2 가게 찾기와 06-2n 네이버 플레이스 연결을 한 번에) */
export function NaverStoreScreen() {
  const { data } = useHome();
  // 네이버로 시작할 때 받아 둔 네이버 플레이스 값 (다음 화면 06-2c와 같은 리뷰 수)
  const placeQ = useQuery({ queryKey: NAVER_PLACE_KEY, queryFn: api.naverPlace, staleTime: Infinity });
  const reviewCount = placeQ.data?.place.review_count ?? data?.reviews.reviews.length ?? 0;
  const s = data?.settings.settings;
  const rows: { icon: IconName; text: string }[] = [
    { icon: "clock", text: "요일별 장사 시간" },
    { icon: "image", text: "메뉴와 메뉴 사진" },
    { icon: "messages", text: `리뷰 ${reviewCount}개 (배민, 쿠팡이츠, 요기요, 네이버)` },
  ];
  return (
    <SubPage
      onBack={() => back("/start")}
      footer={
        <>
          <PrimaryButton testID="naver-store-ok" onPress={() => go("/start/naver-confirm")}>
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
            <Text className="text-label text-ink-2">{STORE_ADDRESS[s.store_id] ?? "강원 춘천시 효자동"}</Text>
          </View>
          <View className="h-7 w-7 items-center justify-center rounded-full bg-brand">
            <Icon name="check" size={18} color={C["brand-ink"]} />
          </View>
        </View>
      ) : null}
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
