"use client";

import * as React from "react";
import { Search, TrendingUp, Minus, TrendingDown, ArrowUpDown } from "lucide-react";

import type { IngredientRanking } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const CLASS_BADGE_VARIANT: Record<string, "destructive" | "warning" | "success"> = {
  Low: "destructive",
  Medium: "warning",
  High: "success",
};
const CLASS_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  Low: TrendingDown,
  Medium: Minus,
  High: TrendingUp,
};

type SortKey = "rank" | "adjusted_effect_pct" | "descriptive_mean_pct" | "n_train";

export function IngredientTable({ rankings, families }: { rankings: IngredientRanking[]; families: string[] }) {
  const [query, setQuery] = React.useState("");
  const [family, setFamily] = React.useState<string>("all");
  const [sortKey, setSortKey] = React.useState<SortKey>("rank");
  const [sortAsc, setSortAsc] = React.useState(true);

  const filtered = React.useMemo(() => {
    let rows = rankings;
    if (family !== "all") rows = rows.filter((r) => r.ingredient_family === family);
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      rows = rows.filter((r) => r.ingredient_name.toLowerCase().includes(q) || r.ingredient_family.toLowerCase().includes(q));
    }
    const sorted = [...rows].sort((a, b) => (a[sortKey] as number) - (b[sortKey] as number));
    return sortAsc ? sorted : sorted.reverse();
  }, [rankings, family, query, sortKey, sortAsc]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc((v) => !v);
    } else {
      setSortKey(key);
      setSortAsc(key === "rank");
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-subtle-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search ingredient or family…"
            className="pl-8"
          />
        </div>
        <Select value={family} onValueChange={(v) => v && setFamily(v)}>
          <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All families</SelectItem>
            {families.map((f) => <SelectItem key={f} value={f}>{f.replace(/_/g, " ")}</SelectItem>)}
          </SelectContent>
        </Select>
        <span className="type-caption ml-auto text-muted-foreground">{filtered.length} of {rankings.length} ingredients</span>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <SortableHead label="Rank" active={sortKey === "rank"} asc={sortAsc} onClick={() => toggleSort("rank")} className="w-14" />
              <TableHead>Ingredient</TableHead>
              <TableHead>Family</TableHead>
              <TableHead className="text-center">Class</TableHead>
              <SortableHead label="Adjusted effect" active={sortKey === "adjusted_effect_pct"} asc={sortAsc} onClick={() => toggleSort("adjusted_effect_pct")} className="text-right" />
              <SortableHead label="Raw mean" active={sortKey === "descriptive_mean_pct"} asc={sortAsc} onClick={() => toggleSort("descriptive_mean_pct")} className="text-right" />
              <SortableHead label="Train n" active={sortKey === "n_train"} asc={sortAsc} onClick={() => toggleSort("n_train")} className="text-right" />
              <TableHead className="text-right">Val / test mean</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((r) => {
              const Icon = CLASS_ICON[r.efficacy_class] ?? Minus;
              return (
                <TableRow key={r.ingredient_name} className="row-interactive">
                  <TableCell className="numeral text-muted-foreground">{r.rank}</TableCell>
                  <TableCell className="font-medium text-foreground">
                    {r.ingredient_name}
                    {r.low_confidence && <Badge variant="outline" className="ml-1.5 h-4 px-1 text-[9px] text-warning">low n</Badge>}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{r.ingredient_family.replace(/_/g, " ")}</TableCell>
                  <TableCell className="text-center">
                    <Badge variant={CLASS_BADGE_VARIANT[r.efficacy_class] ?? "secondary"} className="h-5 gap-1 px-1.5 text-[10px]">
                      <Icon className="size-2.5" />
                      {r.efficacy_class}
                    </Badge>
                  </TableCell>
                  <TableCell className="numeral text-right font-medium text-foreground">
                    {r.adjusted_effect_pct >= 0 ? "+" : ""}{r.adjusted_effect_pct.toFixed(1)}%
                  </TableCell>
                  <TableCell className="numeral text-right text-muted-foreground">
                    {r.descriptive_mean_pct >= 0 ? "+" : ""}{r.descriptive_mean_pct.toFixed(1)}%
                  </TableCell>
                  <TableCell className="numeral text-right text-muted-foreground">{r.n_train}</TableCell>
                  <TableCell className="numeral text-right text-muted-foreground">
                    {r.validation_mean_pct !== null ? `${r.validation_mean_pct >= 0 ? "+" : ""}${r.validation_mean_pct.toFixed(0)}%` : "—"}
                    {" / "}
                    {r.test_mean_pct !== null ? `${r.test_mean_pct >= 0 ? "+" : ""}${r.test_mean_pct.toFixed(0)}%` : "—"}
                  </TableCell>
                </TableRow>
              );
            })}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">No ingredients match.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function SortableHead({
  label, active, asc, onClick, className,
}: { label: string; active: boolean; asc: boolean; onClick: () => void; className?: string }) {
  return (
    <TableHead className={className}>
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-1 transition-colors hover:text-foreground ${active ? "text-foreground" : ""}`}
      >
        {label}
        <ArrowUpDown className={`size-3 ${active ? "opacity-100" : "opacity-40"}`} style={active ? { transform: asc ? "scaleY(1)" : "scaleY(-1)" } : undefined} />
      </button>
    </TableHead>
  );
}
