import { api } from "@/lib/api";
import { PageBody } from "@/components/page-shell";
import { PredictionV6StoreProvider } from "@/components/prediction-v6-store";
import { PredictionV6Flow } from "@/components/prediction-v6-flow";

export default async function PredictionPage() {
  const { catalog } = await api.cheeseCatalog();

  return (
    <PageBody>
      <PredictionV6StoreProvider>
        <PredictionV6Flow catalog={catalog} />
      </PredictionV6StoreProvider>
    </PageBody>
  );
}
