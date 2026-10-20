"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState } from "react";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(false);
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (res.ok) window.location.href = "/";
    else setError(true);
  }

  return (
    <main className="grid min-h-svh lg:grid-cols-2">
      {/* Brand panel */}
      <div className="relative hidden flex-col justify-between overflow-hidden bg-slate-950 p-10 text-white lg:flex">
        <div className="pointer-events-none absolute -top-40 -left-40 h-96 w-96 rounded-full bg-sky-500/20 blur-3xl" />
        <div className="pointer-events-none absolute right-0 bottom-0 h-109 w-109 translate-x-1/3 translate-y-1/3 rounded-full bg-blue-600/25 blur-3xl" />

        <div className="relative flex w-fit items-center rounded-2xl bg-white p-3 pr-6 shadow-lg">
          <img src="/nfc-logo.svg" alt="NFC" className="h-11 w-auto" />
        </div>

        <div className="relative max-w-md space-y-4">
          <h2 className="text-4xl font-bold tracking-tight">
            Monthly call reports,
            <br />
            on autopilot.
          </h2>
          <p className="text-lg text-slate-300">
            Inbound and outbound call statistics for your teams — collected
            nightly from Webex and emailed on the 2nd of every month.
          </p>
          <ul className="space-y-2 text-sm text-slate-400">
            <li className="flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-sky-400" />
              Scope defined by your Control Hub groups
            </li>
            <li className="flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-sky-400" />
              Dashboard history with CSV download and re-send
            </li>
          </ul>
        </div>

        <div className="relative flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-xl bg-white/95 py-2 pr-5 pl-3 shadow-lg">
            <span className="text-xs font-medium tracking-wide text-slate-600 uppercase">
              Presented by
            </span>
            <img src="/tct-logo.png" alt="TCT" className="h-9 w-auto" />
          </div>
        </div>
      </div>

      {/* Form */}
      <div className="flex flex-col items-center justify-center bg-muted/40 p-6">
        <form
          onSubmit={submit}
          className="w-full max-w-sm rounded-2xl border bg-background p-8 shadow-xs space-y-5"
        >
          <div className="space-y-2 text-center">
            <img
              src="/nfc-logo.svg"
              alt="NFC"
              className="mx-auto h-8 w-auto lg:hidden"
            />
            <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
            <p className="text-sm text-muted-foreground">
              Webex Reports admin dashboard
            </p>
          </div>
          <Input
            type="password"
            name="password"
            placeholder="Admin password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-10"
          />
          {error && (
            <p className="text-center text-sm text-destructive">
              Wrong password — try again
            </p>
          )}
          <Button type="submit" className="h-10 w-full text-base">
            Sign in
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Reports run automatically on the 2nd of each month, 06:00 (Oman time)
          </p>
        </form>

        {/* presented-by on small screens */}
        <div className="mt-6 flex items-center gap-2 rounded-xl bg-white py-1.5 pr-4 pl-3 shadow-xs lg:hidden">
          <span className="text-[10px] font-medium tracking-wide text-slate-500 uppercase">
            Presented by
          </span>
          <img src="/tct-logo.png" alt="TCT" className="h-7 w-auto" />
        </div>
      </div>
    </main>
  );
}
