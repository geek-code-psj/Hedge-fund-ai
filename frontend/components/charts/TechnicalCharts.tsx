// frontend/components/charts/TechnicalCharts.tsx
"use client";

import {
  RadialBarChart, RadialBar, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Cell, Tooltip,
  ReferenceLine, Legend,
} from "recharts";
import { cn, technicalSignalColor, fmt } from "@/lib/utils";
import type { TechnicalIndicators } from "@/types";

interface TechnicalChartsProps {
  indicators: TechnicalIndicators;
  ticker: string;
}

export function TechnicalCharts({ indicators, ticker }: TechnicalChartsProps) {
  const { rsi, macd, bollinger, sma, overall_technical_signal } = indicators;

  return (
    <div className="space-y-4">
      {/* Overall signal badge */}
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-xs uppercase tracking-widest text-zinc-500">
          Technical Analysis — {ticker}
        </h3>
        <span className={cn(
          "rounded-full border px-3 py-0.5 font-mono text-xs font-medium",
          technicalSignalBadge(overall_technical_signal)
        )}>
          {overall_technical_signal.replace("_", " ")}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {/* RSI Gauge */}
        {rsi && <RSIGauge value={rsi.value} signal={rsi.signal} />}

        {/* MACD Histogram */}
        {macd && <MACDHistogram macd={macd} />}

        {/* Bollinger Bands visual */}
        {bollinger && <BollingerVisual bb={bollinger} />}

        {/* SMA Stack */}
        {sma && <SMAStack sma={sma} />}
      </div>
    </div>
  );
}

// ── RSI Gauge ─────────────────────────────────────────────────────────────────

function RSIGauge({ value, signal }: { value: number; signal: string }) {
  const color = value >= 70 ? "#f87171" : value <= 30 ? "#34d399" : "#a78bfa";
  const data = [{ name: "RSI", value, fill: color }];

  return (
    <div className="rounded-xl border border-white/5 bg-white/2 p-4">
      <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-zinc-500">RSI (14)</p>
      <div className="flex items-center gap-4">
        <div className="h-20 w-20 flex-shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <RadialBarChart
              innerRadius="60%" outerRadius="100%"
              data={[{ value: 100, fill: "#1f1f2e" }, { value, fill: color }]}
              startAngle={180} endAngle={0}
            >
              <RadialBar dataKey="value" cornerRadius={4} />
            </RadialBarChart>
          </ResponsiveContainer>
        </div>
        <div>
          <p className="text-3xl font-black text-white">{value.toFixed(0)}</p>
          <p className={cn("text-xs font-mono", technicalSignalColor(signal as any))}>
            {signal.replace("_", " ")}
          </p>
          <p className="mt-0.5 text-[10px] text-zinc-600">
            {value >= 70 ? "Overbought" : value <= 30 ? "Oversold" : "Neutral zone"}
          </p>
        </div>
      </div>
    </div>
  );
}

// ── MACD Histogram ────────────────────────────────────────────────────────────

function MACDHistogram({ macd }: { macd: NonNullable<TechnicalIndicators["macd"]> }) {
  const data = [
    { name: "MACD", value: macd.macd_line },
    { name: "Signal", value: macd.signal_line },
    { name: "Hist", value: macd.histogram },
  ];

  return (
    <div className="rounded-xl border border-white/5 bg-white/2 p-4">
      <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-zinc-500">MACD (12/26/9)</p>
      <div className="h-20">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barSize={20}>
            <XAxis dataKey="name" tick={{ fill: "#52525b", fontSize: 9 }} axisLine={false} tickLine={false} />
            <YAxis hide />
            <Tooltip
              contentStyle={{ background: "#0d0d14", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, fontSize: 11 }}
              labelStyle={{ color: "#a1a1aa" }}
              itemStyle={{ color: "#e4e4e7" }}
            />
            <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" />
            <Bar dataKey="value" radius={[3, 3, 0, 0]}>
              {data.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.value >= 0 ? "#34d399" : "#f87171"}
                  opacity={i === 2 ? 1 : 0.6}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className={cn("mt-1 text-[10px] font-mono", technicalSignalColor(macd.signal as any))}>
        {macd.signal.replace("_", " ")} — histogram {macd.histogram > 0 ? "+" : ""}{macd.histogram.toFixed(4)}
      </p>
    </div>
  );
}

// ── Bollinger Bands visual ────────────────────────────────────────────────────

function BollingerVisual({ bb }: { bb: NonNullable<TechnicalIndicators["bollinger"]> }) {
  const pct = Math.round(bb.percent_b * 100);
  const isOverBought = bb.percent_b > 1;
  const isOverSold = bb.percent_b < 0;

  return (
    <div className="rounded-xl border border-white/5 bg-white/2 p-4">
      <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-zinc-500">Bollinger Bands</p>
      <div className="space-y-3">
        {/* Price within band */}
        <div className="space-y-1">
          <div className="relative h-6 overflow-visible rounded-full bg-gradient-to-r from-red-500/20 via-zinc-700/20 to-green-500/20 border border-white/5">
            <div
              className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full bg-white shadow-lg ring-2 ring-indigo-500/60 transition-all"
              style={{ left: `${Math.max(2, Math.min(98, pct))}%`, transform: "translateX(-50%) translateY(-50%)" }}
            />
          </div>
          <div className="flex justify-between font-mono text-[9px] text-zinc-600">
            <span>${bb.lower.toFixed(2)}</span>
            <span className="text-zinc-400">${bb.current_price.toFixed(2)}</span>
            <span>${bb.upper.toFixed(2)}</span>
          </div>
        </div>
        <p className={cn("text-xs font-mono", isOverBought ? "text-red-400" : isOverSold ? "text-emerald-400" : "text-zinc-400")}>
          {isOverBought ? "Above upper band" : isOverSold ? "Below lower band" : `%B = ${(bb.percent_b * 100).toFixed(0)}%`}
        </p>
        <p className="text-[10px] text-zinc-600">Bandwidth: {(bb.bandwidth * 100).toFixed(1)}%</p>
      </div>
    </div>
  );
}

// ── SMA Stack ─────────────────────────────────────────────────────────────────

function SMAStack({ sma }: { sma: NonNullable<TechnicalIndicators["sma"]> }) {
  const smas = [
    { label: "SMA 20", value: sma.sma_20, above: sma.sma_20 ? sma.current_price > sma.sma_20 : null },
    { label: "SMA 50", value: sma.sma_50, above: sma.sma_50 ? sma.current_price > sma.sma_50 : null },
    { label: "SMA 200", value: sma.sma_200, above: sma.sma_200 ? sma.current_price > sma.sma_200 : null },
  ];

  return (
    <div className="rounded-xl border border-white/5 bg-white/2 p-4">
      <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-zinc-500">Moving Averages</p>
      <div className="space-y-2">
        <div className="text-2xl font-bold text-white">${sma.current_price.toFixed(2)}</div>
        {smas.map(({ label, value, above }) => (
          <div key={label} className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-zinc-500">{label}</span>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-zinc-300">{value ? `$${value.toFixed(2)}` : "—"}</span>
              {above !== null && (
                <span className={cn("text-[9px] font-bold", above ? "text-emerald-400" : "text-red-400")}>
                  {above ? "▲ ABOVE" : "▼ BELOW"}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function technicalSignalBadge(signal: string): string {
  if (signal.includes("BULLISH")) return "border-emerald-500/30 bg-emerald-500/10 text-emerald-400";
  if (signal.includes("BEARISH")) return "border-red-500/30 bg-red-500/10 text-red-400";
  return "border-zinc-700 bg-zinc-800 text-zinc-400";
}
