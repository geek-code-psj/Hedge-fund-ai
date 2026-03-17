// frontend/components/dashboard/FeedbackPanel.tsx
"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { ThumbsUp, ThumbsDown, MessageSquare, Star } from "lucide-react";
import { cn } from "@/lib/utils";

interface FeedbackPanelProps {
  onSubmit: (score: number, text?: string, correction?: string) => Promise<void>;
}

export function FeedbackPanel({ onSubmit }: FeedbackPanelProps) {
  const [score, setScore] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [correction, setCorrection] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    if (!score) return;
    setSubmitting(true);
    await onSubmit(score, text || undefined, correction || undefined);
    setSubmitting(false);
    setSubmitted(true);
  }

  if (submitted) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm text-emerald-400"
      >
        <ThumbsUp className="h-4 w-4" />
        Feedback stored in Experience Bank — will improve future analyses.
      </motion.div>
    );
  }

  return (
    <div className="rounded-xl border border-white/5 bg-white/2 p-4 space-y-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-zinc-500">
        Rate This Analysis
      </p>

      {/* Star rating */}
      <div className="flex items-center gap-2">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            onClick={() => setScore(n)}
            className="transition-transform hover:scale-110 active:scale-95"
          >
            <Star
              className={cn(
                "h-6 w-6 transition-colors",
                score !== null && n <= score
                  ? "fill-amber-400 text-amber-400"
                  : "fill-transparent text-zinc-700 hover:text-zinc-500"
              )}
            />
          </button>
        ))}
        {score && (
          <span className="ml-2 font-mono text-xs text-zinc-500">
            {["", "Poor", "Fair", "Good", "Great", "Excellent"][score]}
          </span>
        )}
      </div>

      {/* Text feedback */}
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Optional: What could be improved?"
        rows={2}
        className="w-full resize-none rounded-lg border border-white/5 bg-black/20 px-3 py-2 text-xs text-zinc-400 placeholder:text-zinc-700 focus:outline-none focus:border-white/10"
      />

      {/* Correction — feeds Experience Bank */}
      {score !== null && score <= 2 && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
          <p className="mb-1 font-mono text-[10px] text-zinc-600">
            Correction (stored in Experience Bank for prompt tuning):
          </p>
          <textarea
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            placeholder="Describe what was wrong and what the correct analysis should say…"
            rows={3}
            className="w-full resize-none rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-zinc-300 placeholder:text-zinc-700 focus:outline-none"
          />
        </motion.div>
      )}

      <button
        onClick={handleSubmit}
        disabled={!score || submitting}
        className={cn(
          "w-full rounded-lg py-2 font-mono text-xs font-bold transition-all",
          score
            ? "bg-indigo-600 text-white hover:bg-indigo-500 active:scale-98"
            : "cursor-not-allowed bg-white/5 text-zinc-700"
        )}
      >
        {submitting ? "Submitting…" : "Submit Feedback"}
      </button>
    </div>
  );
}
