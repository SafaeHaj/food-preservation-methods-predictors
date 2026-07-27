/**
 * Find the most recent job of a given type for a paper.
 *
 * This is how a page reconnects to work already in flight. Opening the extraction
 * workspace on a paper whose parse is half-finished must attach to that job, not start a
 * second one — the previous page had a bespoke `/workspace/status` endpoint for exactly
 * this, which the generic job list now covers for every workflow.
 */

import { useJobs } from '../api/jobs'

export function useLatestJob(projectId: number, paperId: number, jobType: string) {
  const { data: jobs, isLoading } = useJobs({
    project_id: projectId,
    paper_id: paperId,
    job_type: jobType,
    limit: 1,
  })

  // The list is ordered newest-first by the server.
  const latest = jobs?.[0]
  return { job: latest, jobId: latest?.id ?? null, isLoading }
}
