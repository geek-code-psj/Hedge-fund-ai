// frontend/components/dashboard/ConfidenceScoring.tsx
"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import type { InvestmentThesis } from "@/types";

interface ConfidenceScoringProps {
  thesis: InvestmentThesis;
  agentsCompleted: string[];
  agentsFailed: string[];
}

const SIGNAL_WEIGHTS = [
  { key: "news_agent", label: "News Sentiment", weight: 0.2 },
  { key: "financial_data_agent", label: "Financial Data", weight: 0.45 },
  { key: "document_agent", label: "Filing Analysis", weight: 0.35 },
];

export function ConfidenceScoring({ thesis, agentsCompleted, agentsFailed }: ConfidenceScoringProps) {
  const conviction = thesis.conviction_score;
  const pct = Math.round(conviction * 100);

  // Per-signal confidence contribution
  const signalScores = SIGNAL_WEIGHTS.map(({ key, label, weight }) => {
    const completed = agentsCompleted.includes(key);
    const failed = agentsFailed.includes(key);
    const score = failed ? 0 : completed ? conviction : 0;
    return { label, score, weight, completed, failed };
  });

  // Color based on conviction
  const ringColor =
    pct >= 75 ? "#10b981" :
    pct >= 55 ? "#f59e0b" :
    "#ef4444";

  const ringLabel =
    pct >= 75 ? "High conviction" :
    pct >= 55 ? "Moderate conviction" :
    "Low conviction — limited data";

  return (
    <div className="space-y-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-zinc-500">
        AI Confidence Breakdown
      </p>

      {/* Main ring */}
      <div className="flex items-center gap-5">
        <ConvictionRingLarge value={pct} color={ringColor} />
        <div className="space-y-1">
          <p className="text-2xl font-black text-white">{pct}%</p>
          <p className="font-mono text-xs" style={{ color: ringColor }}>{ringLabel}</p>
          <p className="font-mono text-[10px] text-zinc-600">
            {agentsCompleted.length}/{agentsCompleted.length + agentsFailed.length} agents succeeded
          </p>
        </div>
      </div>

      {/* Signal breakdown */}
      <div className="space-y-2">
        {signalScores.map(({ label, score, weight, completed, failed }) => (
          <div key={label} className="space-y-1">
            <div className="flex items-center justify-between font-mono text-[10px]">
              <div className="flex items-center gap-2">
                <span className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  failed ? "bg-red-500" : completed ? "bg-emerald-500" : "bg-zinc-700"
                )} />
                <span className="text-zinc-400">{label}</span>
              </div>
              <div className="flex items-center gap-3 text-zinc-600">
                <span>weight: {Math.round(weight * 100)}%</span>
                <span className={completed ? "text-emerald-400" : "text-zinc-700"}>
                  {failed ? "failed" : completed ? `${Math.round(score * 100)}%` : "—"}
                </span>
              </div>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-white/5">
              <motion.div
                className={cn("h-full rounded-full", failed ? "bg-red-500/40" : "bg-indigo-500")}
                initial={{ width: 0 }}
                animate={{ width: `${completed ? Math.round(score * 100) : 0}%` }}
                transition={{ duration: 0.8, ease: "easeOut" }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Recommendation rationale */}
      <div className={cn(
        "rounded-xl border p-3",
        pct >= 75 ? "border-emerald-500/20 bg-emerald-500/5" :
        pct >= 55 ? "border-amber-500/20 bg-amber-500/5" :
        "border-red-500/20 bg-red-500/5"
      )}>
        <p className="font-mono text-[10px] text-zinc-500">Reviewer confidence note</p>
        <p className="mt-1 text-xs text-zinc-400">
          {pct >= 75
            ? "Strong data completeness across all agents. High signal alignment warrants conviction."
            : pct >= 55
            ? "Adequate data coverage. Some signals mixed — recommendation reflects uncertainty."
            : "Incomplete data from one or more agents. Exercise additional caution."}
        </p>
      </div>
    </div>
  );
}

function ConvictionRingLarge({ value, color }: { value: number; color: string }) {
  const r = 28;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - value / 100);

  return (
    <svg width="72" height="72" className="-rotate-90">
      <circle cx="36" cy="36" r={r} fill="none" strokeWidth="4" className="stroke-white/5" />
      <motion.circle
        cx="36" cy="36" r={r}
        fill="none"
        strokeWidth="4"
        stroke={color}
        strokeDasharray={circ}
        initial={{ strokeDashoffset: circ }}
        animate={{ strokeDashoffset: offset }}
        transition={{ duration: 1.2, ease: "easeOut" }}
        strokeLinecap="round"
      />
    </svg>
  );
}
