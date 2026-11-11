// 네이버 공식 N 로고. 출처: Figma Community "카카오, 네이버 로그인 디자인 가이드" (네이버 로고 컴포넌트).
// 글자 N으로 대신 쓰지 않는다. 네이버 로그인 버튼은 초록 바탕(#03C75A)에 흰 로고와 흰 글자.
import Svg, { Path } from "react-native-svg";

export function NaverLogo({ size = 16, color = "#FFFFFF" }: { size?: number; color?: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20" fill="none">
      <Path d="M13.5614 10.7033L6.14609 0H0V20H6.43861V9.295L13.8539 20H20V0H13.5614V10.7033Z" fill={color} />
    </Svg>
  );
}
