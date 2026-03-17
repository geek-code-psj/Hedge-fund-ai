// frontend/components/dashboard/InsiderTracker.tsx
"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, User } from "lucide-react";
import { cn } from "@/lib/utils";
import type { InsiderTrade } from "@/types";

interface InsiderTrackerProps {
  trades: InsiderTrade[];
  ticker: string;
}

export function InsiderTracker({ trades, ticker }: InsiderTrackerProps) {
  if (!trades.length) {
    return (
      <div className="flex h-24 items-center justify-center rounded-xl border border-white/5 bg-white/2">
        <p className="font-mono text-xs text-zinc-700">No recent insider activity</p>
      </div>
    );
  }

  const buys = trades.filter((t) => t.transaction_type === "BUY");
  const sells = trades.filter((t) => t.transaction_type === "SELL");
  const buyValue = buys.reduce((s, t) => s + (t.value_usd ?? 0) * t.shares, 0);
  const sellValue = sells.reduce((s, t) => s + (t.value_usd ?? 0) * t.shares, 0);
  const total = buyValue + sellValue || 1;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="font-mono text-[10px] uppercase tracking-widest text-zinc-500">
          Insider Activity — {ticker}
        </p>
        <p className="font-mono text-[10px] text-zinc-600">{trades.length} transactions</p>
      </div>

      {/* Buy/Sell balance bar */}
      <div className="space-y-1.5">
        <div className="flex h-2 overflow-hidden rounded-full">
          <motion.div
            className="bg-emerald-500"
            initial={{ width: 0 }}
            animate={{ width: `${(buyValue / total) * 100}%` }}
            transition={{ duration: 0.8, ease: "easeOut" }}
          />
          <motion.div
            className="bg-red-500"
            initial={{ width: 0 }}
            animate={{ width: `${(sellValue / total) * 100}%` }}
            transition={{ duration: 0.8, ease: "easeOut", delay: 0.1 }}
          />
        </div>
        <div className="flex justify-between font-mono text-[9px]">
          <span className="text-emerald-500">{buys.length} BUYS</span>
          <span className="text-red-500">{sells.length} SELLS</span>
        </div>
      </div>

      {/* Trade list */}
      <div className="max-h-48 space-y-1.5 overflow-y-auto">
        {trades.slice(0, 8).map((trade, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.04 }}
            className={cn(
              "flex items-center gap-3 rounded-lg border px-3 py-2",
              trade.transaction_type === "BUY"
                ? "border-emerald-500/15 bg-emerald-500/5"
                : "border-red-500/15 bg-red-500/5"
            )}
          >
            <div className={cn(
              "flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full",
              trade.transaction_type === "BUY" ? "bg-emerald-500/20" : "bg-red-500/20"
            )}>
              {trade.transaction_type === "BUY"
                ? <TrendingUp className="h-3 w-3 text-emerald-400" />
                : <TrendingDown className="h-3 w-3 text-red-400" />
              }
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate font-mono text-[10px] font-medium text-zinc-300">
                  {trade.name}
                </p>
                <span className={cn(
                  "flex-shrink-0 font-mono text-[9px] font-bold",
                  trade.transaction_type === "BUY" ? "text-emerald-400" : "text-red-400"
                )}>
                  {trade.transaction_type}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <p className="font-mono text-[9px] text-zinc-600">{trade.title || "—"}</p>
                <p className="font-mono text-[9px] text-zinc-500">
                  {trade.shares.toLocaleString()} shares
                  {trade.value_usd ? ` @ $${trade.value_usd.toFixed(2)}` : ""}
                </p>
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {trades.length > 8 && (
        <p className="text-center font-mono text-[10px] text-zinc-700">
          +{trades.length - 8} more transactions
        </p>
      )}
    </div>
  );
}
