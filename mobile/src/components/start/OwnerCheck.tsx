// 사장님 확인 (가입 흐름: 이 가게가 맞나요? → 사장님 확인 → 심사 → 가게 정보 확인).
// 고른 가게의 사장님인지 사업자등록증으로 확인받는다. 심사가 끝나야 계정과 가게가 이어진다 (server/app/modules/owner_check, 지금은 목업 국세청).
// 설정 "우리 가게 다시 찾기"(?again=1)에서도 같은 확인을 거친다.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { Redirect, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Image, Pressable, TextInput, View } from "react-native";
import { Icon } from "@/components/icons/Icon";
import { back, go } from "@/components/ui/nav";
import { PrimaryButton, SecondaryButton, TextLink } from "@/components/ui/parts";
import { CenterMessage, FailNote, Note, SubPage } from "@/components/ui/sub";
import { Text } from "@/components/ui/Text";
import { account } from "@/lib/account";
import { ApiFailure, USE_MOCK } from "@/lib/api";
import { flashToast } from "@/lib/localStore";
import { demoMode } from "@/lib/naverDemo";
import { formatBusinessNo, formatDate, isBusinessNo, isoDate, ownerCheck, ownerCheckSample, readOwnerCheck, submitOwnerCheck } from "@/lib/ownerCheck";
import tokens from "@/theme/tokens.json";
import { param, STEPS } from "./flow";
import { ownerKey } from "./StoreRegister";

const C = tokens.colors;
const OWNER_STEP = 3; // 진행 막대: 가게 찾기, 가게 확인, 사장님 확인, ...

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string | null }) {
  return (
    <View className="gap-1.5">
      <Text className="text-label font-bold text-ink">{label}</Text>
      {children}
      {hint ? (
        <Text accessibilityRole="alert" className="text-small text-urgent">
          {hint}
        </Text>
      ) : null}
    </View>
  );
}

const INPUT = "h-14 rounded-button border border-line bg-surface px-4 text-body text-ink";

/** 사장님 확인: 사업자등록증에 적힌 번호·대표자·개업일자와 사업자등록증 사진 */
export function OwnerCheckScreen() {
  const again = param(useLocalSearchParams<{ again?: string }>().again) === "1";
  // 이 가게가 맞나요? 에서 등록한 가게 (사장님 확인이 끝나야 이 기기의 가게로 바꾼다)
  const storeId = ownerCheck.useValue().storeId;
  const demo = demoMode.useValue().on;
  const [number, setNumber] = useState("");
  const [name, setName] = useState("");
  const [opened, setOpened] = useState("");
  const [photo, setPhoto] = useState<{ uri: string | null; name: string } | null>(null);
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  if (!storeId) return <Redirect href="/start/store" />;
  const numberOk = isBusinessNo(number);
  const date = isoDate(opened);
  const ready = numberOk && name.trim().length > 0 && !!date && !!photo;

  const pickPhoto = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.7 });
    const asset = !res.canceled ? res.assets[0] : undefined;
    if (asset) setPhoto({ uri: asset.uri, name: asset.fileName ?? "사업자등록증.jpg" });
  };

  const fillSample = async () => {
    const s = await ownerCheckSample(storeId);
    if (!s) {
      setFailed("이 가게로 통과하는 시험용 값이 없어요");
      return;
    }
    setNumber(s.business_no);
    setName(s.owner_name);
    setOpened(s.opened_on.replace(/-/g, ""));
    setPhoto({ uri: null, name: s.document ?? "사업자등록증_시험용.jpg" });
    setFailed(null);
  };

  const submit = async () => {
    if (!ready || !date || !photo) return;
    setSending(true);
    setFailed(null);
    try {
      const res = await submitOwnerCheck(storeId, ownerKey() ?? "", { business_no: number, owner_name: name.trim(), opened_on: date, document: photo.name });
      ownerCheck.write({ checkId: res.check_id, storeId, again });
      go(again ? "/start/owner-review?again=1" : "/start/owner-review");
    } catch (e) {
      setFailed(e instanceof ApiFailure ? e.message : "보내지 못했어요. 다시 눌러 주세요");
    } finally {
      setSending(false);
    }
  };

  return (
    <SubPage
      progress={again ? undefined : { total: STEPS, done: OWNER_STEP }}
      onBack={() => back(again ? "/start/store-confirm?again=1" : "/start/store-confirm")}
      footer={
        <PrimaryButton testID="owner-check-send" onPress={submit} disabled={!ready || sending}>
          {sending ? "보내는 중" : "확인 받기"}
        </PrimaryButton>
      }
    >
      <Text className="text-display text-ink" accessibilityRole="header">
        사장님 확인을 해 주세요
      </Text>
      <Text className="mt-1.5 text-body text-ink-2">사업자등록증에 적힌 대로 써 주세요</Text>

      <View className="mt-6 gap-5">
        <Field label="사업자등록번호" hint={number.length === 10 && !numberOk ? "번호를 다시 확인해 주세요" : null}>
          <TextInput
            testID="owner-business-no"
            accessibilityLabel="사업자등록번호"
            value={formatBusinessNo(number)}
            onChangeText={(v) => setNumber(v.replace(/\D/g, "").slice(0, 10))}
            keyboardType="number-pad"
            placeholder="000-00-00000"
            placeholderTextColor={C["ink-3"]}
            className={INPUT}
          />
        </Field>
        <Field label="대표자 이름">
          <TextInput
            testID="owner-name"
            accessibilityLabel="대표자 이름"
            value={name}
            onChangeText={setName}
            autoComplete="name"
            placeholder="홍길동"
            placeholderTextColor={C["ink-3"]}
            className={INPUT}
          />
        </Field>
        <Field label="개업일자" hint={opened.length === 8 && !date ? "날짜를 다시 확인해 주세요" : null}>
          <TextInput
            testID="owner-opened-on"
            accessibilityLabel="개업일자"
            value={formatDate(opened)}
            onChangeText={(v) => setOpened(v.replace(/\D/g, "").slice(0, 8))}
            keyboardType="number-pad"
            placeholder="2021.04.01"
            placeholderTextColor={C["ink-3"]}
            className={INPUT}
          />
        </Field>
        <Field label="사업자등록증 사진">
          <Pressable
            testID="owner-photo"
            accessibilityRole="button"
            accessibilityLabel={photo ? "사업자등록증 사진 다시 고르기" : "사업자등록증 사진 올리기"}
            onPress={pickPhoto}
            className={`min-h-14 flex-row items-center gap-3 rounded-button border px-4 py-3 ${photo ? "border-brand bg-brand-soft" : "border-dashed border-line bg-surface active:bg-paper"}`}
          >
            {photo?.uri ? <Image source={{ uri: photo.uri }} style={{ width: 40, height: 40, borderRadius: 8 }} accessibilityIgnoresInvertColors /> : <Icon name={photo ? "check" : "image"} size={24} color={photo ? C.brand : C["ink-2"]} />}
            <Text className={`flex-1 text-body ${photo ? "font-bold text-brand" : "text-ink-2"}`}>{photo ? "사진을 올렸어요" : "사진 올리기"}</Text>
            {photo ? <Text className="text-small text-ink-3">다시 고르기</Text> : null}
          </Pressable>
        </Field>
      </View>

      <View className="mt-4">
        <Note icon="shield">사장님 확인에만 써요</Note>
      </View>
      {demo ? (
        <View className="mt-4 items-start">
          <TextLink onPress={() => void fillSample()}>시험용 값 넣기</TextLink>
        </View>
      ) : null}
      {failed ? <FailNote title="확인을 보내지 못했어요" sub={failed} icon="refresh" /> : null}
    </SubPage>
  );
}

/** 심사: 결과가 나올 때까지 기다린다. 승인이면 가게 정보 확인으로, 보류면 까닭과 다시 쓰기 */
export function OwnerReviewScreen() {
  const againParam = param(useLocalSearchParams<{ again?: string }>().again) === "1";
  const { checkId, storeId, again: savedAgain } = ownerCheck.useValue();
  const again = againParam || savedAgain;
  const qc = useQueryClient();
  const result = useQuery({
    queryKey: ["owner-check", checkId],
    queryFn: () => readOwnerCheck(checkId as string, storeId as string),
    enabled: !!checkId && !!storeId,
    refetchInterval: (q) => (q.state.data?.status === "reviewing" || !q.state.data ? 1500 : false),
    retry: 1,
  });

  if (!checkId || !storeId) return <Redirect href="/start/owner-check" />;
  const r = result.data;
  const rewrite = () => back(again ? "/start/owner-check?again=1" : "/start/owner-check");

  const next = () => {
    // 승인된 가게로 이 기기의 가게를 바꾸고, 앞서 본 다른 가게 데이터는 지운다 (앱 안 목업 모드는 가게를 바꾸지 않는다)
    if (!USE_MOCK) {
      account.write({ storeId });
      qc.clear();
    }
    ownerCheck.reset();
    if (again) {
      flashToast("우리 가게를 바꿨어요");
      back("/settings");
    } else go("/start/naver-confirm");
  };

  if (result.isError) {
    return (
      <SubPage progress={again ? undefined : { total: STEPS, done: OWNER_STEP }} onBack={rewrite} footer={<PrimaryButton onPress={() => result.refetch()}>다시 보기</PrimaryButton>}>
        <FailNote title="심사 결과를 읽지 못했어요" />
      </SubPage>
    );
  }

  if (!r || r.status === "reviewing") {
    return (
      <SubPage progress={again ? undefined : { total: STEPS, done: OWNER_STEP }} onBack={rewrite}>
        <View testID="owner-reviewing" className="flex-1" accessibilityLiveRegion="polite">
          <CenterMessage img="q-clipboard" title="확인하고 있어요" sub="사업자등록증을 보고 있어요. 잠깐만 기다려 주세요">
            <View className="mt-6">
              <ActivityIndicator color={C.brand} size="large" />
            </View>
          </CenterMessage>
        </View>
      </SubPage>
    );
  }

  if (r.status === "approved") {
    return (
      <SubPage
        progress={again ? undefined : { total: STEPS, done: OWNER_STEP }}
        onBack={next}
        footer={
          <PrimaryButton testID="owner-approved-next" onPress={next}>
            다음
          </PrimaryButton>
        }
      >
        <View testID="owner-approved" className="flex-1">
          <CenterMessage img="b1-2" title="사장님 확인이 끝났어요" sub="이제 이 계정으로 우리 가게를 볼 수 있어요" />
        </View>
      </SubPage>
    );
  }

  return (
    <SubPage
      progress={again ? undefined : { total: STEPS, done: OWNER_STEP }}
      onBack={rewrite}
      footer={
        <>
          <PrimaryButton testID="owner-held-rewrite" onPress={rewrite}>
            다시 쓰기
          </PrimaryButton>
          {r.reason_code === "OTHER_STORE" || r.reason_code === "TAKEN" ? (
            <SecondaryButton onPress={() => go(again ? "/start/store?again=1" : "/start/store")}>가게 다시 찾기</SecondaryButton>
          ) : null}
        </>
      }
    >
      <View testID="owner-held" className="flex-1">
        <CenterMessage img="q-shrug" title={r.reason_title ?? "확인하지 못했어요"} sub={r.reason_sub ?? "다시 써 주세요"} />
      </View>
    </SubPage>
  );
}
