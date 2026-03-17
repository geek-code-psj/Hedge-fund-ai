import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Formatters
export function fmt(num: number | undefined | null) {
  if (num === undefined || num === null) return "-";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(num);
}

export function fmtPct(num: number | undefined | null) {
  if (num === undefined || num === null) return "-";
  return new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 2 }).format(num);
}

export function fmtB(num: number | undefined | null) {
  if (num === undefined || num === null) return "-";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(num) + "B";
}

// Color and mapping utilities
export function recommendationBg(rec: string | undefined) {
  switch (rec?.toLowerCase()) {
    case "strong_buy": return "bg-emerald-500/20";
    case "buy": return "bg-green-500/20";
    case "hold": return "bg-zinc-500/20";
    case "sell": return "bg-red-500/20";
    case "strong_sell": return "bg-rose-500/20";
    default: return "bg-zinc-500/10";
  }
}

export function recommendationColor(rec: string | undefined) {
  switch (rec?.toLowerCase()) {
    case "strong_buy": return "text-emerald-500";
    case "buy": return "text-green-500";
    case "hold": return "text-zinc-500";
    case "sell": return "text-red-500";
    case "strong_sell": return "text-rose-500";
    default: return "text-zinc-500";
  }
}

export function riskColor(risk: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | undefined) {
  switch (risk) {
    case "LOW": return "text-green-500";
    case "MEDIUM": return "text-yellow-500";
    case "HIGH": return "text-red-500";
    case "CRITICAL": return "text-rose-600 font-bold";
    default: return "text-zinc-500";
  }
}

export function sentimentColor(sentiment: string | undefined) {
  switch (sentiment?.toLowerCase()) {
    case "positive": return "text-green-500";
    case "negative": return "text-red-500";
    case "neutral": return "text-zinc-500";
    default: return "text-zinc-500";
  }
}

export function technicalSignalColor(signal: string | undefined) {
  switch (signal?.toLowerCase()) {
    case "bullish": return "text-green-500";
    case "bearish": return "text-red-500";
    case "neutral": return "text-zinc-500";
    default: return "text-zinc-500";
  }
}

export function agentLabel(agent: string) {
  switch (agent.toLowerCase()) {
    case "news_agent": return "News Agent";
    case "financial_agent": return "Financial Quant";
    case "document_agent": return "10-K RAG Parser";
    default: return "Agent";
  }
}
