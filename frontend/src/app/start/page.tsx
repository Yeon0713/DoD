import { Suspense } from "react";
import { IntroScreen } from "@/components/start/StartScreens";

export default function Page() {
  return (
    <Suspense>
      <IntroScreen />
    </Suspense>
  );
}
