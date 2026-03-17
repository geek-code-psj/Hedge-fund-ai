// frontend/components/agents/AgentTimeline.tsx
"use client";

import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle, XCircle, Loader2, Clock, Cpu, FileText, TrendingUp, Newspaper } from "lucide-react";
import { cn, agentLabel } from "@/lib/utils";
import type { AgentStatus } from "@/types";

const AGENT_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  news_agent: Newspaper,
  financial_data_agent: TrendingUp,
  document_agent: FileText,
  orchestrator_node: Cpu,
  reviewer_node: Cpu,
};

interface AgentTimelineProps {
  agents: Record<string, AgentStatus>;
  reasoningLog: string[];
  currentStep: string;
  progress: number;
}

export function AgentTimeline({ agents, reasoningLog, currentStep, progress }: AgentTimelineProps) {
  const agentList = Object.values(agents);

  return (
    <div className="flex h-full flex-col gap-6">
      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-zinc-500 uppercase tracking-widest">Pipeline</span>
          <span className="font-mono text-xs text-indigo-400">{progress}%</span>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-white/5">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500"
            animate={{ width: `${progress}%` }}
            transition={{ ease: "easeOut", duration: 0.4 }}
          />
        </div>
        <p className="font-mono text-xs text-zinc-500 truncate">{currentStep}</p>
      </div>

      {/* Agent cards */}
      <div className="grid grid-cols-3 gap-3">
        {agentList.map((agent) => {
          const Icon = AGENT_ICONS[agent.name] ?? Cpu;
          return (
            <motion.div
              key={agent.name}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={cn(
                "relative overflow-hidden rounded-xl border p-3 transition-all duration-500",
                agent.status === "pending" && "border-white/5 bg-white/2",
                agent.status === "running" && "border-indigo-500/40 bg-indigo-500/5",
                agent.status === "success" && "border-emerald-500/30 bg-emerald-500/5",
                agent.status === "failed" && "border-red-500/30 bg-red-500/5"
              )}
            >
              {/* Running shimmer */}
              {agent.status === "running" && (
                <motion.div
                  className="absolute inset-0 bg-gradient-to-r from-transparent via-indigo-500/10 to-transparent"
                  animate={{ x: ["-100%", "100%"] }}
                  transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                />
              )}

              <div className="relative flex items-start gap-2">
                <div className={cn(
                  "mt-0.5 rounded-lg p-1.5",
                  agent.status === "running" && "bg-indigo-500/20",
                  agent.status === "success" && "bg-emerald-500/20",
                  agent.status === "failed" && "bg-red-500/20",
                  agent.status === "pending" && "bg-white/5",
                )}>
                  <Icon className={cn(
                    "h-3.5 w-3.5",
                    agent.status === "running" && "text-indigo-400",
                    agent.status === "success" && "text-emerald-400",
                    agent.status === "failed" && "text-red-400",
                    agent.status === "pending" && "text-zinc-600",
                  )} />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-1">
                    <p className="truncate text-xs font-medium text-zinc-300">{agent.label}</p>
                    <StatusIcon status={agent.status} />
                  </div>
                  {agent.summary && (
                    <p className="mt-0.5 truncate text-[10px] text-zinc-500">{agent.summary}</p>
                  )}
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Reasoning log — glass terminal */}
      <div className="flex-1 overflow-hidden rounded-xl border border-white/5 bg-black/30">
        <div className="flex items-center gap-1.5 border-b border-white/5 px-3 py-2">
          <div className="h-2 w-2 rounded-full bg-red-500/70" />
          <div className="h-2 w-2 rounded-full bg-amber-500/70" />
          <div className="h-2 w-2 rounded-full bg-emerald-500/70" />
          <span className="ml-2 font-mono text-[10px] text-zinc-600">agent_reasoning.log</span>
        </div>
        <div className="h-[220px] overflow-y-auto p-3 space-y-1">
          <AnimatePresence initial={false}>
            {reasoningLog.map((line, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                className="font-mono text-[10px] leading-relaxed text-zinc-400"
              >
                <span className="text-zinc-700 select-none">{String(i + 1).padStart(3, "0")} </span>
                {line}
              </motion.div>
            ))}
          </AnimatePresence>
          {reasoningLog.length === 0 && (
            <p className="font-mono text-[10px] text-zinc-700">Waiting for pipeline to start…</p>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: AgentStatus["status"] }) {
  if (status === "running") return <Loader2 className="h-3 w-3 animate-spin text-indigo-400" />;
  if (status === "success") return <CheckCircle className="h-3 w-3 text-emerald-400" />;
  if (status === "failed") return <XCircle className="h-3 w-3 text-red-400" />;
  return <Clock className="h-3 w-3 text-zinc-700" />;
}
