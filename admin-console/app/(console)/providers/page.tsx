import { Suspense } from "react";
import { Providers } from "@/components/providers";
export default function Page() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <Providers />
    </Suspense>
  );
}
