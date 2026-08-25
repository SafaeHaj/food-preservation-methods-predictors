import { api } from "@/lib/api";
import { PageBody, PageHeader, Reveal, SectionLabel } from "@/components/page-shell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default async function ReferencesPage() {
  const data = await api.references();
  const ruleRows = Object.entries(data.generation_rules).sort((a, b) => b[1] - a[1]);

  return (
    <PageBody>
      <PageHeader
        title="References"
        description="How this dataset version was generated. This version is entirely synthetic — there is no literature-derived real subset to cite."
      />

      <Card className="surface mb-6">
        <CardHeader>
          <CardTitle className="text-sm">Synthetic data methodology</CardTitle>
          <CardDescription>{data.n_synthetic_rows.toLocaleString()} rows, {data.n_real_rows} real.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm leading-relaxed text-muted-foreground">
          <p>
            Every row uses <strong className="text-foreground">{data.synthetic_method.replace(/_/g, " ")}</strong> —
            points generated within scientifically plausible bounds informed by the food-science literature, not
            measured directly. Each row is tagged with a generation-rule id (below) rather than a specific citation.
            Every row&apos;s <code className="rounded bg-secondary px-1 py-0.5 font-mono text-xs">data_origin</code>,{" "}
            <code className="rounded bg-secondary px-1 py-0.5 font-mono text-xs">quality_flag</code>, and{" "}
            <code className="rounded bg-secondary px-1 py-0.5 font-mono text-xs">source_rule_id</code> are excluded
            from the model&apos;s own features.
          </p>
        </CardContent>
      </Card>

      <Reveal>
        <SectionLabel>Provenance</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader>
            <CardTitle className="text-sm">Generation-rule breakdown</CardTitle>
            <CardDescription>Rows per synthetic-generation rule.</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow><TableHead>Rule</TableHead><TableHead className="text-right">Rows</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                {ruleRows.map(([rule, n]) => (
                  <TableRow key={rule} className="row-interactive">
                    <TableCell className="font-mono text-xs">{rule}</TableCell>
                    <TableCell className="text-right tabular-nums">{n.toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Credits</SectionLabel>
        <Card className="surface">
          <CardHeader>
            <CardTitle className="text-sm">Background imagery credits</CardTitle>
            <CardDescription>Required/appreciated attribution for the decorative background layer used throughout this app.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2.5 text-xs leading-relaxed text-muted-foreground">
              <li>
                <strong className="text-foreground">Macdonald Campus</strong> — &ldquo;Campus Macdonald 01.jpg&rdquo; by
                Jeangagnon,{" "}
                <a href="https://commons.wikimedia.org/wiki/File:Campus_Macdonald_01.jpg" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                  Wikimedia Commons
                </a>
                , licensed CC BY-SA 3.0.
              </li>
              <li>
                <strong className="text-foreground">Petri dish</strong> — photo by Araf Ibne Alam on{" "}
                <a href="https://unsplash.com/photos/a-petri-dish-with-bacteria-cultures-M9wnk86lcdg" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                  Unsplash
                </a>
                , Unsplash License.
              </li>
              <li>
                <strong className="text-foreground">Laboratory glassware</strong> — photo by Madeline Liu on{" "}
                <a href="https://unsplash.com/photos/JT3wYV0LHYI" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                  Unsplash
                </a>
                , Unsplash License.
              </li>
              <li>
                <strong className="text-foreground">Cheese aging cellar</strong> — photo by Katrin Leinfellner on{" "}
                <a href="https://unsplash.com/photos/v9deD75EaRw" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                  Unsplash
                </a>
                , Unsplash License.
              </li>
              <li>
                <strong className="text-foreground">Microscope</strong> — photo by Ousa Chea on{" "}
                <a href="https://unsplash.com/photos/gKUC4TMhOiY" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                  Unsplash
                </a>
                , Unsplash License.
              </li>
              <li>
                <strong className="text-foreground">Molecular lattice &amp; growth-curve motifs</strong> — hand-drawn SVG, original to this project.
              </li>
            </ul>
          </CardContent>
        </Card>
      </Reveal>
    </PageBody>
  );
}
