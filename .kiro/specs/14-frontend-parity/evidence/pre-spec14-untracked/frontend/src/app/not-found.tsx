import Link from "next/link";

export default function NotFound() {
  return (
    <main id="main" tabIndex={-1} className="content">
      <h1>Page not found</h1>
      <p>There is no page at this address.</p>
      <p>
        <Link href="/">Go to the status page</Link>
      </p>
    </main>
  );
}
