"use client";

import { useEffect, useState } from "react";
import { backendAvailable, loadComparison, loadEval, loadRecordingIndex, type ComparisonSummary, type EvalSummary, type RecordingIndexEntry } from "./api";

/** Published results (recordings, comparison, evaluation) and whether a live backend is reachable. */
export function useData() {
  const [index, setIndex] = useState<RecordingIndexEntry[] | null>(null);
  const [comparison, setComparison] = useState<ComparisonSummary | null>(null);
  const [evaluation, setEvaluation] = useState<EvalSummary | null>(null);
  const [live, setLive] = useState<boolean | null>(null);
  useEffect(() => {
    loadRecordingIndex()
      .then(setIndex)
      .catch(() => setIndex([]));
    loadComparison().then(setComparison);
    loadEval().then(setEvaluation);
    backendAvailable().then(setLive);
  }, []);
  return { index, comparison, evaluation, live };
}

export const kTokens = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}K` : String(n));
export const minutes = (sec: number) => (sec < 60 ? `${Math.round(sec)} s` : `${(sec / 60).toFixed(1)} min`);
export const fmtDate = (unix?: number) =>
  unix ? new Date(unix * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
