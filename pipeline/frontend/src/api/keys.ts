/**
 * Query keys — the cache's addressing scheme, and therefore the invalidation contract.
 *
 * Keys are hierarchical, so a broad invalidation reaches everything beneath it:
 * `invalidateQueries({ queryKey: keys.papers.all(7) })` clears every paper list and detail
 * for project 7 in one call, without any component needing to know who else is caching
 * that data. Keeping every key in one file is what makes that safe — an ad-hoc key spelled
 * slightly differently at the call site is a cache entry nothing can ever invalidate.
 */

export const keys = {
  projects: {
    all: () => ['projects'] as const,
    list: () => ['projects', 'list'] as const,
    detail: (projectId: number) => ['projects', 'detail', projectId] as const,
    stats: (projectId: number) => ['projects', 'stats', projectId] as const,
  },

  papers: {
    all: (projectId: number) => ['papers', projectId] as const,
    list: (projectId: number) => ['papers', projectId, 'list'] as const,
    detail: (projectId: number, paperId: number) =>
      ['papers', projectId, 'detail', paperId] as const,
  },

  workspace: {
    all: (projectId: number, paperId: number) => ['workspace', projectId, paperId] as const,
    assets: (projectId: number, paperId: number, filters?: object) =>
      ['workspace', projectId, paperId, 'assets', filters ?? {}] as const,
    asset: (projectId: number, paperId: number, assetId: number) =>
      ['workspace', projectId, paperId, 'asset', assetId] as const,
    evidence: (projectId: number, paperId: number) =>
      ['workspace', projectId, paperId, 'evidence'] as const,
    projectAssets: (projectId: number, filters?: object) =>
      ['workspace', projectId, 'project-assets', filters ?? {}] as const,
  },

  jobs: {
    all: () => ['jobs'] as const,
    list: (filters?: object) => ['jobs', 'list', filters ?? {}] as const,
    detail: (jobId: number) => ['jobs', 'detail', jobId] as const,
  },

  // The structured five-table extraction output (`ext_*`). Addressed by project, then by
  // paper filter, so switching the paper dropdown reads its own cache entry.
  extracted: {
    all: (projectId: number) => ['extracted', projectId] as const,
    experiments: (projectId: number, paperId?: number) =>
      ['extracted', projectId, 'experiments', paperId ?? 'all'] as const,
    experiment: (projectId: number, experimentId: number) =>
      ['extracted', projectId, 'experiment', experimentId] as const,
    ingredients: (projectId: number) => ['extracted', projectId, 'ingredients'] as const,
    indicators: (projectId: number) => ['extracted', projectId, 'indicators'] as const,
  },

  studies: {
    all: (projectId: number) => ['studies', projectId] as const,
    list: (projectId: number, filters?: object) =>
      ['studies', projectId, 'list', filters ?? {}] as const,
    detail: (studyId: number) => ['studies', 'detail', studyId] as const,
  },

  experiments: {
    all: (projectId: number) => ['experiments', projectId] as const,
    list: (projectId: number, filters?: object) =>
      ['experiments', projectId, 'list', filters ?? {}] as const,
  },

  arms: {
    all: (projectId: number) => ['arms', projectId] as const,
    list: (projectId: number, filters?: object) =>
      ['arms', projectId, 'list', filters ?? {}] as const,
  },

  observations: {
    all: (projectId: number) => ['observations', projectId] as const,
    list: (projectId: number, filters?: object) =>
      ['observations', projectId, 'list', filters ?? {}] as const,
  },

  trajectories: {
    all: (projectId: number) => ['trajectories', projectId] as const,
    list: (projectId: number, filters?: object) =>
      ['trajectories', projectId, 'list', filters ?? {}] as const,
    runs: (trajectoryId: number) => ['trajectories', 'runs', trajectoryId] as const,
  },

  thresholds: {
    all: (projectId: number) => ['thresholds', projectId] as const,
    list: (projectId: number) => ['thresholds', projectId, 'list'] as const,
    crossings: (thresholdId: number, projectId: number) =>
      ['thresholds', projectId, 'crossings', thresholdId] as const,
  },

  imputations: {
    all: (projectId: number) => ['imputations', projectId] as const,
    list: (projectId: number, filters?: object) =>
      ['imputations', projectId, 'list', filters ?? {}] as const,
  },

  normalization: {
    all: (projectId: number) => ['normalization', projectId] as const,
    mappings: (projectId: number) => ['normalization', projectId, 'mappings'] as const,
  },

  microorganisms: {
    list: (projectId: number) => ['microorganisms', projectId] as const,
  },

  members: {
    all: (projectId: number) => ['members', projectId] as const,
  },

  audit: {
    list: (projectId: number, filters?: object) =>
      ['audit', projectId, filters ?? {}] as const,
  },

  snapshots: {
    all: (projectId: number) => ['snapshots', projectId] as const,
    exportRun: (runId: number) => ['snapshots', 'export-run', runId] as const,
  },

  modelLab: {
    all: (projectId: number) => ['model-lab', projectId] as const,
    datasets: (projectId: number) => ['model-lab', projectId, 'datasets'] as const,
    runs: (projectId: number) => ['model-lab', projectId, 'runs'] as const,
    run: (projectId: number, runId: number) => ['model-lab', projectId, 'run', runId] as const,
    models: (projectId: number) => ['model-lab', projectId, 'models'] as const,
    model: (projectId: number, modelId: number) =>
      ['model-lab', projectId, 'model', modelId] as const,
  },
} as const
