// 시작 화면과 로그인 화면 위의 메뉴(☰). 시험·시연용 기능을 모아 둔다.
// - 데모 테스트 모드: 켜면 "네이버로 시작하기/로그인"이 서버의 네이버 로그인(앱 키가 없으면 임시 네이버 로그인)으로 가서 계정을 고를 수 있다.
// - 초기화: 등록한 가게, 불러온 리뷰, 이 기기 기록을 지워 가게 찾기(지도)부터 다시 할 수 있게 한다.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Pressable, View } from "react-native";
import { Icon } from "@/components/icons/Icon";
import { replace } from "@/components/ui/nav";
import { PrimaryButton, SecondaryButton } from "@/components/ui/parts";
import { Sheet } from "@/components/ui/Sheet";
import { Toggle } from "@/components/ui/sub";
import { Text } from "@/components/ui/Text";
import { account } from "@/lib/account";
import { USE_MOCK } from "@/lib/api";
import { resetCardState } from "@/lib/cardState";
import { drafts, flashToast, prefs } from "@/lib/localStore";
import { demoMode, naverProfile } from "@/lib/naverDemo";
import { BASE_URL, serverHealth, type ServerHealth } from "@/lib/server";
import { storage } from "@/lib/storage";
import tokens from "@/theme/tokens.json";
import { pickedPlace } from "./flow";

const C = tokens.colors;

/** 메뉴를 열 때마다 서버에 닿는지 본다. 시험하는 팀원이 "왜 안 되지"를 메뉴에서 바로 알 수 있게.
 * 확인 중이면 undefined, 닿지 않으면 null */
function useServerCheck(open: boolean): ServerHealth | null | undefined {
  const { data, isFetching } = useQuery({
    queryKey: ["server-health"],
    queryFn: () => serverHealth(3000),
    enabled: open && !USE_MOCK,
    staleTime: 0,
    gcTime: 0,
    retry: false,
  });
  return isFetching ? undefined : data;
}

function ServerLine({ health }: { health: ServerHealth | null | undefined }) {
  const where = BASE_URL.replace(/^https?:\/\//, "");
  if (USE_MOCK) return <Text testID="start-menu-server" className="text-small text-ink-3">앱 안 예시 데이터로 보고 있어요 (서버를 쓰지 않아요)</Text>;
  if (health === undefined) return <Text testID="start-menu-server" className="text-small text-ink-3">{`서버 확인 중 · ${where}`}</Text>;
  if (health === null)
    return (
      <Text testID="start-menu-server" className="text-small text-urgent">
        {`서버에 닿지 않아요 · ${where}\n서버를 켰는지 확인해 주세요 (server 폴더에서 python run_dev.py)`}
      </Text>
    );
  // 예전 서버는 dev_mode 를 알려 주지 않는다. 시계 앞당김 값이 오면 시험용으로 켠 것이다
  const dev = health.dev_mode ?? health.clock_shift_minutes !== undefined;
  if (!dev)
    return (
      <Text testID="start-menu-server" className="text-small text-urgent">
        {`서버에 연결됐지만 시험용으로 켜지 않았어요 · ${where}\n초기화가 서버까지 닿으려면 python run_dev.py 로 켜 주세요`}
      </Text>
    );
  return <Text testID="start-menu-server" className="text-small text-ink-3">{`서버에 연결됐어요 · ${where}`}</Text>;
}

/** 오른쪽 위 줄: 데모 모드 표시 + 메뉴 버튼. left 에는 뒤로 버튼 같은 것을 넣는다.
 * center 를 주면(시작 화면의 로고) 가운데에 두고, 줄을 본문과 같은 24 안쪽에 맞춘다. 데모 표시는 로고를 가리지 않게 줄 아래로 내린다. */
export function DemoMenuBar({ left, center }: { left?: React.ReactNode; center?: React.ReactNode }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [serverNote, setServerNote] = useState<string | null>(null);
  const demo = demoMode.useValue();
  const health = useServerCheck(open);

  const reset = async () => {
    setResetting(true);
    setServerNote(null);
    // 서버: 등록한 가게와 불러온 리뷰, 등록 기록, 고친 설정을 지운다 (서버를 개발 모드로 켰을 때만 열린다)
    if (!USE_MOCK) {
      try {
        const res = await fetch(`${BASE_URL}/dev/reset`, { method: "POST" });
        if (!res.ok) setServerNote("서버 기록은 지우지 못했어요. 서버를 python run_dev.py 로 켜 주세요");
      } catch {
        setServerNote("서버에 닿지 않아 이 기기 기록만 지웠어요");
      }
    }
    // 이 기기: 로그인, 가입, 끝낸 일, 고쳐 쓴 답글 등을 지운다 (데모 테스트 모드 같은 시험용 스위치는 남긴다)
    storage.clearAll();
    resetCardState();
    prefs.reset();
    drafts.reset();
    account.reset();
    naverProfile.reset();
    pickedPlace.reset();
    qc.clear();
    setResetting(false);
    setConfirming(false);
    setOpen(false);
    flashToast("처음 상태로 돌렸어요", "로그인하고 가게를 지도에서 다시 골라 주세요");
    replace("/start");
  };

  return (
    <>
      <View className={`h-11 flex-row items-center gap-2 ${center ? "px-6" : "mt-3 px-4"}`}>
        <View className="flex-1 flex-row">{left}</View>
        {center ? (
          <View pointerEvents="none" className="absolute inset-y-0 left-0 right-0 items-center justify-center">
            {center}
          </View>
        ) : null}
        {demo.on && !center ? (
          <View testID="start-demo-badge" className="rounded-full bg-brand-soft px-3 py-1">
            <Text className="text-small font-medium text-brand">데모 테스트 모드</Text>
          </View>
        ) : null}
        <Pressable
          testID="start-menu"
          accessibilityRole="button"
          accessibilityLabel="메뉴"
          onPress={() => setOpen(true)}
          hitSlop={8}
          className="h-11 w-11 items-center justify-center rounded-full active:bg-brand-soft"
        >
          <Icon name="menu" size={26} color={C.ink} />
        </Pressable>
      </View>
      {demo.on && center ? (
        <View testID="start-demo-badge" className="mt-1 self-center rounded-full bg-brand-soft px-3 py-1">
          <Text className="text-small font-medium text-brand">데모 테스트 모드</Text>
        </View>
      ) : null}
      <Sheet open={open && !confirming} onClose={() => setOpen(false)} title="메뉴">
        <View className="gap-2.5">
          <View testID="start-menu-demo" className="min-h-[64px] flex-row items-center gap-3 rounded-card border border-line px-4 py-3">
            <Icon name="user" size={24} color={C.brand} />
            <View className="flex-1">
              <Text className="text-body font-medium text-ink">데모 테스트 모드</Text>
              <Text className="text-small text-ink-2">켜면 네이버 로그인에서 테스트 계정을 골라 들어가요</Text>
            </View>
            <Toggle testID="start-menu-demo-toggle" label="데모 테스트 모드" checked={demo.on} onChange={(on) => demoMode.write({ on })} />
          </View>
          <Pressable
            testID="start-menu-reset"
            accessibilityRole="button"
            onPress={() => setConfirming(true)}
            className="min-h-[64px] flex-row items-center gap-3 rounded-card border border-line px-4 py-3 active:bg-brand-soft"
          >
            <Icon name="refresh" size={24} color={C.urgent} />
            <View className="flex-1">
              <Text className="text-body font-medium text-ink">초기화</Text>
              <Text className="text-small text-ink-2">등록한 가게를 지우고 지도에서 다시 골라요</Text>
            </View>
            <Icon name="chevR" size={20} color={C["ink-3"]} />
          </Pressable>
          {serverNote ? <Text className="text-small text-urgent">{serverNote}</Text> : null}
          <ServerLine health={health} />
        </View>
      </Sheet>
      <Sheet open={confirming} onClose={() => setConfirming(false)} title="처음부터 다시 할까요?">
        <Text className="text-body text-ink-2">{"등록한 가게, 불러온 리뷰, 끝낸 일과 설정을 모두 지워요.\n로그인하면 가게 찾기(지도)부터 다시 해요."}</Text>
        <Text className="mt-2 text-small text-ink-3">팀 목업 가게와 데모 테스트 모드는 그대로 둬요</Text>
        <View className="mt-5 gap-2.5">
          <PrimaryButton testID="start-menu-reset-yes" disabled={resetting} onPress={reset}>
            {resetting ? "지우는 중" : "초기화할게요"}
          </PrimaryButton>
          <SecondaryButton testID="start-menu-reset-no" onPress={() => setConfirming(false)}>
            그만둘게요
          </SecondaryButton>
        </View>
      </Sheet>
    </>
  );
}
