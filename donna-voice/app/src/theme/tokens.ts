// 디자인 토큰. Figma `DoNA 03 · 토큰`과 v0.2.0 `간격과 모양 규칙` 보드를 그대로 옮긴 것이다.
// 색, 글자, 간격은 여기 한 곳에만 둔다.

export const colors = {
  paper: '#fbf7f2',
  home: '#f5ecdf',
  surface: '#fffcf8',
  line: '#e8dccd',
  ink: '#2b1a0f',
  ink2: '#5c4533',
  ink3: '#7a6250',
  brand: '#6f4220',
  brandInk: '#fff8f0',
  brandSoft: '#f2e4d4',
  urgent: '#a3291c',
  urgentSoft: '#f8e0da',
  busy: '#a63d17',
  busySoft: '#f9e3d7',
  calm: '#2f6280',
  calmSoft: '#e2edf3',
  done: '#2f6b3f',
  doneSoft: '#e1efe3',
  naver: '#03c75a',
  /** 불러오는 동안 자리 (Bone). Figma DoNA 03 · 토큰/skeleton */
  skeleton: '#e7dacb',
} as const;

export type ColorName = keyof typeof colors;

// 간격은 다섯 가지만 쓴다.
//  4  한 덩어리 안의 글줄, 꼬리표 안의 아이콘과 글
//  8  같은 것이 나란히 있을 때 (칩과 칩, 카드와 카드)
// 12  카드 안에서 (아이콘 칸과 글, 줄 안쪽 여백)
// 16  한 답 안의 덩어리 사이, 카드 안쪽 여백, 듣기 알약과 메뉴바 사이
// 24  화면 양옆 여백(휴대폰), 구역이 바뀌는 곳
export const space = { s4: 4, s8: 8, s12: 12, s16: 16, s24: 24, s32: 32 } as const;

export const radius = { card: 20, row: 14, tile: 12, bubble: 12, button: 14, item: 16, pill: 999 } as const;

export const fonts = {
  regular: 'NotoSansKR_400Regular',
  medium: 'NotoSansKR_500Medium',
  bold: 'NotoSansKR_700Bold',
} as const;

export type TypeName = 'display' | 'title' | 'body' | 'bodyStrong' | 'label' | 'small' | 'button';
type TypeSpec = { fontSize: number; lineHeight: number; fontFamily: string };

const spec = (fontSize: number, lineHeight: number, weight: keyof typeof fonts): TypeSpec => ({
  fontSize,
  lineHeight,
  fontFamily: fonts[weight],
});

// 휴대폰은 Figma 크기 그대로. 태블릿은 세워 두고 멀리서 보므로 한 단계 크게.
export const typeScale: Record<'phone' | 'tablet', Record<TypeName, TypeSpec>> = {
  phone: {
    display: spec(28, 38, 'bold'),
    title: spec(22, 31, 'bold'),
    body: spec(18, 28, 'regular'),
    bodyStrong: spec(18, 28, 'medium'),
    label: spec(15, 22, 'medium'),
    small: spec(14, 20, 'medium'),
    button: spec(18, 24, 'bold'),
  },
  tablet: {
    display: spec(34, 46, 'bold'),
    title: spec(28, 38, 'bold'),
    body: spec(22, 32, 'regular'),
    bodyStrong: spec(22, 32, 'medium'),
    label: spec(18, 26, 'medium'),
    small: spec(16, 22, 'medium'),
    button: spec(20, 28, 'bold'),
  },
};

// 너비 600 미만: 휴대폰 / 600 ~ 899: 태블릿 세로 / 900 이상: 태블릿 가로(두 칸)
export const breakpoints = { tablet: 600, wide: 900 } as const;
