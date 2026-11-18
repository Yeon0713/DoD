import { Redirect, useRouter } from 'expo-router';
import { Image, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DemoMenuButton } from '@/components/join';
import { Tagline } from '@/components/motion';
import { FeatureIcon, FeatureIconName, GreenUnderline } from '@/components/startArt';
import { Button } from '@/components/ui';
import { useSession } from '@/lib/session';
import { colors, space } from '@/theme/tokens';

// 시작 (Figma 10 · 시안 v10 › 10-s1b · 시작 · 아이콘 배경 없는 버전, node 355:2, 이전 앱 IntroScreen).
// 위: 가운데 도나 로고와 오른쪽 메뉴(☰, 데모 테스트 모드), 한 줄 소개. 가운데: 도나와 "매장 운영, 도나가 먼저 챙겨요"(도나 밑에 초록 밑줄).
// 아래: 도나가 하는 일 4가지(아이콘 48, 바탕 없음), "도나를 비서로 영입하러 가기 >". 본문은 위아래로 고르게 벌린다.
/** Figma 10-s1b 의 상태 표시줄 칸 (44). 기기에서는 상태 표시줄 높이가 더 크면 그것을 쓴다 */
const STATUS_BAR = 44;

const FEATURES: { icon: FeatureIconName; title: string; sub: string }[] = [
  { icon: 'revisit', title: '고객 재방문 유도', sub: '재방문 시점에 맞춘 리뷰 답변 예약' },
  { icon: 'menuOrder', title: '메뉴판 순서 재배치', sub: '매출·계절·행사에 맞는 메뉴를 상단에' },
  { icon: 'insta', title: '상황 맞춤 인스타 홍보', sub: '계절·경기에 맞는 홍보 이미지 제작·공유' },
  { icon: 'badReview', title: '부정 리뷰 기반 매장 개선', sub: '불만 리뷰에서 개선할 점 발견' },
];

export default function StartScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { signedIn, demo } = useSession();
  if (signedIn) return <Redirect href="/" />;
  return (
    <View style={[styles.screen, { paddingTop: Math.max(insets.top, STATUS_BAR) }]}>
      <View style={[styles.body, { paddingBottom: Math.max(insets.bottom, 28) }]}>
        <View style={{ alignItems: 'center', width: '100%' }}>
          <View style={styles.logoRow}>
            <Image source={require('@/assets/images/donna-logo.png')} style={{ width: 132, height: 44 }} resizeMode="contain" accessibilityLabel="도나" />
            {demo ? (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>DEMO</Text>
              </View>
            ) : null}
            <View style={styles.menu}>
              <DemoMenuButton />
            </View>
          </View>
          <Tagline />
        </View>

        <View style={{ alignItems: 'center', gap: space.s4, width: '100%' }}>
          <Image source={require('@/assets/donna/b4-0.png')} style={{ width: 168, height: 168 }} resizeMode="contain" />
          <View style={styles.titleRow} accessibilityRole="header" accessibilityLabel="매장 운영, 도나가 먼저 챙겨요">
            <Text style={styles.title}>매장 운영,</Text>
            <View style={{ flexDirection: 'row', alignItems: 'baseline' }}>
              <View>
                <View pointerEvents="none" style={styles.underline}>
                  <GreenUnderline />
                </View>
                <Text style={styles.title}>도나</Text>
              </View>
              <Text style={styles.title}>가 먼저 챙겨요</Text>
            </View>
          </View>
        </View>

        <View style={{ width: '100%' }}>
          {FEATURES.map((f, i) => (
            <View key={f.title} style={[styles.feature, i < FEATURES.length - 1 && styles.featureRule]}>
              <FeatureIcon name={f.icon} size={48} />
              <View style={{ flex: 1 }}>
                <Text style={styles.featureTitle}>{f.title}</Text>
                <Text style={styles.featureSub}>{f.sub}</Text>
              </View>
            </View>
          ))}
        </View>

        <View style={{ width: '100%' }}>
          <Button label="도나를 비서로 영입하러 가기" chevron onPress={() => router.push('/login')} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.paper },
  body: { flex: 1, alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: space.s24 },
  logoRow: { height: 44, width: '100%', alignItems: 'center', justifyContent: 'center' },
  // 메뉴 버튼(누르는 곳 44)의 아이콘이 오른쪽 여백 선에 오도록 10 밖으로 (Figma right -10)
  menu: { position: 'absolute', right: -10, top: 0 },
  // 데모 테스트 모드 표시: 10-s1b 배치를 밀지 않게 로고 줄 왼쪽 끝에 띄운다 (시안에는 없는 시험용 표시)
  badge: { position: 'absolute', left: 0, top: 10, paddingHorizontal: space.s8, paddingVertical: 2, borderRadius: 999, backgroundColor: colors.brandSoft },
  badgeText: { fontFamily: 'NotoSansKR_500Medium', fontSize: 14, lineHeight: 20, color: colors.brand },
  titleRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'center', columnGap: 6 },
  title: { fontFamily: 'NotoSansKR_700Bold', fontSize: 22, lineHeight: 31, letterSpacing: -0.22, color: colors.ink },
  // Figma 강조 밑줄: 47 × 8, 글자 왼쪽에서 3 앞, 위에서 25
  underline: { position: 'absolute', left: -3, top: 25 },
  feature: { flexDirection: 'row', alignItems: 'center', gap: space.s16, paddingVertical: space.s12 },
  featureRule: { borderBottomWidth: 1, borderBottomColor: colors.line },
  featureTitle: { fontFamily: 'NotoSansKR_700Bold', fontSize: 18, lineHeight: 26, color: colors.ink },
  featureSub: { fontFamily: 'NotoSansKR_500Medium', fontSize: 15, lineHeight: 22, letterSpacing: -0.15, color: colors.ink3 },
});
