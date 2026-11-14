// 포스터 도움말 카드 그림 (SVG). 우리 화면을 줄여 그린 것이다: 1 사진 고르기 화면, 2 로고 바탕 지우기, 3 도나가 고른 문구, 4 스토리 포스터 배치도.
// 그림 폭은 카드 폭을 따르고 높이는 300 × 180 비율이다. 그림 파일(캐릭터, 실제 포스터)은 쓰지 않고 가볍게 SVG 로만 그린다.
import { Image, View } from "react-native";
import Svg, { Circle, G, Line, Path, Rect, Text as SvgText } from "react-native-svg";
import tokens from "@/theme/tokens.json";

const C = tokens.colors;
const FONT = tokens.fonts.bold;
// 캐릭터 시트의 노트북 앞 윙크·엄지 도나 (assets/donna/b3-3.png)
const DONNA_WINK = require("../../../assets/donna/b3-3.png");
const W = 300;
const H = 180;

function Frame({ children, overlay }: { children: React.ReactNode; overlay?: React.ReactNode }) {
  return (
    <View style={{ width: "100%", aspectRatio: W / H }}>
      <Svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`}>
        {children}
      </Svg>
      {overlay}
    </View>
  );
}

/** 사진 한 칸: 국수 그릇을 위에서 본 모양 */
function Bowl({ x, y, w, h, tone = "#c79f78", picked }: { x: number; y: number; w: number; h: number; tone?: string; picked?: number }) {
  const cx = x + w / 2;
  const cy = y + h / 2;
  const r = Math.min(w, h) * 0.36;
  return (
    <G>
      <Rect x={x} y={y} width={w} height={h} rx={10} fill={tone} stroke={picked ? C.brand : "none"} strokeWidth={picked ? 3 : 0} />
      <Circle cx={cx} cy={cy} r={r} fill="#f7efe4" stroke={C.brand} strokeWidth={1.5} />
      <Circle cx={cx} cy={cy} r={r * 0.78} fill="#ead4b2" />
      <Path d={`M${cx - r * 0.5} ${cy - r * 0.1} q${r * 0.25} ${-r * 0.3} ${r * 0.5} 0 t${r * 0.5} 0`} stroke="#fff8f0" strokeWidth={2} fill="none" strokeLinecap="round" />
      <Path d={`M${cx - r * 0.45} ${cy + r * 0.2} q${r * 0.22} ${-r * 0.25} ${r * 0.45} 0 t${r * 0.45} 0`} stroke="#fff8f0" strokeWidth={2} fill="none" strokeLinecap="round" />
      <Circle cx={cx + r * 0.3} cy={cy - r * 0.35} r={r * 0.12} fill="#7a9a5a" />
      <Circle cx={cx - r * 0.25} cy={cy + r * 0.45} r={r * 0.1} fill="#7a9a5a" />
      {picked ? (
        <G>
          <Circle cx={x + w - 11} cy={y + 11} r={8} fill={C.brand} />
          <SvgText x={x + w - 11} y={y + 14.5} fontSize={10} fontFamily={FONT} fontWeight="700" fill={C["brand-ink"]} textAnchor="middle">
            {String(picked)}
          </SvgText>
        </G>
      ) : null}
    </G>
  );
}

/** 1. 사진 고르기: 맨 위 "+ 사진 올리기" 줄, 아래 사진 칸 (두 장 고름) */
export function PickPhotosArt() {
  return (
    <Frame>
      <Rect x={58} y={8} width={184} height={164} rx={16} fill={C.surface} stroke={C.line} strokeWidth={1.5} />
      <Rect x={70} y={20} width={160} height={24} rx={8} fill={C.surface} stroke={C.brand} strokeWidth={1.5} strokeDasharray="4 3" />
      <SvgText x={150} y={36} fontSize={10} fontFamily={FONT} fontWeight="700" fill={C.brand} textAnchor="middle">
        + 사진 올리기
      </SvgText>
      <Bowl x={70} y={52} w={76} h={54} picked={1} />
      <Bowl x={154} y={52} w={76} h={54} tone="#b98d64" />
      <Bowl x={70} y={112} w={76} h={54} tone="#a97d57" />
      <Bowl x={154} y={112} w={76} h={54} tone="#c9a483" picked={2} />
      {/* 누르는 손가락 */}
      <Circle cx={222} cy={150} r={13} fill={C.brand} opacity={0.18} />
      <Circle cx={222} cy={150} r={6} fill={C.brand} opacity={0.5} />
    </Frame>
  );
}

/** 로고 그림: 그릇과 젓가락 */
function LogoGlyph({ cx, cy, s }: { cx: number; cy: number; s: number }) {
  return (
    <G>
      <Line x1={cx - s * 0.55} y1={cy - s * 0.42} x2={cx + s * 0.6} y2={cy - s * 0.52} stroke={C.brand} strokeWidth={s * 0.07} strokeLinecap="round" />
      <Line x1={cx - s * 0.55} y1={cy - s * 0.3} x2={cx + s * 0.6} y2={cy - s * 0.36} stroke={C.brand} strokeWidth={s * 0.07} strokeLinecap="round" />
      <Path d={`M${cx - s * 0.6} ${cy - s * 0.12} h${s * 1.2} a${s * 0.6} ${s * 0.6} 0 0 1 ${-s * 1.2} 0 z`} fill="none" stroke={C.brand} strokeWidth={s * 0.08} />
      <Path d={`M${cx - s * 0.42} ${cy + s * 0.08} q${s * 0.2} ${-s * 0.14} ${s * 0.42} 0 t${s * 0.42} 0`} fill="none" stroke={C.brand} strokeWidth={s * 0.06} strokeLinecap="round" />
    </G>
  );
}

function Checker({ x, y, size, cell = 8 }: { x: number; y: number; size: number; cell?: number }) {
  const n = Math.ceil(size / cell);
  const cells = [];
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) if ((i + j) % 2 === 0) cells.push(<Rect key={`${i}-${j}`} x={x + i * cell} y={y + j * cell} width={Math.min(cell, size - i * cell)} height={Math.min(cell, size - j * cell)} fill="#ece4da" />);
  return <G>{cells}</G>;
}

/** 2. 로고: 흰 바탕 로고 → 바탕을 지운 로고 → "가게 로고 넣기" 줄 */
export function LogoArt() {
  return (
    <Frame>
      <Rect x={40} y={14} width={78} height={78} rx={12} fill="#ffffff" stroke={C.line} strokeWidth={1.5} />
      <LogoGlyph cx={79} cy={56} s={44} />
      <Path d="M132 53 h30 m-8 -7 l8 7 l-8 7" stroke={C.brand} strokeWidth={2.5} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <Rect x={176} y={14} width={78} height={78} rx={12} fill={C.surface} stroke={C.line} strokeWidth={1.5} />
      <Checker x={180} y={18} size={70} />
      <LogoGlyph cx={215} cy={56} s={44} />
      <Path d="M246 18 l3 6 l6 1 l-4.5 4 l1 6 l-5.5 -3 l-5.5 3 l1 -6 l-4.5 -4 l6 -1 z" fill={C.brand} opacity={0.85} />
      <Rect x={40} y={110} width={214} height={50} rx={12} fill={C["brand-soft"]} stroke={C.brand} strokeWidth={1.5} />
      <Rect x={50} y={117} width={36} height={36} rx={8} fill={C.paper} />
      <LogoGlyph cx={68} cy={137} s={22} />
      <SvgText x={96} y={140} fontSize={12} fontFamily={FONT} fontWeight="700" fill={C.ink}>
        가게 로고 넣기
      </SvgText>
      <Circle cx={236} cy={135} r={10} fill={C.brand} />
      <Path d="M231 135 l3.5 3.5 l6 -7" stroke={C["brand-ink"]} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Frame>
  );
}

// 3번 그림 배치: [도나 105] [간격 26] [문구 카드 160] 묶음을 가로 가운데에 둔다 (도나와 카드 사이 간격은 그대로)
const DONNA_BOX = 105; // 프레임 폭 300 의 35%
const MENT_GAP = 26;
const MENT_W = 160;
const MENT_LEFT = (W - (DONNA_BOX + MENT_GAP + MENT_W)) / 2;
const MENT_X = MENT_LEFT + DONNA_BOX + MENT_GAP;

function MentCard({ y, picked, label, head }: { y: number; picked?: boolean; label: string; head: string }) {
  const x = MENT_X;
  return (
    <G>
      <Rect x={x} y={y} width={MENT_W} height={48} rx={10} fill={picked ? C["brand-soft"] : C.surface} stroke={picked ? C.brand : C.line} strokeWidth={picked ? 2 : 1.5} />
      <SvgText x={x + 11} y={y + 17} fontSize={9} fontFamily={FONT} fontWeight="700" fill={C.brand}>
        {label}
      </SvgText>
      <SvgText x={x + 11} y={y + 32} fontSize={11} fontFamily={FONT} fontWeight="700" fill={C.ink}>
        {head}
      </SvgText>
      <Rect x={x + 11} y={y + 38} width={picked ? 110 : 88} height={4} rx={2} fill={C.line} />
    </G>
  );
}

/** 3. 문구: 도나가 상황을 보고 고른 문구 3개, 첫 번째를 고름. 도나는 카드 위 도나(b3-2)와 다른 그림(b3-3, 노트북 앞에서 윙크하며 엄지)을 쓴다 */
export function MentArt() {
  return (
    <Frame
      overlay={
        // 도나와 문구 카드 묶음을 가로 가운데에, 도나는 세로 가운데
        <View pointerEvents="none" style={{ position: "absolute", left: `${(MENT_LEFT / W) * 100}%`, top: "21%", width: `${(DONNA_BOX / W) * 100}%`, aspectRatio: 1 }}>
          <Image source={DONNA_WINK} style={{ width: "100%", height: "100%" }} resizeMode="contain" accessibilityLabel="문구를 고르는 도나" />
        </View>
      }
    >
      <MentCard y={10} picked label="축제 손님 맞이" head="축제 가는 길에 한 그릇" />
      <MentCard y={66} label="추운 날 메뉴" head="쌀쌀한 날엔 옹심이" />
      <MentCard y={122} label="대표 메뉴" head="오늘은 국수 한 그릇" />
    </Frame>
  );
}

function Tag({ x, y, text, anchor = "start" }: { x: number; y: number; text: string; anchor?: "start" | "end" }) {
  return (
    <SvgText x={x} y={y} fontSize={10.5} fontFamily={FONT} fontWeight="700" fill={C["ink-2"]} textAnchor={anchor}>
      {text}
    </SvgText>
  );
}

/** 4. 완성: 인스타 스토리(9:16) 포스터에 무엇이 어디에 들어가는지 간단한 배치도 (실제 포스터 그림은 넣지 않는다) */
export function DoneArt() {
  // 휴대폰 화면 9:16 (78 × 139)
  const sx = 111;
  const sy = 16;
  return (
    <Frame>
      <Rect x={105} y={8} width={90} height={156} rx={14} fill={C.surface} stroke={C.brand} strokeWidth={2} />
      <Rect x={sx} y={sy} width={78} height={139} rx={8} fill={C.paper} stroke={C.line} strokeWidth={1} />
      {/* 큰 글자 두 줄 + 날짜 */}
      <Rect x={sx + 11} y={sy + 12} width={56} height={8} rx={4} fill={C.brand} />
      <Rect x={sx + 17} y={sy + 24} width={44} height={8} rx={4} fill={C.brand} opacity={0.7} />
      <Rect x={sx + 24} y={sy + 38} width={30} height={9} rx={4.5} fill="none" stroke={C.brand} strokeWidth={1.2} />
      {/* 사진 */}
      <Rect x={sx + 8} y={sy + 54} width={62} height={52} rx={8} fill={C["brand-soft"]} />
      <Circle cx={sx + 39} cy={sy + 80} r={15} fill={C.surface} stroke={C.brand} strokeWidth={1.4} />
      <Circle cx={sx + 39} cy={sy + 80} r={10} fill="#ead4b2" />
      {/* 로고 */}
      <Rect x={sx + 23} y={sy + 116} width={32} height={14} rx={7} fill="none" stroke={C.brand} strokeWidth={1.2} strokeDasharray="3 2" />
      {/* 이름표와 선 */}
      <Line x1={sx - 2} y1={sy + 22} x2={70} y2={sy + 22} stroke={C.line} strokeWidth={1.2} />
      <Tag x={66} y={sy + 26} text="문구" anchor="end" />
      <Line x1={sx - 2} y1={sy + 80} x2={70} y2={sy + 80} stroke={C.line} strokeWidth={1.2} />
      <Tag x={66} y={sy + 84} text="사진" anchor="end" />
      <Line x1={sx + 80} y1={sy + 123} x2={230} y2={sy + 123} stroke={C.line} strokeWidth={1.2} />
      <Tag x={234} y={sy + 127} text="로고" />
      <Line x1={sx + 80} y1={sy + 42} x2={230} y2={sy + 42} stroke={C.line} strokeWidth={1.2} />
      <Tag x={234} y={sy + 46} text="날짜" />
      <Tag x={234} y={sy + 84} text="9:16 스토리" />
    </Frame>
  );
}
