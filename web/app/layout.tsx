import type { Metadata } from "next";
import { Space_Grotesk, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { clerkEnabled } from "@/lib/clerk";
import "./globals.css";

const display = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "700"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const body = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Cashflow Risk Intelligence",
  description:
    "Which late payments threaten your cash runway, and what to do this week. Decision support for UK SMEs.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const tree = (
    <html lang="en-GB" className="h-full antialiased">
      <body
        className={`${display.variable} ${body.variable} ${mono.variable} min-h-full`}
      >
        {children}
      </body>
    </html>
  );

  // Only mount Clerk when configured, so the demo runs without keys.
  return clerkEnabled ? <ClerkProvider>{tree}</ClerkProvider> : tree;
}
