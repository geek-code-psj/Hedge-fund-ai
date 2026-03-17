"use client";
import React from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  BarChart2,
  Brain,
  Database,
  GitBranch,
  Shield,
  Zap,
} from "lucide-react";
import { ContainerScroll } from "@/components/ui/container-scroll-animation";

// ── Feature cards shown below the scroll hero ─────────────────────────────────
const FEATURES = [
  { Icon: GitBranch, label: "LangGraph",       desc: "Fan-out / fan-in directed graph"        },
  { Icon: Brain,     label: "3 AI Agents",      desc: "News · Financial Data · Document RAG"  },
  { Icon: BarChart2, label: "Technical Suite",  desc: "RSI · MACD · Bollinger · SMA"          },
  { Icon: Database,  label: "RAG Pipeline",     desc: "SEC EDGAR + ChromaDB semantic search"  },
  { Icon: Zap,       label: "Semantic Cache",   desc: "RedisVL cosine similarity, 15-min TTL" },
  { Icon: Shield,    label: "Observability",    desc: "Arize Phoenix · MNPI-safe local trace" },
];

export default function LandingPage() {
  const router = useRouter();

  return (
    <main className="min-h-screen bg-[#070710] overflow-x-hidden">
      {/* ── Ambient background ─────────────────────────────────────────────── */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden>
        <div className="absolute left-1/4 top-0 h-[700px] w-[700px] -translate-x-1/2 rounded-full bg-indigo-600/6 blur-[160px]" />
        <div className="absolute right-0 top-1/3 h-[500px] w-[500px] rounded-full bg-violet-600/5 blur-[120px]" />
        <div
          className="absolute inset-0 opacity-[0.025]"
          style={{
            backgroundImage: "radial-gradient(circle, #ffffff 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />
      </div>

      {/* ── Nav ────────────────────────────────────────────────────────────── */}
      <nav className="relative z-20 flex items-center justify-between px-8 py-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 shadow-[0_0_20px_rgba(99,102,241,0.4)]">
            <Activity className="h-3.5 w-3.5 text-white" />
          </div>
          <span className="font-black tracking-tight text-white">Hedge Fund AI</span>
          <span className="rounded-full border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 font-mono text-[9px] text-indigo-400">
            v3.0
          </span>
        </div>
        <motion.button
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          onClick={() => router.push("/dashboard")}
          className="flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 font-mono text-sm font-bold text-white hover:bg-indigo-500 transition-colors"
        >
          Launch App <ArrowRight className="h-4 w-4" />
        </motion.button>
      </nav>

      {/* ── Hero text ──────────────────────────────────────────────────────── */}
      <div className="relative z-10 px-8 pt-12 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="space-y-5"
        >
          {/* Live badge */}
          <div className="flex justify-center">
            <div className="flex items-center gap-2 rounded-full border border-white/8 bg-white/3 px-4 py-1.5 backdrop-blur-sm">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
              <span className="font-mono text-xs text-zinc-400">
                LangGraph · RAG · SSE · Generator-Critic · Live
              </span>
            </div>
          </div>

          {/* Headline */}
          <h1 className="mx-auto max-w-4xl text-5xl font-black tracking-tight text-white md:text-7xl leading-[1.05]">
            Hedge-fund grade
            <br />
            <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-fuchsia-400 bg-clip-text text-transparent">
              AI equity research
            </span>
          </h1>

          <p className="mx-auto max-w-xl text-base text-zinc-500 leading-relaxed">
            Three concurrent agents — News, Financial Data, and Document RAG — orchestrated
            by LangGraph, reviewed by a Generator-Critic LLM, streaming to your screen in real time.
          </p>

          {/* CTAs */}
          <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-center pt-2">
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => router.push("/dashboard")}
              className="group flex items-center gap-2 rounded-2xl bg-indigo-600 px-8 py-3.5 font-bold text-white shadow-[0_0_30px_rgba(99,102,241,0.3)] hover:bg-indigo-500 transition-colors"
            >
              Start Analysing
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </motion.button>
            <a
              href="https://github.com"
              target="_blank"
              className="flex items-center gap-2 rounded-2xl border border-white/8 bg-white/3 px-8 py-3.5 font-mono text-sm text-zinc-400 backdrop-blur-sm hover:border-white/15 hover:text-zinc-200 transition-all"
            >
              View on GitHub
            </a>
          </div>
        </motion.div>
      </div>

      {/* ── ContainerScroll hero (spec-compliant) ──────────────────────────── */}
      <div className="relative z-10">
        <ContainerScroll
          titleComponent={
            <div className="mb-6">
              <p className="font-mono text-xs uppercase tracking-[0.3em] text-indigo-400 mb-3">
                Live glass execution view
              </p>
              <h2 className="text-2xl font-black text-white md:text-3xl">
                Watch three agents run{" "}
                <span className="bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">
                  in parallel
                </span>
              </h2>
            </div>
          }
        >
          {/* Dashboard screenshot — Unsplash finance/trading image */}
          <div className="relative h-full w-full overflow-hidden rounded-2xl bg-[#0d0d14]">
            <Image
              src="https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1400&q=80&fit=crop"
              alt="Financial analysis dashboard showing stock charts and data"
              fill
              className="object-cover object-top opacity-40"
              priority
              draggable={false}
            />
            {/* Overlay: mock dashboard UI */}
            <div className="relative z-10 h-full w-full p-4 flex flex-col gap-3">
              {/* Topbar */}
              <div className="flex items-center justify-between rounded-xl border border-white/5 bg-black/40 px-4 py-2 backdrop-blur-sm">
                <div className="flex items-center gap-2">
                  <div className="h-5 w-5 rounded-md bg-indigo-600/80 flex items-center justify-center">
                    <Activity className="h-3 w-3 text-white" />
                  </div>
                  <span className="font-black text-sm text-white">Hedge Fund AI</span>
                  <span className="font-mono text-[9px] text-zinc-600">AAPL · Live Analysis</span>
                </div>
                <div className="flex items-center gap-1.5">
                  {["Graph","RAG","SSE"].map((l, i) => (
                    <span key={l} className={`rounded-full border px-2 py-0.5 font-mono text-[8px] ${i===2 ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400" : "border-white/5 text-zinc-700"}`}>
                      {i===2 && <span className="mr-1 inline-block h-1 w-1 animate-pulse rounded-full bg-emerald-400 align-middle" />}
                      {l}
                    </span>
                  ))}
                </div>
              </div>

              {/* Agent cards row */}
              <div className="grid grid-cols-3 gap-2">
                {[
                  { name:"News Agent",       status:"✅", summary:"12 headlines · POSITIVE",      color:"emerald" },
                  { name:"Financial Agent",  status:"✅", summary:"$187.15 · RSI=52 · BULLISH",   color:"indigo"  },
                  { name:"Document Agent",   status:"✅", summary:"3 SEC filings · 5 risk factors",color:"violet"  },
                ].map((a) => (
                  <div key={a.name} className={`rounded-xl border border-${a.color}-500/20 bg-${a.color}-500/8 p-3`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-[10px] text-zinc-300">{a.name}</span>
                      <span className="text-xs">{a.status}</span>
                    </div>
                    <span className="font-mono text-[9px] text-zinc-500">{a.summary}</span>
                  </div>
                ))}
              </div>

              {/* Thesis card */}
              <div className="flex-1 rounded-xl border border-white/5 bg-black/40 p-4 backdrop-blur-sm">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl font-black text-white">AAPL</span>
                    <span className="rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-0.5 font-mono text-xs font-bold text-emerald-400">
                      BUY
                    </span>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-sm text-white font-bold">$195.00 target</div>
                    <div className="font-mono text-[10px] text-zinc-500">+4.2% upside · 72% conviction</div>
                  </div>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed line-clamp-3">
                  Apple demonstrates solid fundamentals with $119.6B Q1 revenue (+2.1% YoY), 26.2% net margin,
                  and $23B free cash flow. Services flywheel at 35% gross margin and AI upgrade cycle provide
                  clear upside catalysts. China exposure remains the primary risk.
                </p>
                {/* Technical indicators row */}
                <div className="mt-3 grid grid-cols-4 gap-2">
                  {[
                    { l:"RSI",     v:"52.4",   s:"NEUTRAL",      c:"zinc"    },
                    { l:"MACD",    v:"+0.58",  s:"BULLISH",      c:"emerald" },
                    { l:"SMA",     v:"2/3↑",   s:"BULLISH",      c:"emerald" },
                    { l:"BB %B",   v:"50%",    s:"MID RANGE",    c:"zinc"    },
                  ].map((t) => (
                    <div key={t.l} className="rounded-lg border border-white/5 bg-white/2 px-2 py-1.5">
                      <div className="font-mono text-[8px] text-zinc-600">{t.l}</div>
                      <div className="font-mono text-sm font-bold text-white">{t.v}</div>
                      <div className={`font-mono text-[8px] text-${t.c}-400`}>{t.s}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Progress bar footer */}
              <div className="flex items-center gap-3 rounded-xl border border-white/5 bg-black/30 px-3 py-2">
                <div className="flex-1 h-1 overflow-hidden rounded-full bg-white/5">
                  <div className="h-full w-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" />
                </div>
                <span className="font-mono text-[9px] text-emerald-400">✓ Done · 4,320ms</span>
              </div>
            </div>
          </div>
        </ContainerScroll>
      </div>

      {/* ── Feature grid ───────────────────────────────────────────────────── */}
      <div className="relative z-10 mx-auto max-w-5xl px-8 pb-24 -mt-16">
        <div className="mb-10 text-center">
          <h2 className="text-3xl font-black text-white">Production-grade infrastructure</h2>
          <p className="mt-2 text-zinc-500 text-sm">Every layer engineered for reliability and free deployment.</p>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          {FEATURES.map(({ Icon, label, desc }, i) => (
            <motion.div
              key={label}
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05, duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              className="rounded-2xl border border-white/[0.06] bg-[#0d0d14]/80 p-5 backdrop-blur-xl hover:border-indigo-500/20 transition-colors"
            >
              <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-xl border border-indigo-500/20 bg-indigo-500/10">
                <Icon className="h-4 w-4 text-indigo-400" />
              </div>
              <h3 className="font-bold text-white text-sm">{label}</h3>
              <p className="mt-0.5 text-xs text-zinc-500">{desc}</p>
            </motion.div>
          ))}
        </div>
      </div>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-white/5 px-8 py-5 text-center">
        <p className="font-mono text-xs text-zinc-800">
          FastAPI · LangGraph · Next.js 15 · shadcn/ui · Arize Phoenix · DeepEval
        </p>
      </footer>
    </main>
  );
}
