// 행사·경기 종류 아이콘 (Figma "00 · 에셋" 페이지 › 00f · 포스터 행사·경기 아이콘). 포스터 할 일 카드 날짜 줄, 이번 주 미리보기, 이번 주 행사 화면에 쓴다.
import type { ImageSourcePropType } from "react-native";

export type OccasionIcon =
  | "event_festival"
  | "event_university"
  | "event_marathon"
  | "event_general"
  | "game_soccer"
  | "game_baseball"
  | "game_basketball"
  | "game_volleyball"
  | "game_esports"
  | "game_general"
  | "weekend_promo";

export const OCCASION_IMG: Record<OccasionIcon, ImageSourcePropType> = {
  event_festival: require("../../../assets/icons/occasion/event_festival.png"),
  event_university: require("../../../assets/icons/occasion/event_university.png"),
  event_marathon: require("../../../assets/icons/occasion/event_marathon.png"),
  event_general: require("../../../assets/icons/occasion/event_general.png"),
  game_soccer: require("../../../assets/icons/occasion/game_soccer.png"),
  game_baseball: require("../../../assets/icons/occasion/game_baseball.png"),
  game_basketball: require("../../../assets/icons/occasion/game_basketball.png"),
  game_volleyball: require("../../../assets/icons/occasion/game_volleyball.png"),
  game_esports: require("../../../assets/icons/occasion/game_esports.png"),
  game_general: require("../../../assets/icons/occasion/game_general.png"),
  weekend_promo: require("../../../assets/icons/occasion/weekend_promo.png"),
};

/** 행사·경기 종류와 이름(예: "남양 가을 축제", "축구 경기")으로 아이콘을 고른다. kind 가 없으면 행사·경기 없는 주말 홍보 */
export function occasionIcon(kind: "EVENT" | "GAME" | null, name: string): OccasionIcon {
  if (kind === "EVENT") {
    if (/대학/.test(name)) return "event_university";
    if (/마라톤|달리기|러닝/.test(name)) return "event_marathon";
    if (/축제|페스티벌/.test(name)) return "event_festival";
    return "event_general";
  }
  if (kind === "GAME") {
    if (/e스포츠|이스포츠|롤|LoL/i.test(name)) return "game_esports";
    if (/축구/.test(name)) return "game_soccer";
    if (/야구/.test(name)) return "game_baseball";
    if (/농구/.test(name)) return "game_basketball";
    if (/배구/.test(name)) return "game_volleyball";
    return "game_general";
  }
  return "weekend_promo";
}
