import { AppHeader } from "@/components/app-header";
import { AuthProvider } from "@/components/auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AppHeader />
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </AuthProvider>
  );
}
