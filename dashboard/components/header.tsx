import { Button } from "@/components/ui/button";
import Link from "next/link";

export function Header() {
  return (
    <header className="border-b bg-background/80 px-6 py-3 flex items-center gap-3">
      <div className="flex items-center justify-center rounded-lg bg-white p-1.5 shadow-xs ring-1 ring-border">
        <img src="/nfc-logo.svg" alt="NFC" className="h-7 w-auto" />
      </div>
      <h1 className="text-xl font-semibold">Webex Reports</h1>
      <nav className="ml-auto flex items-center gap-4 text-sm">
        <Link href="/" className="text-primary hover:underline font-medium">
          Dashboard
        </Link>
        <Link href="/reports" className="text-primary hover:underline font-medium">
          Reports
        </Link>
        <Button variant="outline" size="sm" render={<a href="/api/logout" />}>
          Sign out
        </Button>
      </nav>
    </header>
  );
}
