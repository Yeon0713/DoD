import { Suspense } from "react";
import { CheckScreen } from "@/components/reply/CheckScreen";

export default function Page() {
  return (
    <Suspense>
      <CheckScreen />
    </Suspense>
  );
}
