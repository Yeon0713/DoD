// 설정 › 계정 (Figma 08-19a 네이버 연결 전, 08-19b 연결됨).
// 네이버 계정을 연결하면 네이버 플레이스(장사 시간, 메뉴, 사진, 메뉴 순서 바꾸기)도 함께 연결된다. 끊어도 리뷰와 할 일은 남는다.
import { useState, type ReactNode } from "react";
import { Image, Pressable, View } from "react-native";
import { Icon, type IconName } from "@/components/icons/Icon";
import { NaverLogo } from "@/components/icons/NaverLogo";
import { NaverButton } from "@/components/start/AccountScreens";
import { storeName } from "@/components/start/flow";
import { back, go } from "@/components/ui/nav";
import { PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Sheet, useSheetClose } from "@/components/ui/Sheet";
import { Note, SubPage } from "@/components/ui/sub";
import { Text } from "@/components/ui/Text";
import { account, maskPhone } from "@/lib/account";
import { resetCardState } from "@/lib/cardState";
import { drafts, flashToast, prefs } from "@/lib/localStore";
import { NAVER_FIELD_LABEL, naverFieldText, naverProfile } from "@/lib/naverDemo";
import { onTestLogout } from "@/lib/testAccount";
import { useHome } from "@/lib/useHome";
import tokens from "@/theme/tokens.json";

const C = tokens.colors;

function Card({ children, testID }: { children: ReactNode; testID?: string }) {
  return (
    <View testID={testID} className="gap-3 rounded-card border border-line bg-surface p-5">
      {children}
    </View>
  );
}

export function AccountSettingsScreen() {
  const acc = account.useValue();
  // 데모 테스트 모드에서 진짜 네이버 로그인으로 받은 정보
  const profile = naverProfile.useValue().value;
  const { data, prefs: p } = useHome();
  const [leaving, setLeaving] = useState(false);
  const sheetClose = useSheetClose();
  const linked = p.naverConnected;
  const store = data ? storeName(data.settings.settings.name) : "";

  const methods = [acc.phone ? `휴대폰 ${maskPhone(acc.phone)}` : null, acc.method === "naver" || linked ? "네이버" : null].filter(Boolean);
  const loginLabel = acc.phone && (acc.method === "naver" || linked) ? "휴대폰, 네이버" : (methods[0] ?? "");

  const disconnect = () => {
    prefs.write({ naverConnected: false, naverAuto: false });
    flashToast("네이버 연결을 끊었어요", "메뉴 순서는 직접 바꿔 주세요");
  };
  // 계정을 지우면 아래 탭의 문(app/(tabs)/_layout.tsx)이 로그인 화면으로 보낸다. 여기서 따로 화면을 옮기지 않는다.
  const logout = async () => {
    // 테스트 계정이면 서버 DB 조건(on_logout)대로: reset 은 그 가게와 이 기기 기록을 처음으로, keep 은 계정별로 보관
    await onTestLogout();
    naverProfile.reset();
    account.reset();
  };
  const withdraw = async () => {
    // 시트가 다 닫힌 뒤에 화면을 옮긴다 (열린 시트째 옮기면 iOS에서 앱이 멈춘다).
    setLeaving(false);
    await sheetClose.closed();
    // 목업: 이 기기의 계정과 처음 설정, 카드 기록, 고쳐 쓴 답글을 지운다. 제안: DELETE /api/account
    naverProfile.reset();
    account.reset();
    prefs.reset();
    drafts.reset();
    resetCardState();
  };

  const got: { icon: IconName; text: string }[] = [
    { icon: "store", text: `네이버 플레이스: ${store}` },
    { icon: "clock", text: "장사 시간, 메뉴, 사진을 불러왔어요" },
    { icon: "link", text: "메뉴 순서를 바꿀 수 있어요" },
  ];

  return (
    <SubPage
      title="계정"
      onBack={() => back("/settings")}
      footer={
        <View className="items-center">
          <SecondaryButton testID="account-logout" onPress={logout}>
            로그아웃
          </SecondaryButton>
          <Pressable testID="account-withdraw" accessibilityRole="button" hitSlop={8} onPress={() => setLeaving(true)} className="min-h-11 justify-center px-4">
            <Text className="text-small text-ink-3">탈퇴하기</Text>
          </Pressable>
        </View>
      }
    >
      <View className="gap-4">
        <Card testID="account-login">
          <View className="flex-row items-center gap-2">
            <Text className="flex-1 text-body text-ink">로그인</Text>
            <Text className="text-label text-ink-2">{loginLabel}</Text>
          </View>
        </Card>

        {profile ? (
          <Card testID="account-naver-profile">
            <Text className="text-body font-bold text-ink">네이버에서 받은 정보</Text>
            {profile.test ? (
              <Text className="text-small text-ink-3">임시 네이버 로그인의 테스트 계정이에요{profile.storeName ? ` · 가게: ${profile.storeName}` : ""}</Text>
            ) : null}
            <View className="gap-2.5">
              {Object.keys(NAVER_FIELD_LABEL)
                .filter((k) => profile.received[k])
                .map((k) => (
                  <View key={k} className="gap-0.5">
                    <Text className="text-small text-ink-2">{NAVER_FIELD_LABEL[k]}</Text>
                    {k === "profile_image" ? (
                      <Image source={{ uri: profile.received[k] }} style={{ width: 48, height: 48, borderRadius: 24 }} accessibilityLabel="프로필 사진" />
                    ) : (
                      <Text className="text-body text-ink" selectable>
                        {naverFieldText(k, profile.received[k])}
                      </Text>
                    )}
                  </View>
                ))}
            </View>
            {profile.missing.length > 0 ? (
              <Text className="text-small text-ink-3">받지 못한 정보: {profile.missing.map((k) => NAVER_FIELD_LABEL[k] ?? k).join(", ")}</Text>
            ) : null}
          </Card>
        ) : null}

        <Card testID={linked ? "account-naver-linked" : "account-naver-unlinked"}>
          <View className="flex-row items-center gap-3">
            <View className="h-10 w-10 items-center justify-center rounded-[10px] bg-naver">
              <NaverLogo size={16} />
            </View>
            <View className="flex-1">
              <Text className="text-body font-bold text-ink">네이버 계정</Text>
              <View className="flex-row items-center gap-1">
                {linked ? <Icon name="check" size={16} color={C.done} /> : null}
                <Text className={`text-label ${linked ? "text-done" : "text-ink-3"}`}>{linked ? "연결됨" : "연결 안 됨"}</Text>
              </View>
            </View>
          </View>
          {linked ? (
            <>
              <View className="gap-2 rounded-xl bg-paper px-3.5 py-3">
                {got.map((g) => (
                  <View key={g.text} className="flex-row items-center gap-2">
                    <Icon name={g.icon} size={20} color={C["ink-2"]} />
                    <Text className="flex-1 text-label text-ink-2">{g.text}</Text>
                  </View>
                ))}
              </View>
              <Pressable testID="account-naver-disconnect" accessibilityRole="button" onPress={disconnect} className="h-[52px] items-center justify-center rounded-button border-[1.5px] border-line active:bg-brand-soft">
                <Text className="text-body font-medium text-ink-2">연결 끊기</Text>
              </Pressable>
              <Text className="text-small text-ink-3">끊어도 도나에 있는 리뷰와 할 일은 그대로예요. 메뉴 순서 바꾸기만 멈춰요</Text>
            </>
          ) : (
            <>
              <Text className="text-body text-ink-2">연결하면 네이버 플레이스의 장사 시간, 메뉴, 사진을 불러오고, 누르시면 메뉴 순서도 바꿔 드려요</Text>
              <NaverButton testID="account-naver-connect" onPress={() => go("/start/naver-login?mode=link")}>
                네이버 계정 연결하기
              </NaverButton>
              <Note icon="shield">비밀번호는 받지 않아요</Note>
            </>
          )}
        </Card>
      </View>

      <Sheet open={leaving} onClose={() => setLeaving(false)} onDismiss={sheetClose.onDismiss} title={"정말\n탈퇴할까요?"}>
        <Text className="text-body text-ink-2">이 휴대폰에 있는 가게 설정, 할 일 기록, 고쳐 쓴 답글이 모두 지워져요. 되돌릴 수 없어요.</Text>
        <View className="mt-5 gap-1">
          <PrimaryButton testID="withdraw-cancel" onPress={() => setLeaving(false)}>
            계속 쓸게요
          </PrimaryButton>
          <SecondaryButton testID="withdraw-confirm" onPress={() => void withdraw()}>
            탈퇴하기
          </SecondaryButton>
        </View>
      </Sheet>
    </SubPage>
  );
}
