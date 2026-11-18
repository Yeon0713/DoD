import { Redirect, useLocalSearchParams, useRouter } from 'expo-router';
import { ReactNode, useState } from 'react';
import { Image, Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { Icon } from '@/components/Icon';
import { FailNote, JoinPage, Note } from '@/components/join';
import { Txt } from '@/components/Txt';
import { Button } from '@/components/ui';
import { ApiFailure } from '@/lib/api';
import { formatBusinessNo, formatDate, isBusinessNo, isoDate, join, joinState, ownerKey } from '@/lib/join';
import { useSession } from '@/lib/session';
import { colors, radius, space } from '@/theme/tokens';

// 사장님 확인 (이전 앱 OwnerCheck): 사업자등록증에 적힌 번호, 대표자, 개업일자와 사진. 서버가 목업 국세청으로 심사한다.
// 데모 테스트 모드에서는 "시험용 값 넣기"로 그 가게가 통과하는 값을 채운다.

/** 사진 고르기. 웹은 브라우저 파일 창, 앱은 아직 사진 고르기를 넣지 않아 이름만 둔다 */
function pickPhoto(): Promise<{ uri: string | null; name: string } | null> {
  if (Platform.OS !== 'web') return Promise.resolve({ uri: null, name: '사업자등록증.jpg' });
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) return resolve(null);
      const reader = new FileReader();
      reader.onload = () => resolve({ uri: String(reader.result), name: file.name });
      reader.onerror = () => resolve({ uri: null, name: file.name });
      reader.readAsDataURL(file);
    };
    input.click();
  });
}

function Field({ label, hint, children }: { label: string; hint?: string | null; children: ReactNode }) {
  return (
    <View style={{ gap: space.s8 }}>
      <Txt variant="label" style={{ fontFamily: 'NotoSansKR_700Bold' }}>
        {label}
      </Txt>
      {children}
      {hint ? (
        <Txt variant="label" color="urgent" accessibilityRole="alert">
          {hint}
        </Txt>
      ) : null}
    </View>
  );
}

export default function OwnerCheckScreen() {
  const router = useRouter();
  const session = useSession();
  const again = useLocalSearchParams<{ again?: string }>().again === '1';
  const storeId = joinState.check.storeId;
  const [number, setNumber] = useState('');
  const [name, setName] = useState('');
  const [opened, setOpened] = useState('');
  const [photo, setPhoto] = useState<{ uri: string | null; name: string } | null>(null);
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  if (!storeId) return <Redirect href="/join/store" />;
  const numberOk = isBusinessNo(number);
  const date = isoDate(opened);
  const ready = numberOk && name.trim().length > 0 && !!date && !!photo;

  const fillSample = async () => {
    try {
      const s = await join.ownerSample(storeId);
      setNumber(s.business_no);
      setName(s.owner_name);
      setOpened(s.opened_on.replace(/-/g, ''));
      setPhoto({ uri: null, name: s.document ?? '사업자등록증_시험용.jpg' });
      setFailed(null);
    } catch {
      setFailed('이 가게로 통과하는 시험용 값이 없어요');
    }
  };
  const submit = async () => {
    if (!ready || !date || !photo || sending) return;
    setSending(true);
    setFailed(null);
    try {
      const res = await join.ownerSubmit({ business_no: number, owner_name: name.trim(), opened_on: date, document: photo.name, store_id: storeId, owner_key: ownerKey(session) ?? '' });
      joinState.check = { ...joinState.check, checkId: res.check_id };
      router.push(again ? '/join/owner-review?again=1' : '/join/owner-review');
    } catch (e) {
      setFailed(e instanceof ApiFailure ? e.message : '보내지 못했어요. 다시 눌러 주세요');
    } finally {
      setSending(false);
    }
  };

  return (
    <JoinPage
      progress={again ? undefined : 3}
      onBack={() => router.replace(again ? '/join/store-confirm?again=1' : '/join/store-confirm')}
      footer={<Button label={sending ? '보내는 중' : '확인 받기'} disabled={!ready || sending} onPress={() => void submit()} />}
    >
      <Txt variant="display" accessibilityRole="header">
        사장님 확인을 해 주세요
      </Txt>
      <Txt variant="body" color="ink2" style={{ marginTop: space.s4 }}>
        사업자등록증에 적힌 대로 써 주세요
      </Txt>
      <View style={{ marginTop: space.s24, gap: space.s16 }}>
        <Field label="사업자등록번호" hint={number.length === 10 && !numberOk ? '번호를 다시 확인해 주세요' : null}>
          <TextInput
            accessibilityLabel="사업자등록번호"
            value={formatBusinessNo(number)}
            onChangeText={(v) => setNumber(v.replace(/\D/g, '').slice(0, 10))}
            keyboardType="number-pad"
            placeholder="000-00-00000"
            placeholderTextColor={colors.ink3}
            style={styles.input}
          />
        </Field>
        <Field label="대표자 이름">
          <TextInput accessibilityLabel="대표자 이름" value={name} onChangeText={setName} autoComplete="name" placeholder="홍길동" placeholderTextColor={colors.ink3} style={styles.input} />
        </Field>
        <Field label="개업일자" hint={opened.length === 8 && !date ? '날짜를 다시 확인해 주세요' : null}>
          <TextInput
            accessibilityLabel="개업일자"
            value={formatDate(opened)}
            onChangeText={(v) => setOpened(v.replace(/\D/g, '').slice(0, 8))}
            keyboardType="number-pad"
            placeholder="2021.04.01"
            placeholderTextColor={colors.ink3}
            style={styles.input}
          />
        </Field>
        <Field label="사업자등록증 사진">
          <Pressable
            onPress={() => void pickPhoto().then((p) => p && setPhoto(p))}
            accessibilityRole="button"
            accessibilityLabel={photo ? '사업자등록증 사진 다시 고르기' : '사업자등록증 사진 올리기'}
            style={[styles.photo, photo ? { borderColor: colors.brand, backgroundColor: colors.brandSoft } : { borderStyle: 'dashed' }]}
          >
            {photo?.uri ? <Image source={{ uri: photo.uri }} style={{ width: 40, height: 40, borderRadius: 8 }} /> : <Icon name={photo ? 'check' : 'image'} size={24} color={photo ? 'brand' : 'ink2'} />}
            <Txt variant="body" color={photo ? 'brand' : 'ink2'} style={[{ flex: 1 }, photo && { fontFamily: 'NotoSansKR_700Bold' }]}>
              {photo ? '사진을 올렸어요' : '사진 올리기'}
            </Txt>
            {photo ? (
              <Txt variant="label" color="ink2">
                다시 고르기
              </Txt>
            ) : null}
          </Pressable>
        </Field>
      </View>
      <View style={{ marginTop: space.s16 }}>
        <Note>사장님 확인에만 써요</Note>
      </View>
      {session.demo ? (
        <Pressable onPress={() => void fillSample()} accessibilityRole="button" style={{ marginTop: space.s16, minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' }}>
          <Txt variant="label" color="brand" style={{ textDecorationLine: 'underline', fontFamily: 'NotoSansKR_700Bold' }}>
            시험용 값 넣기
          </Txt>
        </Pressable>
      ) : null}
      {failed ? (
        <View style={{ marginTop: space.s12 }}>
          <FailNote title="확인을 보내지 못했어요" sub={failed} />
        </View>
      ) : null}
    </JoinPage>
  );
}

const styles = StyleSheet.create({
  input: { height: 56, borderRadius: radius.button, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface, paddingHorizontal: space.s16, fontSize: 18, fontFamily: 'NotoSansKR_500Medium', color: colors.ink },
  photo: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: space.s12, paddingHorizontal: space.s16, paddingVertical: space.s12, borderRadius: radius.button, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface },
});
