import { Suspense } from "react";
import { PosterScreen } from "@/components/poster/PosterScreens";

export default function Page() {
  return (
    <Suspense>
      <PosterScreen />
    </Suspense>
  );
}
