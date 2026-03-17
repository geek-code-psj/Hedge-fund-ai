// frontend/components/dashboard/StockSearch.tsx
"use client";

import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, TrendingUp, Loader2, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

const QUICK_TICKERS = [
  { ticker: "AAPL", name: "Apple" },
  { ticker: "NVDA", name: "Nvidia" },
  { ticker: "MSFT", name: "Microsoft" },
  { ticker: "TSLA", name: "Tesla" },
  { ticker: "RELIANCE.NSE", name: "Reliance" },
  { ticker: "AMZN", name: "Amazon" },
];

interface StockSearchProps {
  onAnalyse: (ticker: string, query: string) => void;
  isRunning: boolean;
}

export function StockSearch({ onAnalyse, isRunning }: StockSearchProps) {
  const [ticker, setTicker] = useState("");
  const [query, setQuery] = useState(
    "Provide a comprehensive investment thesis with buy/sell recommendation."
  );
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker.trim() || isRunning) return;
    onAnalyse(ticker.trim().toUpperCase(), query);
  }

  function selectQuick(t: string) {
    setTicker(t);
    inputRef.current?.focus();
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-3">
        {/* Ticker input */}
        <div className={cn(
          "relative overflow-hidden rounded-2xl border transition-all duration-300",
          focused
            ? "border-indigo-500/60 shadow-[0_0_30px_rgba(99,102,241,0.15)]"
            : "border-white/10"
        )}>
          {/* Animated gradient border glow */}
          {focused && (
            <motion.div
              className="absolute inset-0 rounded-2xl opacity-30"
              style={{
                background: "linear-gradient(135deg, #6366f1, #8b5cf6, #a855f7)",
                filter: "blur(20px)",
                zIndex: 0,
              }}
              animate={{ opacity: [0.1, 0.3, 0.1] }}
              transition={{ duration: 2, repeat: Infinity }}
            />
          )}

          <div className="relative z-10 flex items-center gap-3 bg-[#0d0d14]/90 px-4 py-4 backdrop-blur-sm">
            <Search className={cn(
              "h-5 w-5 flex-shrink-0 transition-colors",
              focused ? "text-indigo-400" : "text-zinc-600"
            )} />
            <input
              ref={inputRef}
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              placeholder="Enter ticker… e.g. AAPL, NVDA, RELIANCE.NSE"
              className="flex-1 bg-transparent font-mono text-lg text-white placeholder:text-zinc-700 focus:outline-none"
              disabled={isRunning}
            />
            {ticker && (
              <motion.button
                type="submit"
                disabled={isRunning}
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                className={cn(
                  "flex items-center gap-1.5 rounded-xl px-4 py-2 font-mono text-sm font-bold transition-all",
                  isRunning
                    ? "cursor-not-allowed bg-indigo-500/20 text-indigo-400"
                    : "bg-indigo-600 text-white hover:bg-indigo-500 active:scale-95"
                )}
              >
                {isRunning ? (
                  <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Analysing</>
                ) : (
                  <><TrendingUp className="h-3.5 w-3.5" /> Analyse</>
                )}
              </motion.button>
            )}
          </div>
        </div>

        {/* Query input */}
        <div className="rounded-xl border border-white/5 bg-white/2">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={2}
            placeholder="Research question…"
            className="w-full resize-none bg-transparent px-4 py-3 text-sm text-zinc-400 placeholder:text-zinc-700 focus:outline-none"
            disabled={isRunning}
          />
        </div>
      </form>

      {/* Quick-select tickers */}
      <div className="flex flex-wrap gap-2">
        {QUICK_TICKERS.map(({ ticker: t, name }) => (
          <button
            key={t}
            onClick={() => selectQuick(t)}
            disabled={isRunning}
            className={cn(
              "rounded-lg border px-3 py-1.5 font-mono text-xs transition-all hover:border-indigo-500/40 hover:bg-indigo-500/5",
              ticker === t
                ? "border-indigo-500/50 bg-indigo-500/10 text-indigo-300"
                : "border-white/5 bg-white/2 text-zinc-500 hover:text-zinc-300"
            )}
          >
            <span className="text-zinc-300">{t.split(".")[0]}</span>
            <span className="ml-1 text-zinc-600">{name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
