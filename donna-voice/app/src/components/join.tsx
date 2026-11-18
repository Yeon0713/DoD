// 가입 흐름 화면의 부품 (이전 앱 mobile/src/components/ui/sub.tsx, start/HoursEditor.tsx, start/DemoMenu.tsx 에서 옮김).
// 모양은 v0.2.1 토큰을 쓴다: 바탕 paper, 카드 surface + line, 보조 글자 ink-2, 간격 4·8·12·16·24.
import { useRouter } from 'expo-router';
import { ReactNode, useEffect, useState } from 'react';
import { Image, Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon, IconName } from '@/components/Icon';
import { Txt } from '@/components/Txt';
import { Button, Switch } from '@/components/ui';
import { BASE } from '@/lib/api';
import { serverUp } from '@/lib/join';
import { useLayout } from '@/lib/layout';
import { useSession } from '@/lib/session';
import { colors, radius, space } from '@/theme/tokens';

export const DONNA = {
  'b1-1': require('@/assets/donna/b1-1.png'),
  'b1-2': require('@/assets/donna/b1-2.png'),
  'b2-1': require('@/assets/donna/b2-1.png'),
  'b3-1': require('@/assets/donna/b3-1.png'),
  'b4-0': require('@/assets/donna/b4-0.png'),
  'q-arms': require('@/assets/donna/q-arms.png'),
  'q-clipboard': require('@/assets/donna/q-clipboard.png'),
  'q-laptop': require('@/assets/donna/q-laptop.png'),
  'q-scratch': require('@/assets/donna/q-scratch.png'),
  'q-shrug': require('@/assets/donna/q-shrug.png'),
} as const;
export type DonnaPose = keyof typeof DONNA;

export function DonnaPic({ img, size }: { img: DonnaPose; size: number }) {
  return <Image source={DONNA[img]} style={{ width: size, height: size }} resizeMode="contain" accessibilityIgnoresInvertColors />;
}

/** 진행 막대: 한 칸씩, 지난 칸은 갈색. 숫자는 쓰지 않는다 */
function Progress({ total, done }: { total: number; done: number }) {
  return (
    <View style={styles.progress} accessibilityLabel={`${total}단계 가운데 ${done}단계`}>
      {Array.from({ length: total }, (_, i) => (
        <View key={i} style={[styles.progressCell, { backgroundColor: i < done ? colors.brand : colors.line }]} />
      ))}
    </View>
  );
}

/** 가입 흐름 한 화면: 위에 뒤로와 진행 막대, 가운데 밀리는 내용, 아래에 붙는 버튼. */
export function JoinPage({
  children,
  footer,
  onBack,
  progress,
  center,
}: {
  children: ReactNode;
  footer?: ReactNode;
  onBack?: () => void;
  progress?: number;
  /** 내용을 화면 가운데에 (기다리는 화면, 다 됐어요 화면) */
  center?: boolean;
}) {
  const insets = useSafeAreaInsets();
  const { margin, contentMax, scale } = useLayout();
  const column = { width: '100%' as const, maxWidth: contentMax };
  return (
    <View style={{ flex: 1, backgroundColor: colors.paper, paddingTop: insets.top }}>
      <View style={[styles.head, { paddingHorizontal: margin - 10 }]}>
        {onBack ? (
          <Pressable onPress={onBack} accessibilityRole="button" accessibilityLabel="뒤로" style={styles.back}>
            <Icon name="chevronLeft" size={Math.round(26 * scale)} color="ink" />
          </Pressable>
        ) : (
          <View style={styles.back} />
        )}
        {progress !== undefined ? <Progress total={6} done={progress} /> : null}
      </View>
      <ScrollView contentContainerStyle={{ flexGrow: 1, paddingHorizontal: margin, paddingTop: space.s8, paddingBottom: space.s16, alignItems: 'center' }} keyboardShouldPersistTaps="handled">
        <View style={[column, { flexGrow: 1 }, center && { justifyContent: 'center' }]}>{children}</View>
      </ScrollView>
      {footer ? (
        <View style={{ paddingHorizontal: margin, paddingTop: space.s16, paddingBottom: Math.max(insets.bottom, space.s24), alignItems: 'center' }}>
          <View style={[column, { gap: space.s8 }]}>{footer}</View>
        </View>
      ) : null}
    </View>
  );
}

/** 큰 제목 (두 줄까지) + 오른쪽 도나 + 아래 한 줄 설명 */
export function TitleWithDonna({ title, sub, img = 'b1-1' }: { title: string; sub?: string; img?: DonnaPose }) {
  const { scale } = useLayout();
  return (
    <View style={{ gap: space.s4 }}>
      <View style={styles.titleRow}>
        <Txt variant="display" style={{ flex: 1, paddingTop: space.s12 }} accessibilityRole="header">
          {title}
        </Txt>
        <DonnaPic img={img} size={Math.round(88 * scale)} />
      </View>
      {sub ? (
        <Txt variant="body" color="ink2">
          {sub}
        </Txt>
      ) : null}
    </View>
  );
}

/** 방패 아이콘과 한 줄: 무엇을 하지 않는지 (안심) */
export function Note({ children, icon = 'shield' }: { children: string; icon?: IconName }) {
  return (
    <View style={styles.note}>
      <View style={{ paddingTop: 1 }}>
        <Icon name={icon} size={20} color="done" />
      </View>
      <Txt variant="label" color="ink2" style={{ flex: 1 }}>
        {children}
      </Txt>
    </View>
  );
}

/** 실패한 까닭 한 덩이 */
export function FailNote({ title, sub }: { title: string; sub?: string }) {
  return (
    <View style={styles.fail} accessibilityRole="alert">
      <Icon name="refresh" size={20} color="urgent" />
      <View style={{ flex: 1 }}>
        <Txt variant="bodyStrong" color="urgent">
          {title}
        </Txt>
        {sub ? (
          <Txt variant="label" color="ink2">
            {sub}
          </Txt>
        ) : null}
      </View>
    </View>
  );
}

/** 가운데 도나 + 제목 + 설명 (기다리는 화면, 다 됐어요 화면) */
export function CenterMessage({ img, title, sub, children }: { img: DonnaPose; title: string; sub?: string; children?: ReactNode }) {
  const { scale } = useLayout();
  return (
    <View style={{ alignItems: 'center', gap: space.s8 }} accessibilityLiveRegion="polite">
      <DonnaPic img={img} size={Math.round(180 * scale)} />
      <Txt variant="display" center>
        {title}
      </Txt>
      {sub ? (
        <Txt variant="body" color="ink2" center>
          {sub}
        </Txt>
      ) : null}
      {children}
    </View>
  );
}

/** 아래에서 올라오는 창 */
export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const insets = useSafeAreaInsets();
  const { margin, contentMax } = useLayout();
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel="닫기" />
      <View style={[styles.sheet, { paddingHorizontal: margin, paddingBottom: Math.max(insets.bottom, space.s24) }]}>
        <View style={{ width: '100%', maxWidth: contentMax, alignSelf: 'center', gap: space.s16 }}>
          <Txt variant="title">{title}</Txt>
          {children}
        </View>
      </View>
    </Modal>
  );
}

/** 시작 화면의 메뉴(☰) 버튼과 메뉴 창. 시험·시연용 스위치를 모아 둔다 (이전 앱 DemoMenu).
 *  - 데모 테스트 모드: 켜면 "네이버로 시작하기"가 서버의 임시 네이버 로그인으로 가서 DB 테스트 계정(dona_demo 등)으로 들어간다
 *  - 처음 상태로: 이 기기의 로그인과 가입 기록을 지운다 (서버의 등록 기록은 지우지 않는다. 데모 계정은 탈퇴로 다시 가입부터 한다) */
export function DemoMenuButton() {
  const router = useRouter();
  const session = useSession();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [server, setServer] = useState<boolean | null>(null);
  useEffect(() => {
    if (!open) return;
    setServer(null);
    serverUp().then(setServer);
  }, [open]);
  const where = BASE.replace(/^https?:\/\//, '');
  return (
    <>
      <Pressable onPress={() => setOpen(true)} accessibilityRole="button" accessibilityLabel="메뉴" hitSlop={8} style={styles.back}>
        <Icon name="menu" size={24} color="ink" />
      </Pressable>
      <Sheet open={open && !confirming} onClose={() => setOpen(false)} title="메뉴">
        <View style={styles.menuItem}>
          <Icon name="user" size={24} color="brand" />
          <View style={{ flex: 1 }}>
            <Txt variant="bodyStrong">데모 테스트 모드</Txt>
            <Txt variant="label" color="ink2">
              켜면 네이버 로그인에서 테스트 계정을 골라 들어가요
            </Txt>
          </View>
          <Switch on={session.demo} onChange={session.setDemo} label="데모 테스트 모드" />
        </View>
        <Pressable onPress={() => setConfirming(true)} accessibilityRole="button" style={styles.menuItem}>
          <Icon name="refresh" size={24} color="urgent" />
          <View style={{ flex: 1 }}>
            <Txt variant="bodyStrong">처음 상태로</Txt>
            <Txt variant="label" color="ink2">
              이 기기의 로그인과 가입 기록을 지워요
            </Txt>
          </View>
          <Icon name="chevronRight" size={20} color="ink2" />
        </Pressable>
        <Txt variant="label" color={server === false ? 'urgent' : 'ink2'}>
          {server === null ? `서버 확인 중 · ${where}` : server ? `서버에 연결됐어요 · ${where}` : `서버에 닿지 않아요 · ${where}`}
        </Txt>
      </Sheet>
      <Sheet open={confirming} onClose={() => setConfirming(false)} title="처음부터 다시 할까요?">
        <Txt variant="body" color="ink2">
          이 기기의 로그인과 가입 기록을 지워요. 데모 테스트 모드는 그대로 둬요.
        </Txt>
        <View style={{ gap: space.s8 }}>
          <Button
            label="처음 상태로 돌릴게요"
            onPress={() => {
              session.resetDevice();
              setConfirming(false);
              setOpen(false);
              router.replace('/start');
            }}
          />
          <Button kind="outline" label="그만둘게요" onPress={() => setConfirming(false)} />
        </View>
      </Sheet>
    </>
  );
}

/** 위 줄 오른쪽: 데모 테스트 모드 표시와 메뉴 버튼 (다시 왔을 때 로그인 화면) */
export function DemoMenuBar() {
  const { demo } = useSession();
  return (
    <View style={styles.menuBar}>
      {demo ? (
        <View style={styles.badge}>
          <Txt variant="label" color="brand" style={styles.bold}>
            데모 테스트 모드
          </Txt>
        </View>
      ) : null}
      <DemoMenuButton />
    </View>
  );
}

const styles = StyleSheet.create({
  bold: { fontFamily: 'NotoSansKR_700Bold' },
  head: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: space.s8 },
  back: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  progress: { flex: 1, flexDirection: 'row', gap: space.s4, paddingRight: space.s8 },
  progressCell: { flex: 1, height: 6, borderRadius: 3 },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', gap: space.s8 },
  note: { flexDirection: 'row', alignItems: 'flex-start', gap: space.s8 },
  fail: { flexDirection: 'row', alignItems: 'flex-start', gap: space.s8, padding: space.s12, borderRadius: radius.tile, backgroundColor: colors.urgentSoft },
  backdrop: { flex: 1, backgroundColor: 'rgba(43, 26, 15, 0.4)' },
  sheet: { backgroundColor: colors.paper, borderTopLeftRadius: radius.card, borderTopRightRadius: radius.card, paddingTop: space.s24 },
  menuBar: { minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: space.s8 },
  badge: { paddingHorizontal: space.s12, paddingVertical: space.s4, borderRadius: radius.pill, backgroundColor: colors.brandSoft },
  menuItem: { minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: space.s12, padding: space.s16, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.surface },
});
