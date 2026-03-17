// frontend/app/dashboard/page.tsx  v3 FINAL
"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, BarChart3, RefreshCw, Cpu, Database, TrendingUp, FileText, Users } from "lucide-react";
import { useAnalysisStream } from "@/hooks/useAnalysisStream";
import { AgentTimeline } from "@/components/agents/AgentTimeline";
import { ThesisCard } from "@/components/dashboard/ThesisCard";
import { TechnicalCharts } from "@/components/charts/TechnicalCharts";
import { StockSearch } from "@/components/dashboard/StockSearch";
import { FeedbackPanel } from "@/components/dashboard/FeedbackPanel";
import { SentimentHeatmap } from "@/components/dashboard/SentimentHeatmap";
import { InsiderTracker } from "@/components/dashboard/InsiderTracker";
import { ConfidenceScoring } from "@/components/dashboard/ConfidenceScoring";

type Tab = "thesis" | "technical" | "sentiment" | "insider" | "confidence";

export default function DashboardPage() {
  const { state, analyse, reset, submitFeedback } = useAnalysisStream();
  const [tab, setTab] = useState<Tab>("thesis");
  const isRunning = state.status === "running";
  const isDone = state.status === "complete";

  const TABS: { id: Tab; label: string; Icon: React.ComponentType<{ className?: string }> }[] = [
    { id: "thesis",     label: "Thesis",     Icon: FileText   },
    { id: "technical",  label: "Technical",  Icon: TrendingUp },
    { id: "sentiment",  label: "Sentiment",  Icon: Activity   },
    { id: "insider",    label: "Insider",    Icon: Users      },
    { id: "confidence", label: "Confidence", Icon: Cpu        },
  ];

  return (
    <div className="h-screen overflow-hidden bg-[#070710]">
      {/* Ambient glow */}
      <div className="pointer-events-none fixed inset-0" aria-hidden>
        <div className="absolute -left-32 -top-32 h-[600px] w-[600px] rounded-full bg-indigo-700/6 blur-[160px]" />
        <div className="absolute -bottom-32 -right-16 h-[500px] w-[500px] rounded-full bg-violet-700/5 blur-[120px]" />
        <div className="absolute inset-0 opacity-[0.018]"
          style={{ backgroundImage: "radial-gradient(circle, #fff 1px, transparent 1px)", backgroundSize: "28px 28px" }} />
      </div>

      {/* ── Topbar ─────────────────────────────────────────────────────────── */}
      <header className="relative z-20 flex h-14 items-center justify-between border-b border-white/[0.05] px-6">
        <div className="flex items-center gap-3">
          <a href="/" className="flex items-center gap-2 opacity-90 hover:opacity-100 transition-opacity">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600/20 ring-1 ring-indigo-500/25">
              <Activity className="h-3.5 w-3.5 text-indigo-400" />
            </div>
            <span className="font-black tracking-tight text-white">Hedge Fund AI</span>
          </a>
          <span className="font-mono text-[9px] text-zinc-700">v3.0 · LangGraph</span>
        </div>
        <div className="flex items-center gap-2">
          {[{ l:"Graph", a:false }, { l:"RAG", a:false }, { l:"Live SSE", a:true }].map(({ l, a }) => (
            <span key={l} className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[9px] ${a ? "border-emerald-500/25 bg-emerald-500/8 text-emerald-400" : "border-white/5 text-zinc-700"}`}>
              {a && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />}{l}
            </span>
          ))}
          {(isRunning || isDone) && (
            <button onClick={reset} className="ml-1 flex items-center gap-1.5 rounded-lg border border-white/5 px-3 py-1.5 font-mono text-[9px] text-zinc-600 hover:text-zinc-300 transition-colors">
              <RefreshCw className="h-2.5 w-2.5" /> Reset
            </button>
          )}
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <div className="relative z-10 flex h-[calc(100vh-56px)] overflow-hidden">

        {/* ── Left sidebar ─────────────────────────────────────────────────── */}
        <aside className="flex w-[390px] flex-shrink-0 flex-col gap-4 overflow-y-auto border-r border-white/[0.05] p-5 scrollbar-thin">
          <div className="rounded-2xl border border-white/[0.06] bg-[#0d0d14]/80 p-5 backdrop-blur-xl">
            <p className="mb-4 font-mono text-[9px] uppercase tracking-[0.3em] text-zinc-600">Research Terminal</p>
            <StockSearch onAnalyse={analyse} isRunning={isRunning} />
          </div>

          <div className="flex-1 rounded-2xl border border-white/[0.06] bg-[#0d0d14]/80 p-5 backdrop-blur-xl">
            <p className="mb-4 font-mono text-[9px] uppercase tracking-[0.3em] text-zinc-600">Agent Execution</p>
            <AgentTimeline agents={state.agents} reasoningLog={state.reasoningLog} currentStep={state.currentStep} progress={state.progress} />
          </div>

          <AnimatePresence>
            {isDone && state.thesis && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className="rounded-2xl border border-white/[0.06] bg-[#0d0d14]/80 p-5 backdrop-blur-xl">
                <FeedbackPanel onSubmit={submitFeedback} />
              </motion.div>
            )}
          </AnimatePresence>
        </aside>

        {/* ── Right panel ──────────────────────────────────────────────────── */}
        <main className="flex flex-1 flex-col overflow-hidden">

          {/* Tab bar */}
          <AnimatePresence>
            {isDone && state.thesis && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="flex items-center gap-1 border-b border-white/[0.05] px-5 py-2">
                {TABS.map(({ id, label, Icon }) => (
                  <button key={id} onClick={() => setTab(id)}
                    className={`flex items-center gap-1.5 rounded-lg px-3 py-2 font-mono text-[11px] transition-all ${tab === id ? "bg-indigo-600/20 text-indigo-300" : "text-zinc-600 hover:text-zinc-400"}`}>
                    <Icon className="h-3 w-3" />{label}
                  </button>
                ))}
                {state.cached && (
                  <span className="ml-auto flex items-center gap-1 rounded-full border border-indigo-500/25 bg-indigo-500/8 px-2 py-0.5 font-mono text-[9px] text-indigo-400">
                    ⚡ cached · {state.latencyMs?.toFixed(0)}ms
                  </span>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6">

            {/* Idle placeholder */}
            {state.status === "idle" && (
              <div className="flex h-full flex-col items-center justify-center gap-5">
                <motion.div animate={{ y: [0, -8, 0] }} transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                  className="flex h-24 w-24 items-center justify-center rounded-3xl border border-white/5 bg-white/2">
                  <BarChart3 className="h-12 w-12 text-zinc-800" />
                </motion.div>
                <div className="text-center">
                  <p className="font-mono text-sm text-zinc-600">Enter a ticker to begin</p>
                  <p className="mt-1 font-mono text-[10px] text-zinc-800">LangGraph · 3 agents · RAG · Generator-Critic · SSE</p>
                </div>
                {/* Mini feature grid */}
                <div className="mt-2 grid grid-cols-3 gap-3">
                  {[["RSI · MACD · Bollinger", TrendingUp], ["SEC EDGAR + RAG", Database], ["Experience Bank", Cpu]].map(([label, Icon]: any, i) => (
                    <div key={i} className="rounded-xl border border-white/5 bg-white/2 p-3 text-center">
                      <Icon className="mx-auto mb-1 h-4 w-4 text-zinc-700" />
                      <p className="font-mono text-[9px] text-zinc-700">{label}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Error */}
            {state.status === "error" && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="rounded-2xl border border-red-500/20 bg-red-500/5 p-6">
                <p className="font-mono text-sm text-red-400">⚠ {state.error}</p>
                <button onClick={reset} className="mt-3 font-mono text-xs text-zinc-600 underline underline-offset-4 hover:text-zinc-300">Reset</button>
              </motion.div>
            )}

            {/* Results */}
            <AnimatePresence mode="wait">
              {isDone && state.thesis && (
                <>
                  {tab === "thesis" && (
                    <motion.div key="thesis" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                      className="rounded-2xl border border-white/[0.06] bg-[#0d0d14]/80 p-6 backdrop-blur-xl">
                      <ThesisCard thesis={state.thesis} cached={state.cached} latencyMs={state.latencyMs ?? 0} />
                    </motion.div>
                  )}

                  {tab === "technical" && (
                    <motion.div key="tech" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                      className="rounded-2xl border border-white/[0.06] bg-[#0d0d14]/80 p-6 backdrop-blur-xl">
                      {state.technicals
                        ? <TechnicalCharts indicators={state.technicals} ticker={state.thesis.ticker} />
                        : <p className="font-mono text-sm text-zinc-600 text-center py-12">Technical indicators not available for this ticker.</p>}
                    </motion.div>
                  )}

                  {tab === "sentiment" && (
                    <motion.div key="sent" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                      className="rounded-2xl border border-white/[0.06] bg-[#0d0d14]/80 p-6 backdrop-blur-xl">
                      <SentimentHeatmap
                        sentimentScore={0} sentiment="NEUTRAL" headlineCount={0} keyThemes={[]}
                        sentimentAssessment={state.thesis.sentiment_assessment}
                      />
                    </motion.div>
                  )}

                  {tab === "insider" && (
                    <motion.div key="ins" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                      className="rounded-2xl border border-white/[0.06] bg-[#0d0d14]/80 p-6 backdrop-blur-xl">
                      <InsiderTracker trades={[]} ticker={state.thesis.ticker} />
                    </motion.div>
                  )}

                  {tab === "confidence" && (
                    <motion.div key="conf" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                      className="rounded-2xl border border-white/[0.06] bg-[#0d0d14]/80 p-6 backdrop-blur-xl">
                      <ConfidenceScoring
                        thesis={state.thesis}
                        agentsCompleted={Object.values(state.agents).filter(a => a.status === "success").map(a => a.name)}
                        agentsFailed={Object.values(state.agents).filter(a => a.status === "failed").map(a => a.name)}
                      />
                    </motion.div>
                  )}
                </>
              )}
            </AnimatePresence>
          </div>
        </main>
      </div>
    </div>
  );
}
