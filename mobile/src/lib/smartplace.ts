// 네이버 스마트플레이스(사장님용 네이버 플레이스 관리 화면) 열기.
// 메뉴, 메뉴 사진은 도나가 바꾸지 않고 사장님이 네이버 플레이스에서 고친다. 고치고 돌아오면 화면이 다시 불러온다.
import { Linking, Platform } from "react-native";

export const SMARTPLACE_URL = "https://new.smartplace.naver.com/";

export function openSmartPlace() {
  if (Platform.OS === "web") window.open(SMARTPLACE_URL, "_blank", "noopener");
  else void Linking.openURL(SMARTPLACE_URL);
}
