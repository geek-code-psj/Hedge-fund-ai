// frontend/components/dashboard/SentimentHeatmap.tsx
"use client";

import { motion } from "framer-motion";
import { cn, sentimentColor } from "@/lib/utils";
import type { Sentiment } from "@/types";

// Extended type for the component (maps from full thesis data)
interface SentimentHeatmapProps {
  sentimentScore: number;      // -1 to +1
  sentiment: Sentiment;
  headlineCount: number;
  keyThemes: string[];
  sentimentAssessment: string;
}

const SENTIMENT_LABELS: Record<string, string> = {
  VERY_POSITIVE: "Very Positive",
  POSITIVE: "Positive",
  NEUTRAL: "Neutral",
  NEGATIVE: "Negative",
  VERY_NEGATIVE: "Very Negative",
};

export function SentimentHeatmap({
  sentimentScore,
  sentiment,
  headlineCount,
  keyThemes,
  sentimentAssessment,
}: SentimentHeatmapProps) {
  // Map -1…+1 to 0…100 for the gauge
  const gaugePct = Math.round(((sentimentScore + 1) / 2) * 100);

  // Color stops: red → amber → neutral → green → emerald
  const gaugeColor =
    gaugePct >= 70 ? "#10b981" :
    gaugePct >= 55 ? "#34d399" :
    gaugePct >= 40 ? "#a1a1aa" :
    gaugePct >= 25 ? "#f59e0b" :
    "#ef4444";

  // Theme heat: positive keywords get green, negative get red
  const POSITIVE_KW = new Set(["growth","profit","beat","record","strong","upgrade","buyback","surge","expansion"]);
  const NEGATIVE_KW = new Set(["loss","miss","decline","cut","downgrade","lawsuit","fall","risk","investigation","fraud"]);

  function themeColor(theme: string): string {
    if (POSITIVE_KW.has(theme)) return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
    if (NEGATIVE_KW.has(theme)) return "border-red-500/30 bg-red-500/10 text-red-400";
    return "border-white/5 bg-white/3 text-zinc-400";
  }

  return (
    <div className="space-y-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-zinc-500">
        Market Sentiment
      </p>

      {/* Gauge bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between font-mono text-[10px]">
          <span className="text-red-500">Very Negative</span>
          <span className={cn("font-bold", sentimentColor(sentiment))}>
            {SENTIMENT_LABELS[sentiment]} ({sentimentScore >= 0 ? "+" : ""}{sentimentScore.toFixed(3)})
          </span>
          <span className="text-emerald-500">Very Positive</span>
        </div>
        <div className="relative h-2.5 overflow-hidden rounded-full bg-gradient-to-r from-red-500/40 via-zinc-700/20 to-emerald-500/40">
          {/* Indicator dot */}
          <motion.div
            className="absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-white/80 shadow-lg"
            style={{ backgroundColor: gaugeColor }}
            initial={{ left: "50%" }}
            animate={{ left: `${gaugePct}%` }}
            transition={{ duration: 1, ease: "easeOut", type: "spring", stiffness: 60 }}
          />
        </div>
        <p className="text-right font-mono text-[10px] text-zinc-600">
          Based on {headlineCount} headlines
        </p>
      </div>

      {/* Theme heatmap */}
      {keyThemes.length > 0 && (
        <div>
          <p className="mb-2 font-mono text-[10px] text-zinc-600">Key themes</p>
          <div className="flex flex-wrap gap-1.5">
            {keyThemes.map((theme) => (
              <motion.span
                key={theme}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 font-mono text-[10px] transition-colors",
                  themeColor(theme)
                )}
              >
                {theme}
              </motion.span>
            ))}
          </div>
        </div>
      )}

      {/* Assessment quote */}
      <div className="rounded-xl border border-white/5 bg-white/2 p-3">
        <p className="text-xs italic leading-relaxed text-zinc-400">
          "{sentimentAssessment}"
        </p>
      </div>
    </div>
  );
}
