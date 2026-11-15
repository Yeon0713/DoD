import { AiPosterScreen } from "@/components/poster/AiPosterScreen";
import { PosterScreen } from "@/components/poster/PosterScreens";
import { USE_MOCK } from "@/lib/api";

// 서버를 쓰면 AI 포스터(그날 상황·CLOVA 문구 → ChatGPT 그림), 목업이면 앱이 그려 만드는 포스터
export default function Screen() {
  return USE_MOCK ? <PosterScreen /> : <AiPosterScreen />;
}
