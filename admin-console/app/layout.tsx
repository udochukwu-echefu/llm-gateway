import type { Metadata } from "next";
import { connection } from "next/server";
import "./globals.css";
import "./styles/search-glow.css";
export const metadata: Metadata = {
  title: "Gateway · Admin console",
  description: "Private gateway administration",
};
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  await connection();
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
