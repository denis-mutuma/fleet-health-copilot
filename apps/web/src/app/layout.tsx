import type { Metadata } from "next";
import "./globals.css";
import Providers from "./providers";
import AppShell from "./components/app-shell";

export const metadata: Metadata = {
  title: "Fleet Health Copilot",
  description: "Multi-agent incident operations cockpit",
  icons: {
    icon: "/icon.png",
    shortcut: "/icon.png",
    apple: "/icon.png"
  }
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
