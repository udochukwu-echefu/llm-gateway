"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
export function Breadcrumbs() {
  const parts = usePathname().split("/").filter(Boolean);
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumbs">
      <Link prefetch={false} href="/overview">
        Gateway
      </Link>
      {parts.map((part, index) =>
        part === "teams" ? null : (
          <span key={index}>
            {" "}
            /{" "}
            <Link prefetch={false} href={"/" + parts.slice(0, index + 1).join("/")}>
              {decodeURIComponent(part)
                .replace(/^orgs$/, "Organisations")
                .replace(/^teams$/, "Teams")}
            </Link>
          </span>
        ),
      )}
    </nav>
  );
}
