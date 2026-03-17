// frontend/components/dashboard/ThesisCard.tsx
"use client";

import { motion } from "framer-motion";
import {
  TrendingUp, TrendingDown,
  Zap, Target, BarChart2, Shield,
} from "lucide-react";
import { cn, recommendationBg, riskColor, fmtPct } from "@/lib/utils";
import type { InvestmentThesis } from "@/types";

interface ThesisCardProps {
  thesis: InvestmentThesis;
  cached: boolean;
  latencyMs: number;
}

export function ThesisCard({ thesis, cached, latencyMs }: ThesisCardProps) {
  const convictionPct = Math.round(thesis.conviction_score * 100);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-5"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-3xl font-black tracking-tight text-white">{thesis.ticker}</h2>
            <span className={cn(
              "rounded-lg border px-3 py-1 text-sm font-bold tracking-wide",
              recommendationBg(thesis.recommendation)
            )}>
              {thesis.recommendation.replace("_", " ")}
            </span>
            {cached && (
              <span className="flex items-center gap-1 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 font-mono text-[10px] text-indigo-400">
                <Zap className="h-2.5 w-2.5" /> cached
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-zinc-500">{thesis.company_name} · {thesis.analysis_date}</p>
        </div>

        {/* Conviction score ring */}
        <div className="flex flex-col items-center">
          <ConvictionRing value={convictionPct} />
          <p className="mt-1 font-mono text-[10px] text-zinc-600">conviction</p>
        </div>
      </div>

      {/* Key stats row */}
      <div className="grid grid-cols-4 gap-2">
        <StatBadge label="Target Price" value={`$${thesis.valuation.target_price_usd.toFixed(2)}`} icon={<Target className="h-3.5 w-3.5" />} />
        <StatBadge
          label="Upside"
          value={fmtPct(thesis.valuation.upside_pct / 100)}
          icon={thesis.valuation.upside_pct >= 0 ? <TrendingUp className="h-3.5 w-3.5 text-emerald-400" /> : <TrendingDown className="h-3.5 w-3.5 text-red-400" />}
          positive={thesis.valuation.upside_pct >= 0}
        />
        <StatBadge label="Horizon" value={thesis.time_horizon} icon={<BarChart2 className="h-3.5 w-3.5" />} />
        <StatBadge label="Methodology" value={thesis.valuation.methodology} icon={<Shield className="h-3.5 w-3.5" />} />
      </div>

      {/* Executive Summary */}
      <div className="rounded-xl border border-white/5 bg-white/2 p-4">
        <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-zinc-500">Executive Summary</p>
        <p className="text-sm leading-relaxed text-zinc-300">{thesis.executive_summary}</p>
      </div>

      {/* Bull / Bear */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
            <p className="font-mono text-[10px] uppercase tracking-widest text-emerald-500">Bull Case</p>
          </div>
          <p className="text-xs leading-relaxed text-zinc-300">{thesis.bull_case}</p>
        </div>
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
          <div className="mb-2 flex items-center gap-1.5">
            <TrendingDown className="h-3.5 w-3.5 text-red-400" />
            <p className="font-mono text-[10px] uppercase tracking-widest text-red-500">Bear Case</p>
          </div>
          <p className="text-xs leading-relaxed text-zinc-300">{thesis.bear_case}</p>
        </div>
      </div>

      {/* Financials + Technical */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-white/5 bg-white/2 p-4">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-zinc-500">Financials</p>
          <p className="text-xs leading-relaxed text-zinc-300">{thesis.financials_summary}</p>
        </div>
        <div className="rounded-xl border border-white/5 bg-white/2 p-4">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-zinc-500">Technical</p>
          <p className="text-xs leading-relaxed text-zinc-300">{thesis.technical_summary}</p>
        </div>
      </div>

      {/* Catalysts */}
      <div className="rounded-xl border border-white/5 bg-white/2 p-4">
        <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-zinc-500">
          Catalysts ({thesis.catalysts.length})
        </p>
        <div className="space-y-2">
          {thesis.catalysts.map((c, i) => (
            <div key={i} className="flex items-start gap-3">
              <div className="mt-0.5 flex-shrink-0 rounded-full border border-violet-500/30 bg-violet-500/10 px-1.5 py-0.5 font-mono text-[9px] text-violet-400">
                {c.timeline}
              </div>
              <p className="flex-1 text-xs text-zinc-300">{c.description}</p>
              <ProbabilityBar value={c.probability} />
            </div>
          ))}
        </div>
      </div>

      {/* Risk Factors */}
      <div className="rounded-xl border border-white/5 bg-white/2 p-4">
        <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-zinc-500">
          Risk Factors ({thesis.risk_factors.length})
        </p>
        <div className="space-y-2">
          {thesis.risk_factors.map((r, i) => (
            <div key={i} className={cn("rounded-lg border p-3", riskColor(r.severity))}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-[10px] font-bold uppercase">{r.category}</span>
                <span className="font-mono text-[9px]">{r.severity}</span>
              </div>
              <p className="mt-1 text-xs text-zinc-400">{r.description}</p>
              {r.mitigation && (
                <p className="mt-1.5 text-[10px] italic text-zinc-500">↳ {r.mitigation}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Sentiment */}
      <div className="rounded-xl border border-white/5 bg-white/2 p-4">
        <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-zinc-500">Sentiment</p>
        <p className="text-xs leading-relaxed text-zinc-300">{thesis.sentiment_assessment}</p>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-white/5 pt-3">
        <p className="font-mono text-[10px] text-zinc-700">
          Sources: {thesis.data_sources.join(" · ")}
        </p>
        <p className="font-mono text-[10px] text-zinc-700">
          {latencyMs.toFixed(0)}ms
        </p>
      </div>
    </motion.div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatBadge({
  label, value, icon, positive,
}: { label: string; value: string; icon: React.ReactNode; positive?: boolean }) {
  return (
    <div className="rounded-xl border border-white/5 bg-white/2 p-3">
      <div className="flex items-center gap-1.5 text-zinc-500">
        {icon}
        <span className="font-mono text-[9px] uppercase tracking-wider">{label}</span>
      </div>
      <p className={cn(
        "mt-1 font-mono text-sm font-bold",
        positive === true ? "text-emerald-400" :
        positive === false ? "text-red-400" :
        "text-white"
      )}>{value}</p>
    </div>
  );
}

function ProbabilityBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex flex-col items-end gap-0.5">
      <span className="font-mono text-[9px] text-zinc-500">{pct}%</span>
      <div className="h-1 w-14 overflow-hidden rounded-full bg-white/5">
        <div
          className="h-full rounded-full bg-violet-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function ConvictionRing({ value }: { value: number }) {
  const radius = 18;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - value / 100);
  const color = value >= 75 ? "#10b981" : value >= 50 ? "#f59e0b" : "#ef4444";

  return (
    <div className="relative flex h-14 w-14 items-center justify-center">
      <svg className="-rotate-90" width="56" height="56">
        <circle cx="28" cy="28" r={radius} strokeWidth="3" className="stroke-white/5 fill-none" />
        <circle
          cx="28" cy="28" r={radius}
          strokeWidth="3"
          fill="none"
          stroke={color}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 1s ease" }}
        />
      </svg>
      <span className="absolute font-mono text-[11px] font-bold text-white">{value}%</span>
    </div>
  );
}
