import { Suspense } from "react";
import { MenuOrderScreen } from "@/components/naver/NaverScreens";

export default function Page() {
  return (
    <Suspense>
      <MenuOrderScreen />
    </Suspense>
  );
}
