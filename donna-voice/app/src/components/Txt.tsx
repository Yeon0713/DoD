import { Platform, Text, TextProps } from 'react-native';

import { useLayout } from '@/lib/layout';
import { ColorName, colors, TypeName } from '@/theme/tokens';

type Props = TextProps & { variant?: TypeName; color?: ColorName; center?: boolean };

// 한글은 낱말 가운데서 줄이 바뀌면 읽기 어렵다. 띄어쓰기에서만 줄을 바꾼다.
const KEEP_WORDS = Platform.OS === 'web' ? ({ wordBreak: 'keep-all' } as object) : null;

/** 글자는 항상 이 부품으로 쓴다. 크기와 굵기는 variant, 색은 color 로만 고른다. */
export function Txt({ variant = 'body', color = 'ink', center, style, ...rest }: Props) {
  const { type } = useLayout();
  return (
    <Text
      lineBreakStrategyIOS="hangul-word"
      {...rest}
      style={[type[variant], { color: colors[color] }, KEEP_WORDS, center && { textAlign: 'center' }, style]}
    />
  );
}
