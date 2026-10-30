import Link from "next/link";
import { cookies } from "next/headers";
import { Logo } from "@/components/logo";

const FEATURES = [
  ["Acts, not just chats", "Looks up orders and tickets, cancels, refunds and updates tickets through the desk's own API."],
  ["Your permissions, never more", "The assistant acts as the signed-in user. Tools a role can't use are never shown to the model."],
  ["Asks before it changes money", "Cancellations and refunds pause for an explicit \"Are you sure?\" and every step lands in an audit log."],
  ["Answers you can check", "Policy answers come from the help center with citations. Unsupported numbers are replaced, not shown."],
  ["Multi-agent", "A router hands each request to an orders, tickets or knowledge agent (LangGraph)."],
  ["Runs on a laptop", "Local Qwen model via llama.cpp, local embeddings and Qdrant, optional local speech in and out."],
];

export default async function Home() {
  const signedIn = (await cookies()).has("deskpilot_session");
  return (
    <>
      <header className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
        <Logo href="/" />
        {signedIn ? (
          <Link href="/app" className="btn btn-primary">
            Go to dashboard
          </Link>
        ) : (
          <Link href="/login" className="btn btn-primary">
            Sign in
          </Link>
        )}
      </header>
      <main className="mx-auto max-w-5xl px-4 pb-16">
        <section className="py-12">
          <h1 className="max-w-3xl text-4xl font-bold leading-tight">An AI assistant that works inside your support desk, safely.</h1>
          <p className="mt-4 max-w-2xl text-lg muted">
            Ask in plain language: &ldquo;Refund $20 on ORD-1002, the seam is torn.&rdquo; Deskpilot finds the order, checks your role
            and the refund rules, asks you to confirm, does it, and logs it.
          </p>
          <div className="mt-6 flex gap-3">
            <Link href={signedIn ? "/app" : "/login"} className="btn btn-primary">
              {signedIn ? "Go to dashboard" : "Try the demo"}
            </Link>
          </div>
        </section>
        <section aria-labelledby="features" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <h2 id="features" className="sr-only">
            Features
          </h2>
          {FEATURES.map(([title, text]) => (
            <article key={title} className="panel p-4">
              <h3 className="font-semibold">{title}</h3>
              <p className="mt-1 text-sm muted">{text}</p>
            </article>
          ))}
        </section>
      </main>
    </>
  );
}
