export type ModelFamily = 'kinetic' | 'survival'

export interface ModelParam {
  symbol: string
  name: string
  unit: string
  description: string
}

export interface ModelDoc {
  id: string
  name: string
  shortName: string
  family: ModelFamily
  tagline: string
  color: string
  what: string
  bestFor: string[]
  dataRequirements: string[]
  outputs: string[]
  equation: string         // legacy Unicode fallback
  equationNote: string
  latex: string[]          // KaTeX display-mode equations
  latexNote?: string       // inline KaTeX annotation
  params: ModelParam[]
  assumptions: string[]
  limitations: string[]
  references?: { authors: string; year: number; title: string; journal: string }[]
}

export const MODEL_DOCS: ModelDoc[] = [
  // ──────────────────────────────── KINETIC ─────────────────────────────────
  {
    id: 'baranyi',
    name: 'Baranyi-Roberts',
    shortName: 'Baranyi',
    family: 'kinetic',
    color: 'teal',
    tagline: 'Gold-standard growth model with physiological lag phase',
    what:
      'The Baranyi-Roberts model describes sigmoidal microbial growth with a mechanistic ' +
      'lag phase. It explicitly models the physiological state of the cells (their readiness ' +
      'to grow), making it the most biologically meaningful of the primary growth models. ' +
      'Cells start with an internal "adjustment variable" h₀ = μ_max × λ that decreases as they ' +
      'adapt to the new environment. Once fully adapted, cells enter exponential growth until ' +
      'limited by nutrient depletion near N_max.',
    bestFor: [
      'Predicting growth of pathogens (L. monocytogenes, Salmonella) under refrigeration',
      'Estimating lag times after temperature shifts or hurdle stress',
      'Fitting challenge study data from meat, dairy, RTE foods',
      'Comparing growth potential across treatment conditions',
    ],
    dataRequirements: [
      'Time-series counts: log₁₀(N) vs time (minimum 8–12 data points)',
      'Initial inoculation level N₀ (log CFU/g or log CFU/mL)',
      'Steady-state maximum population N_max (often fixed at literature value)',
      'Even time-step measurements improve parameter identifiability',
    ],
    outputs: [
      'N(t) — microbial count at any time t (log CFU/g)',
      'μ_max — maximum specific growth rate (h⁻¹)',
      'λ — lag phase duration (h)',
      'N_max — maximum population density (ln CFU/g)',
      'Doubling time t_d = ln(2)/μ_max',
    ],
    equation: 'N(t) = N_max - ln{1 + [exp(N_max - N₀) - 1] × exp[-μ_max × A(t)]}',
    equationNote:
      'Variables are in natural-log scale. N₀, N(t), and N_max are ln(CFU/g). ' +
      'A(t) is the adjustment function — approaches t as t → ∞.',
    latex: [
      String.raw`\ln N(t) = N_{\max} - \ln\!\Bigl\{1 + \bigl[\mathrm{e}^{N_{\max}-N_0}-1\bigr]\,\mathrm{e}^{-\mu_{\max}A(t)}\Bigr\}`,
      String.raw`A(t) = t + \frac{1}{\mu_{\max}}\ln\!\bigl[\mathrm{e}^{-\mu_{\max}t} + \mathrm{e}^{-h_0} - \mathrm{e}^{-\mu_{\max}t-h_0}\bigr]`,
      String.raw`h_0 = \mu_{\max}\,\lambda \qquad \text{(initial physiological state)}`,
    ],
    latexNote:
      'All concentrations in natural-log scale (\\(\\ln\\,\\text{CFU/g}\\)). ' +
      'The adjustment function satisfies \\(A(t)\\to t\\) as \\(t\\to\\infty\\), ' +
      'recovering pure exponential growth once cells are fully adapted.',
    references: [
      {
        authors: 'Baranyi, J. & Roberts, T. A.',
        year: 1994,
        title: 'A dynamic approach to predicting bacterial growth in food',
        journal: 'International Journal of Food Microbiology 23, 277–294',
      },
    ],
    params: [
      { symbol: 'N₀',    name: 'Initial count',   unit: 'ln CFU/g',      description: 'Microbial population at t = 0' },
      { symbol: 'N_max', name: 'Maximum count',    unit: 'ln CFU/g',      description: 'Carrying capacity (nutrient limit)' },
      { symbol: 'μ_max', name: 'Max growth rate',  unit: 'h⁻¹',  description: 'Slope during exponential phase' },
      { symbol: 'λ',     name: 'Lag time',         unit: 'h',             description: 'Time before detectable growth starts' },
      { symbol: 'h₀',    name: 'Physiol. state',   unit: 'dimensionless', description: 'Derived: h₀ = μ_max × λ' },
    ],
    assumptions: [
      'Cells are in a homogeneous well-mixed environment',
      'Temperature, pH, a_W remain constant during the experiment',
      'All cells share the same physiological state at t = 0',
      'Growth is limited only by a single nutrient (implicit carrying capacity)',
    ],
    limitations: [
      'Requires time-series data — cannot be applied to single-point measurements',
      'Assumes isothermal conditions; does not handle temperature shifts without a secondary model',
      'Four parameters can be poorly identifiable with sparse data (< 8 points)',
      'Does not account for sub-population variability or stochastic effects',
    ],
  },

  {
    id: 'gompertz',
    name: 'Modified Gompertz',
    shortName: 'Gompertz',
    family: 'kinetic',
    color: 'teal',
    tagline: 'Empirical sigmoidal growth — simple, widely cited',
    what:
      'The Modified Gompertz equation (Zwietering et al. 1990) fits the characteristic ' +
      'S-curve of microbial growth using three interpretable parameters: the total ' +
      'growth range A, the maximum growth rate μ_max, and the lag phase λ. ' +
      'It is purely empirical — it does not model cell physiology — but is extremely ' +
      'widely used in food microbiology for its simplicity and good fit across a broad ' +
      'range of growth conditions.',
    bestFor: [
      'Rapid comparative studies across many conditions/treatments',
      'Published literature meta-analysis (most papers report Gompertz parameters)',
      'When Baranyi fails to converge due to sparse data',
      'Secondary modelling (fitting μ_max vs temperature, pH, a_W)',
    ],
    dataRequirements: [
      'Time-series counts: log₁₀(N) vs time (minimum 6 points)',
      'Growth must show clear lag, exponential, and stationary phases',
      'Data in log₁₀ scale (model operates in log₁₀)',
    ],
    outputs: [
      'N(t) — log₁₀(CFU/g) at any time t',
      'μ_max — max specific growth rate (log CFU/h)',
      'λ — lag phase (h)',
      'A — growth range: log(N_max/N₀) (log CFU/g)',
    ],
    equation: 'log(N(t)) = N₀ + A × exp{ -exp[ (μ_max × e / A) × (λ - t) + 1 ] }',
    equationNote:
      'The exponential-of-exponential is large and positive during lag, crosses zero at t = λ, ' +
      'and becomes large and negative in stationary phase, producing the characteristic S-curve.',
    latex: [
      String.raw`\log_{10}N(t) = N_0 + A\exp\!\Biggl\{-\exp\!\biggl[\frac{\mu_{\max}\,e}{A}(\lambda - t)+1\biggr]\Biggr\}`,
      String.raw`A = \log_{10}N_{\max} - \log_{10}N_0 \quad\text{(total growth range, log\,CFU/g)}`,
    ],
    latexNote:
      'Here \\(e \\approx 2.718\\) is Euler\'s number; \\(\\mu_{\\max}\\) is the tangent slope at the inflection point. ' +
      'The model operates in \\(\\log_{10}\\) scale.',
    references: [
      {
        authors: 'Zwietering, M. H., Jongenburger, I., Rombouts, F. M. & van\'t Riet, K.',
        year: 1990,
        title: 'Modeling of the bacterial growth curve',
        journal: 'Applied and Environmental Microbiology 56, 1875–1881',
      },
    ],
    params: [
      { symbol: 'N₀',    name: 'Initial count',  unit: 'log CFU/g',      description: 'Population at t = 0, typically measured' },
      { symbol: 'A',     name: 'Growth range',   unit: 'log CFU/g',      description: 'log(N_max) – log(N₀), total increase' },
      { symbol: 'μ_max', name: 'Max growth rate', unit: 'log CFU/(g·h)', description: 'Tangent slope at inflection point' },
      { symbol: 'λ',     name: 'Lag time',       unit: 'h',              description: 'x-intercept of tangent at inflection' },
    ],
    assumptions: [
      'Symmetric growth curve around the inflection point (often not true)',
      'Homogeneous environment throughout the experiment',
      'Purely empirical — no mechanistic basis for parameter interpretation',
    ],
    limitations: [
      'Tends to overestimate lag phase when data is sparse in early phase',
      'Asymmetric growth curves (common in real foods) fit poorly',
      'Baranyi is generally preferred when mechanistic interpretation is needed',
      'Parameters lack direct biological meaning (μ_max is not the instantaneous rate)',
    ],
  },

  {
    id: 'weibull_inact',
    name: 'Weibull Inactivation',
    shortName: 'Weibull',
    family: 'kinetic',
    color: 'teal',
    tagline: 'Flexible non-linear inactivation — captures shoulder & tail',
    what:
      'The Weibull model for microbial inactivation treats survival curves as cumulative ' +
      'distributions of individual cell resistances. The shape parameter p determines whether ' +
      'the curve is concave-up (shoulder, p < 1), linear (classical first-order, p = 1), or ' +
      'concave-down (tailing, p > 1). It is the most widely used non-linear inactivation model ' +
      'because it can fit virtually any monotonically decreasing survival curve, unlike the ' +
      'log-linear (D-value) model which forces a straight line on semi-log paper.',
    bestFor: [
      'Thermal inactivation where shoulder or tailing is evident',
      'High-pressure processing (HPP) inactivation curves',
      'UV, pulsed electric field, and other non-thermal treatments',
      'Comparing efficacy of multiple hurdle treatments',
    ],
    dataRequirements: [
      'Survival counts: log₁₀(N/N₀) vs treatment time or dose',
      'Minimum 5–8 data points covering at least 2–3 log reductions',
      'Data must be monotonically decreasing (no regrowth)',
      'If tailing, counts near detection limit must be carefully handled',
    ],
    outputs: [
      'N(t)/N₀ — fractional survival at time t',
      'δ — time for first decimal reduction [min or h]',
      'p — shape parameter (curvature of survival curve)',
      'Equivalent D-value at any reduction level',
    ],
    equation: 'log₁₀(N(t)/N₀) = -(t/δ)^p',
    equationNote:
      'When p = 1, δ = D (classical D-value). The n-log reduction time is t_n = δ × n^(1/p).',
    latex: [
      String.raw`\log_{10}\!\left(\frac{N(t)}{N_0}\right) = -\left(\frac{t}{\delta}\right)^{\!p}`,
      String.raw`\begin{cases} p < 1 & \text{concave-up (shoulder / initial resistance)} \\ p = 1 & \text{linear (classical log-linear, } D = \delta\text{)} \\ p > 1 & \text{concave-down (tailing / resistant sub-population)} \end{cases}`,
    ],
    latexNote:
      'When \\(p=1\\), \\(\\delta = D\\) (classical D-value). ' +
      'The \\(n\\)-log reduction time generalises to \\(t_n = \\delta\\,n^{1/p}\\).',
    references: [
      {
        authors: 'Mafart, P., Couvert, O., Gaillard, S. & Leguerinel, I.',
        year: 2002,
        title: 'On calculating sterility in thermal preservation methods: application of the Weibull frequency distribution model',
        journal: 'International Journal of Food Microbiology 72, 107–113',
      },
    ],
    params: [
      { symbol: 'δ',  name: 'Scale (1-log time)', unit: 'min or h',      description: 'Time to achieve 1-log reduction' },
      { symbol: 'p',  name: 'Shape parameter',     unit: 'dimensionless', description: 'Curvature; p = 1 → linear first-order' },
      { symbol: 'N₀', name: 'Initial count',       unit: 'log CFU/g',    description: 'Population at start of treatment' },
    ],
    assumptions: [
      'Inactivation is monotonically decreasing (no growth phase)',
      'All cells within the inoculum have resistance drawn from a Weibull distribution',
      'Isothermal / constant treatment intensity (temperature, pressure, dose)',
      'No viable-but-non-culturable (VBNC) state confounds counts',
    ],
    limitations: [
      'Cannot model biphasic curves (two distinct resistant sub-populations)',
      'Does not mechanistically explain why the shoulder or tail occurs',
      'Parameter correlation: δ and p can be co-linear with sparse data',
      'Requires isothermal data; for dynamic conditions use rate models',
    ],
  },

  {
    id: 'geeraerd',
    name: 'Geeraerd',
    shortName: 'Geeraerd',
    family: 'kinetic',
    color: 'teal',
    tagline: 'Mechanistic inactivation with explicit shoulder and tail terms',
    what:
      'The Geeraerd model (2000) explicitly separates three biologically distinct phases of ' +
      'an inactivation curve: a protective shoulder (cells protected by a “critical component” ' +
      'C_c), a log-linear inactivation phase (at rate k_max), and a tail of resistant survivors ' +
      'N_res. Unlike the Weibull model which treats the whole curve empirically, Geeraerd ' +
      'provides mechanistic parameters that can be related to actual cell biology (heat-shock ' +
      'proteins, membrane integrity, clumping, or physiological heterogeneity).',
    bestFor: [
      'Thermal inactivation with clearly visible shoulder phase (heat-shock protection)',
      'Inactivation curves with a pronounced resistant tail (VBNC or clumped cells)',
      'Comparing treatments that modify shoulder length (e.g., stress pre-adaptation)',
      'Regulatory submissions where mechanistic model justification is required',
    ],
    dataRequirements: [
      'Time-series survival counts with both lag and tail regions visible',
      'Minimum 8–12 data points with good coverage of all three phases',
      'Counts below detection limit must be reported as censored values',
      'Replicate measurements strongly recommended to identify N_res reliably',
    ],
    outputs: [
      'k_max — maximum inactivation rate constant (h⁻¹ or min⁻¹)',
      'S_l — shoulder length (h or min)',
      'N_res — resistant tail population (log CFU/g)',
      'N(t) — microbial count at time t',
    ],
    equation: 'N(t) = [N₀ - N_res] × exp(-k_max × t) × exp(k_max × S_l) / [1 + (exp(k_max × S_l) - 1) × exp(-k_max × t)] + N_res',
    equationNote:
      'The protective term 1/(1+C_c) → 1 as C_c → 0 (shoulder depletes), enabling full ' +
      'log-linear inactivation. The (1 - N_res/N) term prevents N from falling below N_res.',
    latex: [
      String.raw`\frac{dN}{dt} = -k_{\max}\,\frac{1}{1+C_c}\!\left(1-\frac{N_{\rm res}}{N}\right)N, \qquad \frac{dC_c}{dt} = -k_{\max}\,C_c`,
      String.raw`N(t) = \bigl(N_0 - N_{\rm res}\bigr)\,\mathrm{e}^{-k_{\max}t}\,\frac{\mathrm{e}^{k_{\max}S_l}}{1+\bigl(\mathrm{e}^{k_{\max}S_l}-1\bigr)\mathrm{e}^{-k_{\max}t}} + N_{\rm res}`,
      String.raw`S_l = \frac{\ln(1+C_{c,0})}{k_{\max}} \qquad \text{(shoulder length from initial } C_{c,0}\text{)}`,
    ],
    latexNote:
      'The protective component \\(C_c\\) decays at the same rate \\(k_{\\max}\\) as inactivation. ' +
      'When \\(C_{c,0}=0\\) (no shoulder) and \\(N_{\\rm res}=0\\) (no tail), the model collapses to first-order kinetics: \\(N(t)=N_0\\,\\mathrm{e}^{-k_{\\max}t}\\).',
    references: [
      {
        authors: 'Geeraerd, A. H., Herremans, C. H. & Van Impe, J. F.',
        year: 2000,
        title: 'Structural model requirements to describe microbial inactivation during a mild heat treatment',
        journal: 'International Journal of Food Microbiology 59, 185–209',
      },
    ],
    params: [
      { symbol: 'k_max',  name: 'Inactivation rate', unit: 'min⁻¹',    description: 'Max 1st-order inactivation rate constant' },
      { symbol: 'S_l',    name: 'Shoulder length',   unit: 'min',           description: 'Duration before log-linear phase begins' },
      { symbol: 'N_res',  name: 'Tail population',   unit: 'log CFU/g',     description: 'Resistant survivors (lower asymptote)' },
      { symbol: 'N₀', name: 'Initial count',     unit: 'log CFU/g',     description: 'Population at start of treatment (t = 0)' },
    ],
    assumptions: [
      'A single “critical component” C_c protects cells during the shoulder phase',
      'The resistant sub-population N_res is constant (does not grow or decay)',
      'Inactivation of sensitive cells follows first-order kinetics after the shoulder',
      'C_c degrades at the same rate as cell inactivation (k_max)',
    ],
    limitations: [
      'Four parameters increase overfitting risk with fewer than 10 data points',
      'N_res estimation is unreliable when tail is below detection limit',
      'Numerically stiff ODE system can cause convergence issues',
      'Not suitable when inactivation curves show multiple phases or oscillation',
    ],
  },

  // ──────────────────────────────── SURVIVAL ────────────────────────────────
  {
    id: 'weibull_aft',
    name: 'Weibull AFT',
    shortName: 'Weibull AFT',
    family: 'survival',
    color: 'violet',
    tagline: 'Parametric survival model — shelf life from treatment covariates',
    what:
      'The Weibull Accelerated Failure Time (AFT) model treats shelf-life failure (exceeding ' +
      'a microbial threshold or sensory rejection) as a time-to-event outcome. Covariates ' +
      '(temperature, pH, a_W, preservative type/dose, packaging atmosphere) are linked to ' +
      'the scale of the Weibull distribution via a log-linear regression: log(T) = Xβ + σε. ' +
      'Each coefficient βᵢ represents how much covariate xᵢ accelerates or decelerates ' +
      'time to failure — exp(βᵢ) is the Acceleration Factor (AF).',
    bestFor: [
      'Predicting shelf life as a function of formulation/storage conditions',
      'Handling right-censored data (products removed before failure)',
      'Comparing shelf life across packaging types, preservative doses, temperatures',
      'Regulatory submissions requiring interpretable survival analysis',
    ],
    dataRequirements: [
      'Observation records: failure_time (h or days), event indicator (1=failed, 0=censored)',
      'Covariate columns: temperature (°C), pH, a_W, preservative type, packaging',
      'Minimum ~30–50 observations per covariate for stable estimates',
      'Balance between failed and censored observations (> 20% events)',
    ],
    outputs: [
      'β coefficients — log-scale effect of each covariate on survival time',
      'Acceleration Factor AF = exp(β) — relative shelf life multiplier',
      'S(t|x) — predicted survival function for any covariate profile',
      'Median shelf life (t at S = 0.5) and percentile confidence intervals',
      'P(shelf life > target) for any specified target time',
    ],
    equation: 'S(t|x) = exp[-(t/λ)^p]   where  log(λ) = Xβ',
    equationNote:
      'When p > 1, the hazard is increasing (aging products). p = 1 gives the exponential model.',
    latex: [
      String.raw`S(t\mid\mathbf{x}) = \exp\!\left[-\left(\frac{t}{\lambda(\mathbf{x})}\right)^{\!p}\right], \qquad \ln\lambda(\mathbf{x}) = \mathbf{x}^{\!\top}\!\boldsymbol{\beta}`,
      String.raw`\ln T = \mathbf{x}^{\!\top}\!\boldsymbol{\beta} + \sigma\,\varepsilon, \qquad \varepsilon \sim \mathrm{Gumbel}(0,1)`,
      String.raw`h(t\mid\mathbf{x}) = \frac{p}{\lambda}\!\left(\frac{t}{\lambda}\right)^{\!p-1}, \qquad \mathrm{AF}_i = \exp(\beta_i)`,
    ],
    latexNote:
      'The Acceleration Factor \\(\\mathrm{AF}_i = \\exp(\\beta_i)\\) gives the multiplicative change in ' +
      'expected survival time per unit increase in \\(x_i\\). ' +
      'When \\(p>1\\) the hazard is monotone increasing (wear-out); \\(p<1\\) gives decreasing hazard (burn-in).',
    references: [
      {
        authors: 'Meeker, W. Q., Escobar, L. A. & Pascual, F. G.',
        year: 2022,
        title: 'Statistical Methods for Reliability Data (2nd ed.)',
        journal: 'Wiley, Hoboken, NJ',
      },
    ],
    params: [
      { symbol: 'β₀',  name: 'Intercept',      unit: 'log days',          description: 'Baseline log shelf life at reference conditions' },
      { symbol: 'βᵢ',  name: 'Coefficients',    unit: 'log days per unit', description: 'Log-scale effect of covariate i on survival' },
      { symbol: 'p',    name: 'Shape parameter', unit: 'dimensionless',    description: 'Controls hazard shape; p = 1 → exponential' },
      { symbol: 'σ',    name: 'Scale of ε',     unit: 'dimensionless',    description: 'σ = 1/p; spread of failure time distribution' },
    ],
    assumptions: [
      'Failure times follow a Weibull distribution conditional on covariates',
      'Log-linear relationship between covariates and log(scale)',
      'Censoring is non-informative (reason for censoring unrelated to failure risk)',
      'Proportional effect of covariates across the full survival curve',
    ],
    limitations: [
      'Weibull shape p is constant across covariate levels (no interaction with hazard shape)',
      'Cannot capture non-monotone hazard functions',
      'Extrapolation outside the observed covariate range is unreliable',
      'Large sample needed when failure times are heavily censored (< 20% events)',
    ],
  },

  {
    id: 'rsf',
    name: 'Random Survival Forest',
    shortName: 'RSF',
    family: 'survival',
    color: 'violet',
    tagline: 'Non-parametric ensemble — handles complex interactions automatically',
    what:
      'Random Survival Forest (RSF, Ishwaran et al. 2008) extends the random forest ' +
      'algorithm to censored time-to-event data. Each tree is built by splitting nodes ' +
      'to maximize the log-rank test statistic (separation of survival curves). Each ' +
      'terminal node contains a Nelson-Aalen survival estimator. The final survival ' +
      'function for a new observation is obtained by averaging across all trees. RSF ' +
      'requires no distributional assumption and automatically captures non-linear effects.',
    bestFor: [
      'Complex datasets with many covariates and unknown interaction structures',
      'When the parametric AFT assumption is questionable',
      'Variable importance ranking to identify key shelf-life drivers',
      'Large datasets (n > 200) where ensemble approaches excel',
    ],
    dataRequirements: [
      'Same structure as AFT: failure_time + event indicator + covariate columns',
      'At minimum 100 observations (RSF is data-hungry; > 200 preferred)',
      'Can handle missing covariate values via imputation or splitting rules',
      'Categorical variables should be encoded (one-hot or ordinal)',
    ],
    outputs: [
      'S(t|x) — predicted survival function (averaged across trees)',
      'C-index (concordance) — discrimination performance metric',
      'Variable importance (VIMP) — each covariate’s contribution to prediction accuracy',
      'Partial effects plots for individual covariates',
    ],
    equation: 'Ś(t|x) = (1/B) × Σ_b Ś_b(t|x)',
    equationNote:
      'Unlike parametric models, RSF has no closed-form equation — it is estimated from data at each terminal node.',
    latex: [
      String.raw`\hat{S}(t\mid\mathbf{x}) = \frac{1}{B}\sum_{b=1}^{B}\hat{S}_b(t\mid\mathbf{x})`,
      String.raw`\hat{S}_b(t\mid\mathbf{x}) = \prod_{t_j\le t}\!\left(1 - \frac{d_j}{n_j}\right) \quad\text{(Nelson-Aalen at terminal node)}`,
      String.raw`L_{\rm split} = \frac{\bigl[\sum_j(d_{j,L}-e_{j,L})\bigr]^2}{\operatorname{Var}\bigl[\sum_j(d_{j,L}-e_{j,L})\bigr]} \quad\text{(log-rank split criterion)}`,
    ],
    latexNote:
      '\\(B\\) is the number of trees, \\(d_j\\) the number of failures at time \\(t_j\\), ' +
      '\\(n_j\\) the number at risk. Out-of-bag (OOB) C-index is used for evaluation without a separate test set.',
    references: [
      {
        authors: 'Ishwaran, H., Kogalur, U. B., Blackstone, E. H. & Lauer, M. S.',
        year: 2008,
        title: 'Random survival forests',
        journal: 'Annals of Applied Statistics 2, 841–860',
      },
    ],
    params: [
      { symbol: 'B',      name: 'n_estimators',     unit: 'integer',  description: 'Number of trees (typically 500–2000)' },
      { symbol: 'd_max',  name: 'max_depth',         unit: 'integer',  description: 'Maximum tree depth (None = fully grown)' },
      { symbol: 'n_leaf', name: 'min_samples_leaf',  unit: 'integer',  description: 'Minimum events per terminal node (≥ 3)' },
      { symbol: 'm_try',  name: 'max_features',      unit: 'fraction', description: 'Features sampled per split (default √p)' },
    ],
    assumptions: [
      'Independence between observations (each product is an independent unit)',
      'Non-informative censoring (reason for censoring unrelated to failure)',
      'No strong temporal ordering within the dataset (IID observations)',
    ],
    limitations: [
      'Computationally expensive for very large datasets (> 50K rows)',
      'Predictions are not easily interpretable as explicit survival equations',
      'Extrapolation to new covariate combinations outside training data is unreliable',
      'Feature importance (VIMP) can be misleading with highly correlated covariates',
    ],
  },

  {
    id: 'xgboost_aft',
    name: 'XGBoost AFT',
    shortName: 'XGBoost AFT',
    family: 'survival',
    color: 'violet',
    tagline: 'Gradient-boosted survival — best predictive accuracy on tabular data',
    what:
      'XGBoost AFT combines gradient boosting with the Accelerated Failure Time likelihood ' +
      'for censored outcomes. Instead of a single linear predictor Xβ, it learns f(X) ' +
      'through an ensemble of regression trees, each correcting the residual errors of the ' +
      'previous. This allows it to capture non-linear effects and interactions without ' +
      'manual feature engineering. XGBoost AFT typically achieves the best predictive ' +
      'accuracy on tabular survival data among all models listed here.',
    bestFor: [
      'Maximum predictive accuracy is the primary goal (e.g., production system)',
      'Large datasets with many interacting covariates (temperature × pH × a_W interactions)',
      'When covariate effects are clearly non-linear',
      'Benchmarking against simpler models to assess non-linearity benefit',
    ],
    dataRequirements: [
      'Same structure: failure_time + event indicator + covariate columns',
      'Minimum ~100–200 observations; performance scales well with more data',
      'Features can be numeric or categorical (XGBoost handles both natively)',
      'Separate validation set needed for early stopping and hyperparameter tuning',
    ],
    outputs: [
      'Predicted log failure time f(x) for each observation',
      'Survival function S(t|x) under assumed AFT distribution',
      'C-index and time-dependent AUC metrics',
      'SHAP values for feature importance and individual prediction explanations',
    ],
    equation: 'log(T) = f(X) + σ·ε    ε ~ D(0,1)   f(X) = Σ_k f_k(X)',
    equationNote:
      'XGBoost minimizes the negative AFT log-likelihood using second-order gradient information (Newton steps) at each tree split.',
    latex: [
      String.raw`\ln T = f(\mathbf{x}) + \sigma\,\varepsilon, \qquad f(\mathbf{x}) = \sum_{k=1}^{K}f_k(\mathbf{x}), \quad \varepsilon \sim \mathcal{D}(0,1)`,
      String.raw`f_k = f_{k-1} + \eta\operatorname*{arg\,min}_{f}\sum_i\mathcal{L}\!\left(y_i,\,f_{k-1}(\mathbf{x}_i)+f(\mathbf{x}_i)\right)`,
      String.raw`\ell_{\rm AFT} = \sum_i\!\Bigl[\delta_i\ln h(t_i\mid\mathbf{x}_i) + \ln S(t_i\mid\mathbf{x}_i)\Bigr]`,
    ],
    latexNote:
      'The distribution \\(\\mathcal{D}\\) is Extreme Value (Gumbel) for Weibull AFT, Normal for log-normal AFT, ' +
      'or Logistic. XGBoost uses Newton boosting with \\(\\eta\\) as the learning rate.',
    references: [
      {
        authors: 'Chen, T. & Guestrin, C.',
        year: 2016,
        title: 'XGBoost: a scalable tree boosting system',
        journal: 'Proceedings of KDD 2016, 785–794',
      },
    ],
    params: [
      { symbol: 'K',     name: 'n_estimators',            unit: 'integer', description: 'Number of boosting rounds (trees)' },
      { symbol: 'η',     name: 'learning_rate',           unit: '(0, 1]',  description: 'Step size shrinkage (default 0.1)' },
      { symbol: 'd_max', name: 'max_depth',                unit: 'integer', description: 'Maximum tree depth (default 6)' },
      { symbol: 'σ',     name: 'aft_loss_distribution_scale', unit: '>0', description: 'Scale of the AFT error distribution' },
    ],
    assumptions: [
      'Residuals follow the chosen AFT distribution (Extreme Value / Normal / Logistic)',
      'Non-informative censoring',
      'Enough data for boosting to generalize (regularization via λ, α hyperparams)',
    ],
    limitations: [
      'Black-box: individual predictions are hard to explain without SHAP tools',
      'Hyperparameter tuning (learning_rate, max_depth, subsample) requires validation data',
      'Can overfit severely on small datasets without careful regularization',
      'Does not produce calibrated survival probabilities without post-hoc calibration',
    ],
  },

  {
    id: 'bayesian_aft',
    name: 'Bayesian Hierarchical AFT',
    shortName: 'Bayesian AFT',
    family: 'survival',
    color: 'violet',
    tagline: 'Full uncertainty quantification with study-level random effects',
    what:
      'The Bayesian Hierarchical AFT model extends the Weibull AFT by placing prior ' +
      'distributions on all parameters and estimating the full posterior using MCMC ' +
      '(NUTS/HMC sampler). The hierarchical structure allows study-level random effects: ' +
      'each paper/study in the database gets its own intercept α_j, which is itself drawn ' +
      'from a population distribution. This pools information across studies while ' +
      'accounting for between-study variability — particularly valuable when some studies ' +
      'have very few observations.',
    bestFor: [
      'Meta-analysis: pooling data from multiple studies with different protocols',
      'Small sample sizes where frequentist models give wide or unreliable CIs',
      'When full predictive uncertainty is needed (not just a point estimate)',
      'Incorporating expert knowledge via informative priors on treatment effects',
    ],
    dataRequirements: [
      'Observation records with study_id column for hierarchical grouping',
      'Minimum 3+ studies with at least 5 observations each for meaningful pooling',
      'Works well with small N per study if many studies available (partial pooling)',
      'Same covariate structure as Weibull AFT',
    ],
    outputs: [
      'Posterior distribution of each β coefficient (mean + 94% HDI)',
      'Study-level random effects α_j for each paper/study',
      'Posterior predictive survival curve with uncertainty band',
      'P(shelf life > target) with full credible interval',
      'MCMC diagnostics: R̂ (convergence), effective sample size (ESS)',
    ],
    equation: 'log(T_ij) = α_j + X_ijβ + σε_ij   α_j ~ N(μ_α, τ_α)',
    equationNote:
      'Study intercepts α_j are pulled toward the global mean μ_α proportionally to τ_α (partial pooling).',
    latex: [
      String.raw`\ln T_{ij} = \alpha_j + \mathbf{x}_{ij}^{\!\top}\!\boldsymbol{\beta} + \sigma\,\varepsilon_{ij}, \qquad \varepsilon_{ij}\sim\mathrm{Gumbel}(0,1)`,
      String.raw`\alpha_j \sim \mathcal{N}(\mu_\alpha,\,\tau_\alpha^2) \quad j = 1,\ldots,J`,
      String.raw`\mu_\alpha \sim \mathcal{N}(0,4),\quad \tau_\alpha \sim \mathrm{HalfNormal}(0,1),\quad \boldsymbol{\beta} \sim \mathcal{N}(\mathbf{0},\mathbf{I}),\quad \sigma \sim \mathrm{HalfNormal}(0,1)`,
      String.raw`p(\boldsymbol{\theta}\mid\mathbf{T},\mathbf{X}) \;\propto\; \mathcal{L}(\mathbf{T},\mathbf{X}\mid\boldsymbol{\theta})\times p(\boldsymbol{\theta})`,
    ],
    latexNote:
      'When \\(\\tau_\\alpha \\approx 0\\) all studies share one intercept (complete pooling). ' +
      'When \\(\\tau_\\alpha\\) is large, each study is estimated independently (no pooling). ' +
      'Partial pooling is achieved automatically. NUTS sampler: 4 chains × 2000 draws, \\(\\delta = 0.9\\).',
    references: [
      {
        authors: 'Gelman, A., Carlin, J. B., Stern, H. S. & Rubin, D. B.',
        year: 2013,
        title: 'Bayesian Data Analysis (3rd ed.)',
        journal: 'Chapman & Hall/CRC, Boca Raton, FL',
      },
    ],
    params: [
      { symbol: 'μ_α',  name: 'Global intercept',  unit: 'log days',      description: 'Average log shelf life across all studies' },
      { symbol: 'τ_α',  name: 'Between-study SD',   unit: 'log days',      description: 'Study-to-study variability in intercept' },
      { symbol: 'α_j',  name: 'Study intercepts',  unit: 'log days',      description: 'Study j’s deviation from global mean' },
      { symbol: 'β',    name: 'Covariate effects',  unit: 'log days/unit', description: 'Fixed-effect regression coefficients' },
      { symbol: 'σ',    name: 'Residual scale',     unit: 'log days',      description: 'Within-study observation variability' },
    ],
    assumptions: [
      'Study-level effects are exchangeable (drawn from a common population distribution)',
      'Chosen priors are weakly informative and do not dominate the posterior',
      'MCMC chains converge (R̂ < 1.01 and ESS > 400)',
      'Non-informative censoring within each study',
    ],
    limitations: [
      'Computationally expensive: MCMC with 4 chains × 2000 draws can take minutes to hours',
      'Requires careful prior specification; uninformative priors can cause pathological posteriors',
      'Model diagnostics (R̂, ESS, trace plots) must be checked before using predictions',
      'Posterior predictive checks needed to validate model adequacy',
    ],
  },
]

export const getModelDoc = (id: string): ModelDoc | undefined =>
  MODEL_DOCS.find((m) => m.id === id)
