"use client";

import { Header } from "@/components/header";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { useCallback, useEffect, useState } from "react";

type Row = {
  name: string;
  email: string;
  inbound: number;
  outbound: number;
  total: number;
  talk_min: number;
};

type Stats = { months: string[]; month: string; rows: Row[] };

const chartConfig: ChartConfig = {
  inbound: { label: "Inbound", color: "var(--chart-2)" },
  outbound: { label: "Outbound", color: "var(--chart-1)" },
};

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (month?: string) => {
    setStats(await api<Stats>(`/api/stats${month ? `?month=${month}` : ""}`));
  }, []);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  async function collect() {
    setBusy(true);
    await api("/api/run/collect", { method: "POST" });
    setBusy(false);
    await load();
  }

  if (!stats) {
    return (
      <div className="flex min-h-svh items-center justify-center text-muted-foreground">
        Loading…
      </div>
    );
  }

  const sums = {
    inbound: stats.rows.reduce((a, r) => a + r.inbound, 0),
    outbound: stats.rows.reduce((a, r) => a + r.outbound, 0),
    total: stats.rows.reduce((a, r) => a + r.total, 0),
  };
  const top = [...stats.rows]
    .sort((a, b) => b.total - a.total)
    .slice(0, 15)
    .map((r) => ({ user: r.name || r.email, inbound: r.inbound, outbound: r.outbound }));

  return (
    <div className="min-h-svh bg-muted/40">
      <Header />
      <main className="mx-auto max-w-6xl space-y-6 p-6">
        <div className="flex flex-wrap items-center gap-3">
          <Select value={stats.month} onValueChange={(m) => load(m ?? undefined)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {stats.months.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={collect} disabled={busy}>
            {busy ? "Collecting…" : "Collect now"}
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Inbound" value={sums.inbound} />
          <StatCard label="Outbound" value={sums.outbound} />
          <StatCard label="Total calls" value={sums.total} />
          <StatCard label="Users" value={stats.rows.length} />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Inbound vs Outbound (top users)</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={chartConfig} className="h-[340px] w-full">
              <BarChart data={top}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="user" tickLine={false} axisLine={false} interval={0} angle={-30} height={60} textAnchor="end" />
                <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Bar dataKey="inbound" fill="var(--color-inbound)" radius={4} />
                <Bar dataKey="outbound" fill="var(--color-outbound)" radius={4} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead className="text-right">Inbound</TableHead>
                  <TableHead className="text-right">Outbound</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead className="text-right">Talk (min)</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {stats.rows.map((r, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-medium">{r.name}</TableCell>
                    <TableCell>{r.email}</TableCell>
                    <TableCell className="text-right">{r.inbound}</TableCell>
                    <TableCell className="text-right">{r.outbound}</TableCell>
                    <TableCell className="text-right">{r.total}</TableCell>
                    <TableCell className="text-right">{r.talk_min}</TableCell>
                  </TableRow>
                ))}
                {stats.rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-muted-foreground">
                      No data for {stats.month} — click “Collect now” or wait for the nightly run.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
              {stats.rows.length > 0 && (
                <TableFooter>
                  <TableRow>
                    <TableCell colSpan={2} className="font-bold">TOTAL</TableCell>
                    <TableCell className="text-right font-bold">{sums.inbound}</TableCell>
                    <TableCell className="text-right font-bold">{sums.outbound}</TableCell>
                    <TableCell className="text-right font-bold">{sums.total}</TableCell>
                    <TableCell />
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        render={<a href={`/download/${stats.month}`} />}
                      >
                        Download CSV
                      </Button>
                    </TableCell>
                  </TableRow>
                </TableFooter>
              )}
            </Table>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="pt-6 text-center">
        <div className="text-4xl font-bold tracking-tight tabular-nums">{value}</div>
        <div className="mt-1 text-sm text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  );
}
