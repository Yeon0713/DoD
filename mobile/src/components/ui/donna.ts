// 도나 그림. 이름은 Figma 레이어(도나/b1-0 ...)와 같다.
import type { ImageSourcePropType } from "react-native";
import type { Donna } from "@/lib/cards";

export const DONNA_IMG: Record<Donna, ImageSourcePropType> = {
  "b1-0": require("../../../assets/donna/b1-0.png"),
  "b1-1": require("../../../assets/donna/b1-1.png"),
  "b1-2": require("../../../assets/donna/b1-2.png"),
  "b2-0": require("../../../assets/donna/b2-0.png"),
  "b2-1": require("../../../assets/donna/b2-1.png"),
  "b3-0": require("../../../assets/donna/b3-0.png"),
  "b3-1": require("../../../assets/donna/b3-1.png"),
  "b3-2": require("../../../assets/donna/b3-2.png"),
  "b4-0": require("../../../assets/donna/b4-0.png"),
  "b4-1": require("../../../assets/donna/b4-1.png"),
  "b4-2": require("../../../assets/donna/b4-2.png"),
  question: require("../../../assets/donna/question.png"),
  // 물음표 도나 6가지 (Figma 00 에셋 "DONNA(5) 1"을 자른 것). 상황에 맞는 것을 쓴다
  "q-think": require("../../../assets/donna/q-think.png"), // 턱 괴고 생각: 화면을 찾지 못했을 때
  "q-arms": require("../../../assets/donna/q-arms.png"), // 팔짱 끼고 찡그림: 일을 마치지 못했을 때
  "q-scratch": require("../../../assets/donna/q-scratch.png"), // 머리 긁적: 취소했거나 시간이 지나 다시 해야 할 때
  "q-clipboard": require("../../../assets/donna/q-clipboard.png"), // N 서류판: 가게가 아직 준비 중일 때
  "q-laptop": require("../../../assets/donna/q-laptop.png"), // N 노트북 앞 어지러움: 인터넷이 끊겼거나 불러오지 못했을 때
  "q-shrug": require("../../../assets/donna/q-shrug.png"), // 양손 으쓱: 찾는 것이 없을 때
};
