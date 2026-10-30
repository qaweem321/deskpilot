import type { Metadata } from "next";
import { BfcacheReload } from "@/components/bfcache-reload";
import { themeScript } from "@/lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "Deskpilot",
  description: "An AI assistant that works inside a support desk: looks up orders, refunds with your OK, answers from the help center.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <BfcacheReload />
        {children}
      </body>
    </html>
  );
}
