"use client";

import { Header } from "@/components/header";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

type Report = {
  id: number;
  month: string;
  sent_at: string;
  recipients: string;
  status: string;
  detail: string;
};

type Data = { history: Report[]; recipients: string };

export default function ReportsPage() {
  const [data, setData] = useState<Data | null>(null);
  const [emails, setEmails] = useState("");
  const [note, setNote] = useState("");

  async function load() {
    const d = await api<Data>("/api/reports");
    setData(d);
    setEmails(d.recipients.split("; ").join("\n"));
    if (!d.recipients) setEmails("");
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  async function save() {
    await api("/api/recipients", {
      method: "POST",
      body: JSON.stringify({ emails }),
    });
    setNote("Recipients saved");
    await load();
  }

  async function action(url: string, body?: object) {
    setNote("Queued — the run happens in the background, refresh to see results.");
    await api(url, { method: "POST", body: body ? JSON.stringify(body) : "{}" });
    await load();
  }

  if (!data) {
    return (
      <div className="flex min-h-svh items-center justify-center text-muted-foreground">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-svh bg-muted/40">
      <Header />
      <main className="mx-auto max-w-5xl space-y-6 p-6">
        {note && <p className="text-sm text-emerald-600">{note}</p>}

        <Card>
          <CardHeader>
            <CardTitle>Monthly email recipients</CardTitle>
            <CardDescription>
              Runs automatically on the 2nd of each month at 06:00 (Oman time)
              for the previous calendar month.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={emails}
              onChange={(e) => setEmails(e.target.value)}
              placeholder="one email per line"
              rows={4}
            />
            <div className="flex flex-wrap gap-3">
              <Button onClick={save}>Save recipients</Button>
              <Button
                variant="secondary"
                onClick={() => action("/api/run/report")}
              >
                Generate &amp; send report now
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Sent at</TableHead>
                  <TableHead>Month</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Recipients</TableHead>
                  <TableHead>Detail</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.history.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{r.sent_at}</TableCell>
                    <TableCell className="font-medium">{r.month}</TableCell>
                    <TableCell>{r.status}</TableCell>
                    <TableCell className="max-w-56 truncate">{r.recipients}</TableCell>
                    <TableCell className="max-w-40 truncate">{r.detail}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => action(`/api/report/${r.id}/resend`)}
                      >
                        Resend
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {data.history.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground">
                      No reports sent yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
