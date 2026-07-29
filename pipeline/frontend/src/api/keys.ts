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

  // The scientific schema. Addressed by project, then by paper filter, so switching the
  // paper dropdown reads its own cache entry.
  science: {
    all: (projectId: number) => ['science', projectId] as const,
    experiments: (projectId: number, paperId?: number) =>
      ['science', projectId, 'experiments', paperId ?? 'all'] as const,
    experiment: (projectId: number, experimentId: number) =>
      ['science', projectId, 'experiment', experimentId] as const,
    ingredients: (projectId: number) => ['science', projectId, 'ingredients'] as const,
    indicators: (projectId: number) => ['science', projectId, 'indicators'] as const,
  },

  members: {
    all: (projectId: number) => ['members', projectId] as const,
  },

  audit: {
    list: (projectId: number, filters?: object) =>
      ['audit', projectId, filters ?? {}] as const,
  },

  // The processed dataset the processing service builds from the scientific schema, and
  // the prediction surface on top of it.
  dataset: {
    all: (projectId: number) => ['dataset', projectId] as const,
    preview: (projectId: number) => ['dataset', projectId, 'preview'] as const,
  },

  prediction: {
    all: (projectId: number) => ['prediction', projectId] as const,
    status: (projectId: number) => ['prediction', projectId, 'status'] as const,
  },
} as const
