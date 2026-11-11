import { Suspense } from "react";
import { StoreSearchScreen } from "@/components/start/StartScreens";

export default function Page() {
  return (
    <Suspense>
      <StoreSearchScreen />
    </Suspense>
  );
}
