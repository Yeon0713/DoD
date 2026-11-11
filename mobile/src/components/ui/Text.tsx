// 앱의 모든 글자가 쓰는 Text. 한국어 문장이 단어 중간에서 끊기지 않게 한다 (Next.js 판의 word-break: keep-all 자리).
// iOS는 lineBreakStrategyIOS, 웹은 global.css의 word-break: keep-all. 안드로이드는 같은 설정이 없어 기본 줄바꿈을 쓴다.
import { Text as RNText, type TextProps } from "react-native";

export function Text(props: TextProps) {
  return <RNText lineBreakStrategyIOS="hangul-word" {...props} />;
}
