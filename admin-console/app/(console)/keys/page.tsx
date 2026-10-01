import { Suspense } from "react";
import { Keys } from "@/components/keys";
export default function Page() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <Keys />
    </Suspense>
  );
}
