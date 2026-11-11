import { Suspense } from "react";
import { NaverConnectScreen } from "@/components/naver/NaverScreens";

export default function Page() {
  return (
    <Suspense>
      <NaverConnectScreen />
    </Suspense>
  );
}
