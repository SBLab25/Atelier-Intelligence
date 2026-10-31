import Link from "next/link";

import type { EventPage } from "@/lib/api/loaders";

import { EmptyState, Timestamp } from "./States";

/** Events of one step, newest first (Spec 14, OD-150). User and session ids are shown as the API returns them. */
export function EventsTable({ page, caption }: { readonly page: EventPage; readonly caption: string }) {
  if (page.data.length === 0) {
    return <EmptyState>No events for this step and filter.</EmptyState>;
  }
  return (
    <div className="table-wrap">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col">Event type</th>
            <th scope="col">User</th>
            <th scope="col">Session</th>
            <th scope="col">Duration</th>
            <th scope="col">URL</th>
          </tr>
        </thead>
        <tbody>
          {page.data.map((event) => (
            <tr key={event.event_id}>
              <th scope="row">
                <Timestamp value={event.timestamp} />
              </th>
              <td>{event.event_type ?? "—"}</td>
              <td>{event.user_id ?? "—"}</td>
              <td>{event.session_id ?? "—"}</td>
              <td>{event.duration_ms === null ? "—" : `${event.duration_ms} ms`}</td>
              <td>{event.url ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** "Next page" link for cursor paging; the cursor is opaque and only passed back to the API. */
export function Pager({ nextHref, label }: { readonly nextHref: string | null; readonly label: string }) {
  if (!nextHref) {
    return <p className="hint">End of the list.</p>;
  }
  return (
    <p>
      <Link href={nextHref} className="button">
        {label}
      </Link>
    </p>
  );
}
