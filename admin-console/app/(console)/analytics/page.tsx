import { Suspense } from "react";
import { Analytics } from "@/components/analytics";
export default function Page() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <Analytics />
    </Suspense>
  );
}
