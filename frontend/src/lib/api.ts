// Thin fetch wrapper around the FastAPI backend (backend/main.py). This file
// contains NO business logic of its own -- every number rendered by the app
// comes from these endpoints, which are themselves a pass-through to
// model_service.py. Never call the training script from here.

const API_PORT = process.env.NEXT_PUBLIC_API_PORT ?? "8010";

/**
 * Resolve the API origin against the host the page is actually being served
 * from.
 *
 * This matters for auth, not just tidiness: `localhost` and `127.0.0.1` are
 * distinct hosts as far as cookies are concerned. If the page is on
 * localhost:3000 and the API is hardcoded to 127.0.0.1:8010, the session
 * cookie gets stored against 127.0.0.1 and is never sent back — every request
 * looks signed-out. Deriving the hostname keeps them on the same host whichever
 * one you browse to. NEXT_PUBLIC_API_BASE still overrides for real deployments.
 */
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ??
  (typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:${API_PORT}`
    : `http://localhost:${API_PORT}`);

/** Error carrying the HTTP status, so callers can branch on 401/409/422 rather
 *  than string-matching a message. `detail` is FastAPI's error text. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

function extractDetail(status: number, body: string): string {
  try {
    const parsed = JSON.parse(body);
    const d = parsed?.detail;
    if (typeof d === "string") return d;
    // FastAPI validation errors arrive as [{loc, msg, type}, ...]
    if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  } catch {
    /* not JSON — fall through to the generic message */
  }
  return body || `Request failed (${status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      // Let the browser set the multipart boundary itself for FormData.
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers ?? {}),
    },
    // Required for the httpOnly session cookie to be sent/stored — the API is
    // a different origin (port) than the app.
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, extractDetail(res.status, body));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface ManifestData {
  created_at_utc: string;
  random_seed: number;
  dataset_path: string;
  sheet: string;
  n_total: number;
  n_real_paper_derived: number;
  n_synthetic: number;
  n_train: number;
  n_validation: number;
  n_test: number;
  n_contexts_total: number;
  models_trained: string[];
  lstm_available: boolean;
  best_model_by_validation_rmse: string;
  total_training_duration_sec: number;
}

export interface SchemaData {
  target: string;
  numeric_columns: string[];
  categorical_columns: string[];
  binary_columns: string[];
  all_feature_columns: string[];
  categorical_options: Record<string, string[]>;
  categorical_modes: Record<string, string>;
  numeric_ranges: Record<string, { min: number; max: number; median: number }>;
  control_template: Record<string, unknown>;
}

export interface ModelSummary {
  id: string;
  label: string;
  blurb: string;
  is_best: boolean;
  validation_r2: number;
  test_r2: number;
  validation_rmse: number;
  test_rmse: number;
  validation_mae: number;
  test_mae: number;
  training_duration_sec: number;
  n_trainable_params: number | null;
}

export interface ModelsResponse {
  best_model: string;
  models: ModelSummary[];
  manifest: ManifestData;
}

export interface ModelDetails {
  id: string;
  label: string;
  metrics: Record<string, number | null>;
  curves: {
    type: "loss_curve" | "learning_curve";
    train_loss?: number[];
    val_loss?: number[];
    train_sizes?: number[];
    train_r2?: number[];
    val_r2?: number[];
  } | null;
  feature_importance: {
    native?: Record<string, number>;
    permutation?: Record<string, number>;
  };
  category_errors: Record<string, Record<string, { mae: number; n: number }>>;
  scatter: {
    train: { y_true: number; y_pred: number }[];
    validation: { y_true: number; y_pred: number }[];
    test: { y_true: number; y_pred: number }[];
  };
}

export interface SyntheticDataset {
  total_rows: number;
  contexts: number;
  controls: number;
  treatments: number;
  target_min: number;
  target_max: number;
  ingredient_families: Record<string, number>;
  storage_temperature_histogram: number[];
  storage_temperature_bin_edges: number[];
  shelf_life_histogram: number[];
  shelf_life_bin_edges: number[];
  generation_method: string;
  has_real_subset: boolean;
  schema_preview: { column: string; role: string; dtype: string; missing_pct: number; example: unknown }[];
}

export interface RealDataset {
  total_rows: number;
  has_real_subset: boolean;
  source_studies: { doi: string; rows: number; food_matrices: string[] }[];
  generation_rules: Record<string, number>;
  quality_flags: Record<string, number>;
  food_matrices: Record<string, number>;
  provenance_note: string;
}

export interface ReferencesData {
  sources: { doi: string; rows: number; food_matrices: string[] }[];
  n_real_rows: number;
  n_synthetic_rows: number;
  synthetic_method: string;
  generation_rules: Record<string, number>;
}

export interface CandidateInput {
  name: string;
  treatment_type: string;
  application_method: string;
  primary_ingredient_name: string;
  primary_concentration: number;
  primary_concentration_unit: string;
  primary_ingredient_family?: string | null;
}

export interface CandidateResult {
  candidate_name: string;
  model: string;
  model_label: string;
  predicted_candidate_shelf_life: number;
  predicted_control_shelf_life: number;
  absolute_improvement_days: number;
  relative_improvement_pct: number | null;
  shelf_life_ratio: number | null;
  lower_bound: number;
  upper_bound: number;
  warnings: string[];
  row: Record<string, unknown>;
  rank: number;
}

export interface PredictResult {
  control: {
    model: string;
    model_label: string;
    prediction_days: number;
    lower_bound: number;
    upper_bound: number;
    warnings: string[];
  };
  candidates: CandidateResult[];
}

export interface AssistantChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AssistantToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result: unknown;
}

export interface AssistantChatResponse {
  reply: string;
  tool_calls: AssistantToolCall[];
}

// ── Classification (formulation efficacy class) ──────────────────────────

export interface ClassDefinitions {
  class_names: string[];
  thresholds_pct: { low_max: number; medium_max: number };
  description: string;
}

export interface ClassificationManifest {
  created_at_utc: string;
  random_seed: number;
  dataset_path: string;
  sheet: string;
  n_total_treated_rows: number;
  n_train: number;
  n_validation: number;
  n_test: number;
  models_trained: string[];
  best_model_by_test_macro_f1: string;
  total_training_duration_sec: number;
  class_definitions: ClassDefinitions;
}

export interface ClassificationDistribution {
  overall: Record<string, number>;
  by_split: Record<string, Record<string, number>>;
  by_ingredient_family: Record<string, Record<string, number>>;
  by_cheese_category: Record<string, Record<string, number>>;
}

export interface PerClassMetric {
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface ClassificationSplitMetrics {
  accuracy: number;
  macro_f1: number;
  per_class: Record<string, PerClassMetric>;
}

export interface ClassificationModelSummary {
  id: string;
  label: string;
  blurb: string;
  is_best: boolean;
  test_accuracy: number;
  test_macro_f1: number;
  validation_accuracy: number;
  validation_macro_f1: number;
  training_duration_sec: number;
}

export interface ClassificationModelsResponse {
  best_model: string;
  models: ClassificationModelSummary[];
  manifest: ClassificationManifest;
  class_definitions: ClassDefinitions;
}

export interface ClassificationModelDetails {
  id: string;
  label: string;
  metrics: {
    train: ClassificationSplitMetrics;
    validation: ClassificationSplitMetrics;
    test: ClassificationSplitMetrics;
    training_duration_sec: number;
  };
  confusion_matrix: { labels: string[]; matrix: number[][] };
  feature_importance: { native?: Record<string, number>; permutation?: Record<string, number> };
}

export interface ClassificationCandidateInput {
  name: string;
  treatment_type: string;
  application_method: string;
  primary_ingredient_name: string;
  primary_concentration: number;
  primary_concentration_unit: string;
  primary_ingredient_family?: string | null;
}

export interface ClassificationResult {
  candidate_name: string;
  model: string;
  model_label: string;
  predicted_class: string;
  probabilities: Record<string, number>;
  warnings: string[];
  row: Record<string, unknown>;
}

export interface ClassificationPredictResult {
  results: ClassificationResult[];
  class_definitions: ClassDefinitions;
}

// ── Ingredient efficacy ranking ────────────────────────────────────────────

export interface IngredientRankingClassDefinitions {
  class_names: string[];
  primary_method: string;
  thresholds_pct: { low_max: number; medium_max: number };
  descriptive_thresholds_pct: { low_max: number; medium_max: number };
  min_samples_for_confidence: number;
  description: string;
}

export interface IngredientRankingManifest {
  created_at_utc: string;
  random_seed: number;
  dataset_path: string;
  sheet: string;
  n_ingredients: number;
  n_train_rows: number;
  n_validation_rows: number;
  n_test_rows: number;
  min_samples_for_confidence: number;
  n_low_confidence: number;
  regression_covariates: { numeric: string[]; categorical: string[] };
  regression_alpha: number;
  regression_in_sample_r2: number;
  descriptive_vs_adjusted_agreement_pct: number;
  rank_stability_spearman_vs_test_split: number | null;
  total_duration_sec: number;
  class_definitions: IngredientRankingClassDefinitions;
}

export interface IngredientRanking {
  ingredient_name: string;
  ingredient_family: string;
  adjusted_effect_pct: number;
  descriptive_mean_pct: number;
  descriptive_std_pct: number;
  descriptive_median_pct: number;
  descriptive_min_pct: number;
  descriptive_max_pct: number;
  n_train: number;
  n_validation: number;
  n_test: number;
  validation_mean_pct: number | null;
  test_mean_pct: number | null;
  low_confidence: boolean;
  rank: number;
  efficacy_class: string;
  efficacy_class_descriptive: string;
}

export interface IngredientRankingsResponse {
  rankings: IngredientRanking[];
  families: string[];
  class_definitions: IngredientRankingClassDefinitions;
}

// ── V6 specialist architecture (cheese_category x model_task routing) ─────

export type CheeseCategory = "soft" | "semi_hard" | "hard";
export type ModelTask = "general_shelf_life" | "safety_endpoint";
export type SupportLevel = "strong" | "moderate" | "limited" | "unsupported" | "experimental";

export interface ResolvedSupport {
  level: SupportLevel;
  label: string;
  explanation: string;
}

export interface PhysicalFormOption {
  physicalForm: string;
  /** The specific food_matrix value this physical form maps to -- lives here,
   * not on the entry, since a base cheese can have different food_matrix
   * values per form within the same category (e.g. cheddar: "cheddar" for
   * block, "shredded cheddar" for shredded). This is what /api/v6/predict
   * actually needs as the food_matrix feature. */
  foodMatrix: string;
  source: string;
  confidence: number;
  support: ResolvedSupport;
}

export interface CheeseCatalogEntry {
  cheeseCategory: CheeseCategory;
  physicalForms: PhysicalFormOption[];
}

/** base_cheese_name -> entries (a list, not a scalar: a handful of names
 * like "kalari cheese" genuinely span two cheese categories in the V6 data). */
export type CheeseCatalog = Record<string, CheeseCatalogEntry[]>;

export type RoutingLevel = "ok" | "thin_sample" | "unavailable";

export interface RoutingMeta {
  level: RoutingLevel;
  reduced_support: boolean;
  reason: string | null;
}

export interface SchemaV6Data extends SchemaData {
  cheese_category: CheeseCategory;
  model_task: ModelTask;
  routing: RoutingMeta;
  best_model: string;
  model_label: string;
}

/** The headline level a prediction's overall support resolves to -- always
 * present on a successful /api/v6/predict response, never silently omitted.
 * "supported" is the only level a result should be shown with normal
 * (non-flagged) styling; every other level must be visually differentiated. */
export type PredictionSupportLevel =
  | "supported"
  | "weak_physical_form"
  | "extrapolation"
  | "unsupported_categorical"
  | "thin_sample";

export interface UnseenCategorical {
  feature: string;
  value: string;
}

export interface NumericExtrapolation {
  feature: string;
  value: number;
  range: { min: number; max: number };
  conditioned_on: Record<string, string> | null;
  detail: string;
}

export interface ModelSupportAssessment {
  level: "supported" | "extrapolation" | "unsupported_categorical";
  unseen_categoricals: UnseenCategorical[];
  extrapolations: NumericExtrapolation[];
  warnings: string[];
}

/** The single combined support object returned by /api/v6/predict --
 * mirrors SpecialistRegistry.assess_prediction_support() exactly, the one
 * place this assessment is computed (never re-derived in the frontend). */
export interface PredictionSupportAssessment {
  level: PredictionSupportLevel;
  can_predict: boolean;
  reason: string | null;
  routing: RoutingMeta;
  physical_form: ResolvedSupport | null;
  model: ModelSupportAssessment | null;
}

export interface CandidateV6Input {
  name: string;
  treatment_type: string;
  application_method: string;
  primary_ingredient_name: string;
  primary_concentration: number;
  primary_concentration_unit: string;
  primary_ingredient_family?: string | null;
}

export interface CandidateV6Result {
  candidate_name: string;
  model: string;
  model_label: string;
  predicted_candidate_shelf_life: number;
  predicted_control_shelf_life: number;
  absolute_improvement_days: number;
  relative_improvement_pct: number | null;
  shelf_life_ratio: number | null;
  lower_bound: number;
  upper_bound: number;
  warnings: string[];
  support: ModelSupportAssessment;
  row: Record<string, unknown>;
  rank: number;
}

export interface PredictV6Result {
  control: {
    model: string;
    model_label: string;
    prediction_days: number;
    lower_bound: number;
    upper_bound: number;
    warnings: string[];
    support: ModelSupportAssessment;
  };
  candidates: CandidateV6Result[];
  routing: RoutingMeta;
  /** The headline combined assessment (physical form + categorical/numeric)
   * for this request -- always present, always the same object
   * backend/main.py computed before predicting. */
  support: PredictionSupportAssessment;
  model_label: string;
}

export interface RoutingV6Response {
  category: CheeseCategory;
  indicator_task_map: Record<string, ModelTask>;
}

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  institution: string | null;
  role: string | null;
  avatar_url: string | null;
  created_at: string;
}

/** Avatar URLs come back as backend-relative paths; resolve against API_BASE. */
export function resolveAvatarUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return url.startsWith("http") ? url : `${API_BASE}${url}`;
}

export const api = {
  health: () => request<{ status: string; best_model: string; models: string[] }>("/api/health"),
  manifest: () => request<ManifestData>("/api/manifest"),
  schema: () => request<SchemaData>("/api/schema"),
  matrixLookup: () => request<Record<string, Record<string, unknown>>>("/api/lookups/matrix"),
  ingredientLookup: () => request<Record<string, Record<string, unknown>>>("/api/lookups/ingredient"),
  datasetSynthetic: () => request<SyntheticDataset>("/api/dataset/synthetic"),
  datasetReal: () => request<RealDataset>("/api/dataset/real"),
  models: () => request<ModelsResponse>("/api/models"),
  modelDetails: (model: string) => request<ModelDetails>(`/api/models/${model}/details`),
  ebmShapes: () => request<{ shapes: { term: string; type: string; names: string[]; scores: number[] }[] }>("/api/models/ebm/shapes"),
  references: () => request<ReferencesData>("/api/references"),
  predict: (body: { model: string; shared: Record<string, unknown>; candidates: CandidateInput[] }) =>
    request<PredictResult>("/api/predict", { method: "POST", body: JSON.stringify(body) }),
  explainLocal: (body: { model: string; row: Record<string, unknown>; top_k?: number }) =>
    request<{ factors: { feature: string; contribution: number; is_interaction: boolean }[] }>(
      "/api/explain/local",
      { method: "POST", body: JSON.stringify(body) },
    ),
  assistantChat: (body: { messages: AssistantChatMessage[]; page_context?: Record<string, unknown> }) =>
    request<AssistantChatResponse>("/api/assistant/chat", { method: "POST", body: JSON.stringify(body) }),

  // ── V6 specialist architecture ─────────────────────────────────────────
  v6Health: () => request<{ available: boolean; specialists?: Record<string, boolean> }>("/api/v6/health"),
  cheeseCatalog: () => request<{ catalog: CheeseCatalog }>("/api/v6/cheese-catalog"),
  routingV6: (category: CheeseCategory) => request<RoutingV6Response>(`/api/v6/routing?category=${category}`),
  schemaV6: (category: CheeseCategory, task: ModelTask) =>
    request<SchemaV6Data>(`/api/v6/schema?category=${category}&task=${task}`),
  predictV6: (body: {
    cheese_category: CheeseCategory;
    model_task: ModelTask;
    shared: Record<string, unknown>;
    candidates: CandidateV6Input[];
  }) => request<PredictV6Result>("/api/v6/predict", { method: "POST", body: JSON.stringify(body) }),
  explainLocalV6: (body: { cheese_category: CheeseCategory; model_task: ModelTask; row: Record<string, unknown>; top_k?: number }) =>
    request<{ factors: { feature: string; contribution: number; is_interaction: boolean }[]; routing: RoutingMeta }>(
      "/api/v6/explain/local",
      { method: "POST", body: JSON.stringify(body) },
    ),

  // ── classification ─────────────────────────────────────────────────────
  classificationHealth: () => request<{ available: boolean; best_model?: string; models?: string[] }>("/api/classification/health"),
  classificationManifest: () => request<ClassificationManifest>("/api/classification/manifest"),
  classificationSchema: () => request<SchemaData>("/api/classification/schema"),
  classificationDistribution: () => request<ClassificationDistribution>("/api/classification/distribution"),
  classificationModels: () => request<ClassificationModelsResponse>("/api/classification/models"),
  classificationModelDetails: (model: string) => request<ClassificationModelDetails>(`/api/classification/models/${model}/details`),
  classificationPredict: (body: { model: string; shared: Record<string, unknown>; candidates: ClassificationCandidateInput[] }) =>
    request<ClassificationPredictResult>("/api/classification/predict", { method: "POST", body: JSON.stringify(body) }),

  // ── ingredient efficacy ranking ────────────────────────────────────────
  ingredientRankingHealth: () => request<{ available: boolean }>("/api/ingredients/health"),
  ingredientRankingManifest: () => request<IngredientRankingManifest>("/api/ingredients/manifest"),
  ingredientRankings: () => request<IngredientRankingsResponse>("/api/ingredients/rankings"),
  ingredientRankingDetail: (name: string) => request<IngredientRanking>(`/api/ingredients/rankings/${encodeURIComponent(name)}`),

  // ── auth ────────────────────────────────────────────────────────────────
  signup: (body: { name: string; email: string; password: string }) =>
    request<AuthUser>("/api/auth/signup", { method: "POST", body: JSON.stringify(body) }),
  login: (body: { email: string; password: string }) =>
    request<AuthUser>("/api/auth/login", { method: "POST", body: JSON.stringify(body) }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  me: () => request<AuthUser | null>("/api/auth/me"),
  updateProfile: (body: { name?: string; institution?: string; role?: string }) =>
    request<AuthUser>("/api/auth/me", { method: "PATCH", body: JSON.stringify(body) }),
  changePassword: (body: { current_password: string; new_password: string }) =>
    request<void>("/api/auth/me/password", { method: "POST", body: JSON.stringify(body) }),
  uploadAvatar: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<AuthUser>("/api/auth/me/avatar", { method: "POST", body: form });
  },
  removeAvatar: () => request<AuthUser>("/api/auth/me/avatar", { method: "DELETE" }),
};

export const BEST_MODEL_KEY = "best_validation_model";

export const MODEL_LABELS: Record<string, string> = {
  random_forest: "Random Forest",
  lightgbm: "LightGBM",
  xgboost: "XGBoost",
  ebm: "Explainable Boosting Machine",
  lstm: "LSTM (experimental)",
};
