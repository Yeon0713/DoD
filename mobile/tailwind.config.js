// 디자인 토큰은 src/theme/tokens.json 한 곳에만 둔다.
// (frontend/src/app/globals.css 의 @theme 값을 그대로 옮긴 것)
const plugin = require('tailwindcss/plugin');
const tokens = require('./src/theme/tokens.json');

const px = (n) => `${n}px`;

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  // 라이트 모드 고정(app.json userInterfaceStyle: light). 'media'면 웹에서 NativeWind가 모드를 정할 때 오류가 난다.
  darkMode: 'class',
  theme: {
    extend: {
      colors: tokens.colors,
      fontFamily: {
        sans: [tokens.fonts.regular],
        'sans-medium': [tokens.fonts.medium],
        'sans-bold': [tokens.fonts.bold],
      },
      borderRadius: {
        card: px(tokens.radius.card),
        button: px(tokens.radius.button),
      },
    },
  },
  // 네이티브는 굵기마다 폰트 파일이 따로다. font-medium 같은 굵기 클래스는 아래 플러그인이 fontFamily로 바꾼다.
  corePlugins: { fontWeight: false },
  plugins: [
    // text-display / text-title / text-body / text-label / text-button / text-small
    // 네이티브는 굵기마다 폰트 파일이 따로라서 font-weight 대신 fontFamily 로 굵기를 고른다.
    plugin(({ addUtilities }) => {
      addUtilities(
        Object.fromEntries(
          Object.entries(tokens.typography).map(([name, t]) => [
            `.text-${name}`,
            {
              fontSize: px(t.size),
              lineHeight: px(t.lineHeight),
              fontFamily: tokens.fonts[t.weight],
            },
          ]),
        ),
      );
    }),
    // 굵기 클래스는 text-* 뒤에 둔다. "text-body font-bold"처럼 같이 쓰면 굵기가 이겨야 한다.
    plugin(({ addUtilities }) => {
      addUtilities({
        '.font-regular': { fontFamily: tokens.fonts.regular },
        '.font-medium': { fontFamily: tokens.fonts.medium },
        '.font-bold': { fontFamily: tokens.fonts.bold },
      });
    }),
  ],
};
