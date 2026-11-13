// 앱의 모든 글자가 쓰는 Text. 한국어 문장이 단어 중간에서 끊기지 않게 한다 (Next.js 판의 word-break: keep-all 자리).
// iOS는 lineBreakStrategyIOS, 웹은 global.css의 word-break: keep-all. 안드로이드는 같은 설정이 없어 기본 줄바꿈을 쓴다.
//
// 제목과 본문(text-display, text-title, text-body, text-label, text-small, text-button)은 줄 나누기 규칙
// (lib/titleBreak.ts, docs/title-line-break.md)을 따른다: 먼저 한 줄로 그려 보고, 화면 폭에 들어가면 한 줄로 둔다.
// 넘치면 그 자리의 실제 폭으로 뜻의 덩어리를 따져 줄을 나눈다 ("문자로 온 숫자 6자리를 / 입력해주세요.").
// 글에 적어 둔 줄 바꿈(\n)은 쓰지 않고 규칙으로 다시 나눈다.
// 단, 80자가 넘는 글(손님 리뷰, 답글 초안처럼 앱이 쓰지 않은 글)과 줄 수를 정해 둔 글(numberOfLines)은 그대로 둔다.
import { useState } from "react";
import { StyleSheet, Text as RNText, useWindowDimensions, type LayoutChangeEvent, type TextProps } from "react-native";
import { breakTitle } from "@/lib/titleBreak";
import tokens from "@/theme/tokens.json";

type Props = TextProps & { className?: string };
type TitleFont = { size: number; lineHeight: number };

// 규칙을 쓰는 글꼴 (tailwind.config.js 의 text-* 와 같은 값)
const TITLE_FONTS: [RegExp, TitleFont][] = (["display", "title", "body", "label", "small", "button"] as const).map((name) => [
  new RegExp(`(^|\\s)text-${name}(\\s|$)`),
  { size: tokens.typography[name].size, lineHeight: tokens.typography[name].lineHeight },
]);
// 이보다 긴 글은 앱이 쓴 짧은 글이 아니라고 보고(손님 리뷰, 답글 초안) 적어 둔 줄 바꿈을 그대로 쓴다
const MAX_RULE_LENGTH = 80;

function titleFont({ className, style }: Props): TitleFont | null {
  if (!className) return null;
  const own = StyleSheet.flatten(style);
  for (const [pattern, font] of TITLE_FONTS) {
    if (pattern.test(className)) return { size: own?.fontSize ?? font.size, lineHeight: own?.lineHeight ?? font.lineHeight };
  }
  return null;
}

export function Text(props: Props) {
  const font = titleFont(props);
  if (font && typeof props.children === "string" && !props.numberOfLines && props.children.length <= MAX_RULE_LENGTH) {
    return <Title {...props} text={props.children} font={font} />;
  }
  return <RNText lineBreakStrategyIOS="hangul-word" {...props} />;
}

/** 제목·본문: 한 줄에 들어가면 한 줄로, 넘치면 줄 나누기 규칙으로 */
function Title({ text, font, onLayout, ...rest }: Props & { text: string; font: TitleFont }) {
  // 화면 폭이 바뀌면(회전, 창 크기) 다시 한 줄로 그려 본다
  const { width: screen } = useWindowDimensions();
  const [broken, setBroken] = useState<{ screen: number; text: string; lines: string } | null>(null);
  const done = broken?.screen === screen && broken.text === text;
  const oneLine = text.replace(/\s*\n\s*/g, " ").trim();

  const check = (e: LayoutChangeEvent) => {
    onLayout?.(e);
    const { width, height } = e.nativeEvent.layout;
    // 한 줄 높이의 1.5배를 넘으면 한 줄에 다 들어가지 않은 것. 넘칠 때 이 글의 폭은 놓인 자리의 폭이다.
    // 글자 폭 어림이 조금 틀려도 넘치지 않게 2% 덜 쓴다.
    if (!done && height > font.lineHeight * 1.5 && width > 0) setBroken({ screen, text, lines: breakTitle(oneLine, (width * 0.98) / font.size) });
  };

  return (
    <RNText lineBreakStrategyIOS="hangul-word" {...rest} onLayout={check}>
      {done ? broken.lines : oneLine}
    </RNText>
  );
}
