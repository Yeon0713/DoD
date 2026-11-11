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
};
