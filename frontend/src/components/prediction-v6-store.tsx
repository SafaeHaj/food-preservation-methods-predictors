"use client";

import * as React from "react";
import type {
  CheeseCatalogEntry, CheeseCategory, ModelTask, PhysicalFormOption,
  PredictV6Result, ResolvedSupport, SchemaV6Data,
} from "@/lib/api";

export type FlowStep = "cheese" | "form" | "profile" | "conditions" | "results";

export interface TreatmentState {
  ingredientName: string;
  ingredientFamily: string | null;
  concentration: number;
  concentrationUnit: string;
  applicationMethod: string;
  treatmentType: string;
}

export const NO_TREATMENT: TreatmentState = {
  ingredientName: "none",
  ingredientFamily: "none",
  concentration: 0,
  concentrationUnit: "none",
  applicationMethod: "none",
  treatmentType: "none",
};

export interface PredictionV6State {
  step: FlowStep;

  // Cheese identity
  baseCheeseName: string | null;
  entry: CheeseCatalogEntry | null; // resolved (cheeseCategory + foodMatrix)
  cheeseCategory: CheeseCategory | null;
  foodMatrix: string | null;

  // Physical presentation
  physicalForm: string | null;
  physicalFormOption: PhysicalFormOption | null; // carries source/confidence/support
  supportLevel: ResolvedSupport | null;

  // Schemas for both tasks of the resolved category (fetched once category known)
  generalSchema: SchemaV6Data | null;
  safetySchema: SchemaV6Data | null;
  modelTask: ModelTask;

  // Conditions
  storageTemperatureC: number | null;
  matrixValues: Record<string, unknown>;
  packagingType: string | null;
  headspaceOxygenPct: number | null;
  headspaceCo2Pct: number | null;
  headspaceN2Pct: number | null;
  pasteurizationApplied: boolean;
  indicatorGroup: string | null;
  indicatorType: string | null;
  indicatorUnit: string | null;
  indicatorThreshold: number | null;
  initialIndicatorValue: number | null;
  treatment: TreatmentState;

  result: PredictV6Result | null;
}

const initialState: PredictionV6State = {
  step: "cheese",
  baseCheeseName: null,
  entry: null,
  cheeseCategory: null,
  foodMatrix: null,
  physicalForm: null,
  physicalFormOption: null,
  supportLevel: null,
  generalSchema: null,
  safetySchema: null,
  modelTask: "general_shelf_life",
  storageTemperatureC: null,
  matrixValues: {},
  packagingType: null,
  headspaceOxygenPct: null,
  headspaceCo2Pct: null,
  headspaceN2Pct: null,
  pasteurizationApplied: true,
  indicatorGroup: null,
  indicatorType: null,
  indicatorUnit: null,
  indicatorThreshold: null,
  initialIndicatorValue: null,
  treatment: { ...NO_TREATMENT },
  result: null,
};

type Action =
  | { type: "goto"; step: FlowStep }
  | { type: "selectCheese"; baseCheeseName: string; entry: CheeseCatalogEntry }
  | { type: "selectPhysicalForm"; option: PhysicalFormOption }
  | { type: "setSchemas"; general: SchemaV6Data; safety: SchemaV6Data | null }
  | { type: "setCondition"; patch: Partial<PredictionV6State> }
  | { type: "setTreatment"; patch: Partial<TreatmentState> }
  | { type: "selectEndpoint"; group: string; indicatorType: string; unit: string; task: ModelTask }
  | { type: "setResult"; result: PredictV6Result }
  | { type: "changeCheese" }
  | { type: "changePresentation" }
  | { type: "reset" };

function reducer(state: PredictionV6State, action: Action): PredictionV6State {
  switch (action.type) {
    case "goto":
      return { ...state, step: action.step };
    case "selectCheese":
      // Changing the cheese invalidates everything downstream: physical form,
      // schemas, conditions, treatment, result -- only the step advances.
      // foodMatrix is not known yet at this point -- it lives on each
      // physical-form option (see CheeseCatalogEntry doc), set once the user
      // picks a form in the next step.
      return {
        ...initialState,
        step: "form",
        baseCheeseName: action.baseCheeseName,
        entry: action.entry,
        cheeseCategory: action.entry.cheeseCategory,
      };
    case "selectPhysicalForm":
      return {
        ...state,
        step: "profile",
        physicalForm: action.option.physicalForm,
        foodMatrix: action.option.foodMatrix,
        physicalFormOption: action.option,
        supportLevel: action.option.support,
      };
    case "setSchemas": {
      const g = action.general;
      return {
        ...state,
        generalSchema: g,
        safetySchema: action.safety,
        storageTemperatureC: state.storageTemperatureC ?? g.numeric_ranges.storage_temperature_c?.median ?? 4,
        packagingType: state.packagingType ?? g.categorical_modes.packaging_type ?? g.categorical_options.packaging_type?.[0] ?? null,
        headspaceOxygenPct: state.headspaceOxygenPct ?? g.numeric_ranges.headspace_oxygen_pct?.median ?? 0,
        headspaceCo2Pct: state.headspaceCo2Pct ?? g.numeric_ranges.headspace_co2_pct?.median ?? 0,
        headspaceN2Pct: state.headspaceN2Pct ?? g.numeric_ranges.headspace_n2_pct?.median ?? 0,
        indicatorGroup: state.indicatorGroup ?? g.categorical_modes.indicator_group ?? null,
        indicatorType: state.indicatorType ?? g.categorical_modes.indicator_type ?? null,
        indicatorUnit: state.indicatorUnit ?? g.categorical_modes.indicator_unit ?? null,
        indicatorThreshold: state.indicatorThreshold ?? g.numeric_ranges.indicator_threshold?.median ?? 0,
        initialIndicatorValue: state.initialIndicatorValue ?? g.numeric_ranges.initial_indicator_value?.median ?? 0,
        matrixValues:
          Object.keys(state.matrixValues).length > 0
            ? state.matrixValues
            : Object.fromEntries(
                ["matrix_ph", "matrix_water_activity", "matrix_moisture_pct", "matrix_fat_pct", "matrix_protein_pct", "matrix_salt_pct", "matrix_ripening_days"]
                  .map((c) => [c, g.numeric_ranges[c]?.median ?? 0]),
              ),
      };
    }
    case "setCondition":
      return { ...state, ...action.patch };
    case "setTreatment":
      return { ...state, treatment: { ...state.treatment, ...action.patch } };
    case "selectEndpoint":
      return {
        ...state,
        indicatorGroup: action.group,
        indicatorType: action.indicatorType,
        indicatorUnit: action.unit,
        modelTask: action.task,
      };
    case "setResult":
      return { ...state, step: "results", result: action.result };
    case "changeCheese":
      return { ...initialState, step: "cheese" };
    case "changePresentation":
      return { ...state, step: "form", physicalForm: null, physicalFormOption: null, supportLevel: null };
    case "reset":
      return initialState;
    default:
      return state;
  }
}

interface PredictionV6ContextValue {
  state: PredictionV6State;
  dispatch: React.Dispatch<Action>;
}

const PredictionV6Context = React.createContext<PredictionV6ContextValue | null>(null);

export function PredictionV6StoreProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = React.useReducer(reducer, initialState);
  const value = React.useMemo(() => ({ state, dispatch }), [state]);
  return <PredictionV6Context.Provider value={value}>{children}</PredictionV6Context.Provider>;
}

export function usePredictionV6() {
  const ctx = React.useContext(PredictionV6Context);
  if (!ctx) throw new Error("usePredictionV6 must be used within PredictionV6StoreProvider");
  return ctx;
}
