// 서버의 웹 개발자 대시보드(저장소 맨 위 dev/ 폴더) 열기. 설정 맨 아래 버튼과 시작 화면 메뉴(☰)가 같이 쓴다.
// 서버를 DEV_TOOLS_ENABLED=true 로 켰을 때만 열린다 (꺼져 있으면 서버가 404를 돌려준다).
import { Linking, Platform } from "react-native";
import { BASE_URL } from "./server";

export const DEV_DASHBOARD_URL = `${BASE_URL}/dev-dashboard/`;

/** 웹은 새 탭, 휴대폰은 브라우저로 연다. 휴대폰(Expo Go)에서는 서버 주소가 같은 와이파이의 컴퓨터 IP여야 열린다. */
export function openDevDashboard() {
  if (Platform.OS === "web") window.open(DEV_DASHBOARD_URL, "_blank", "noopener");
  else void Linking.openURL(DEV_DASHBOARD_URL);
}
