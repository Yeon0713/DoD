import { Suspense } from "react";
import { ReplyScreen } from "@/components/reply/ReplyScreens";

export default function Page() {
  return (
    <Suspense>
      <ReplyScreen />
    </Suspense>
  );
}
