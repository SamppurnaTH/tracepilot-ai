"use client";

import { useEffect, useState } from "react";
import { backendAvailable, loadComparison, loadEval, loadRecordingIndex, type ComparisonSummary, type EvalSummary, type RecordingIndexEntry } from "./api";

/** Published results (recordings, comparison, evaluation) and whether a live backend is reachable. */
export function useData() {
  const [index, setIndex] = useState<RecordingIndexEntry[] | null>(null);
  const [comparison, setComparison] = useState<ComparisonSummary | null>(null);
  const [evaluation, setEvaluation] = useState<EvalSummary | null>(null);
  const [indexError, setIndexError] = useState(false);
  const [comparisonLoading, setComparisonLoading] = useState(true);
  const [live, setLive] = useState<boolean | null>(null);
  useEffect(() => {
    loadRecordingIndex()
      .then(setIndex)
      .catch(() => { setIndex([]); setIndexError(true); });
    loadComparison().then(setComparison).catch(() => setComparison(null)).finally(() => setComparisonLoading(false));
    loadEval().then(setEvaluation).catch(() => setEvaluation(null));
    backendAvailable().then(setLive);
  }, []);
  return { index, comparison, evaluation, live, indexError, comparisonLoading };
}

export const kTokens = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}K` : String(n));
/** A duration, exact to the second: "45s", "1m 43s". */
export const minutes = (sec: number) => {
  const total = Math.max(0, Math.round(sec));
  return total < 60 ? `${total}s` : `${Math.floor(total / 60)}m ${String(total % 60).padStart(2, "0")}s`;
};
export const fmtDate = (unix?: number) =>
  unix ? new Date(unix * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
