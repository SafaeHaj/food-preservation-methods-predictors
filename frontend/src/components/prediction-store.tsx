"use client";

import * as React from "react";
import type { PredictResult } from "@/lib/api";

interface PredictionStoreValue {
  lastPrediction: PredictResult | null;
  setLastPrediction: (result: PredictResult | null) => void;
}

const PredictionContext = React.createContext<PredictionStoreValue | null>(null);

/**
 * Mirrors the previous Dash app's dcc.Store(id="last-prediction-store"):
 * holds the most recent prediction result in memory only, shared between
 * the /prediction, /results, and /explainability pages via this provider
 * mounted once in the root layout. No backend session, no persistence --
 * a fresh page load starts empty, same as the Dash version did.
 */
export function PredictionStoreProvider({ children }: { children: React.ReactNode }) {
  const [lastPrediction, setLastPrediction] = React.useState<PredictResult | null>(null);
  const value = React.useMemo(() => ({ lastPrediction, setLastPrediction }), [lastPrediction]);
  return <PredictionContext.Provider value={value}>{children}</PredictionContext.Provider>;
}

export function usePredictionStore() {
  const ctx = React.useContext(PredictionContext);
  if (!ctx) throw new Error("usePredictionStore must be used within PredictionStoreProvider");
  return ctx;
}
