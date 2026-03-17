// frontend/app/layout.tsx
import type { Metadata } from "next";
import { Space_Mono, Syne } from "next/font/google";
import "./globals.css";

const syne = Syne({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "700", "800"],
});

const mono = Space_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "700"],
});

export const metadata: Metadata = {
  title: "Hedge Fund AI — Multi-Agent Financial Analysis",
  description: "Institutional-grade AI equity research powered by LangGraph, RAG, and real-time SSE streaming.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${syne.variable} ${mono.variable} dark`}>
      <body className="bg-[#070710] font-sans text-zinc-100 antialiased">
        {children}
      </body>
    </html>
  );
}
