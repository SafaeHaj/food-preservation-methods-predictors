import { api } from "@/lib/api";
import { PageBody, PageHeader } from "@/components/page-shell";
import { ExplainabilityView } from "@/components/explainability-view";

export default async function ExplainabilityPage() {
  const { models } = await api.models();
  return (
    <PageBody>
      <PageHeader
        title="Explainability"
        description="Understand how each model makes its predictions, globally and for your most recent query."
      />
      <ExplainabilityView models={models} />
    </PageBody>
  );
}
