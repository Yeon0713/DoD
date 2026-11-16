import { createContext, ReactNode, useContext, useMemo } from 'react';
import { useWindowDimensions } from 'react-native';

import { breakpoints, typeScale, TypeName } from '@/theme/tokens';

export type Mode = 'phone' | 'tabletPortrait' | 'tabletWide';

type Layout = {
  mode: Mode;
  /** 태블릿 가로: 왼쪽에 도나와 듣기 알약, 오른쪽에 대화 */
  wide: boolean;
  tablet: boolean;
  width: number;
  height: number;
  /** 화면 양옆 여백 */
  margin: number;
  /** 한 줄기일 때 내용의 최대 폭 */
  contentMax: number;
  /** 도나 크기. 한 화면 크기 안에서는 어느 화면에서나 같다 */
  donna: number;
  /** 아이콘 칸, 버튼처럼 손이 닿는 것의 배율 */
  scale: number;
  type: (typeof typeScale)['phone'];
};

const LayoutContext = createContext<Layout | null>(null);

export function LayoutProvider({ children }: { children: ReactNode }) {
  const { width, height } = useWindowDimensions();
  const value = useMemo<Layout>(() => {
    const mode: Mode = width >= breakpoints.wide ? 'tabletWide' : width >= breakpoints.tablet ? 'tabletPortrait' : 'phone';
    const tablet = mode !== 'phone';
    return {
      mode,
      wide: mode === 'tabletWide',
      tablet,
      width,
      height,
      margin: tablet ? 32 : 24,
      contentMax: 600,
      donna: mode === 'phone' ? 144 : mode === 'tabletPortrait' ? 192 : 240,
      scale: tablet ? 1.2 : 1,
      type: tablet ? typeScale.tablet : typeScale.phone,
    };
  }, [width, height]);
  return <LayoutContext.Provider value={value}>{children}</LayoutContext.Provider>;
}

export function useLayout(): Layout {
  const v = useContext(LayoutContext);
  if (!v) throw new Error('LayoutProvider가 없습니다');
  return v;
}

export function useType(name: TypeName) {
  return useLayout().type[name];
}
