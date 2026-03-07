import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { CommandPalette } from "./components/CommandPalette";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SwarmWeaver",
  description:
    "Autonomous multi-mode coding agent powered by the Claude Agent SDK",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning className={jetbrainsMono.variable}>
      <body className="antialiased font-sans">
        {children}
        <Toaster theme="dark" position="bottom-right" richColors />
        <CommandPalette />
      </body>
    </html>
  );
}
