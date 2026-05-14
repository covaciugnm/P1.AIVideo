import { formatDate, humanize } from "@/lib/format";
import type { ComplianceEventResponse } from "@/lib/types";

import { StatusBadge } from "./StatusBadge";
import styles from "./ComplianceEvents.module.css";

interface ComplianceEventsProps {
  readonly events: readonly ComplianceEventResponse[];
}

export function ComplianceEvents({ events }: ComplianceEventsProps) {
  if (events.length === 0) {
    return <p className={styles.empty}>No compliance events recorded yet.</p>;
  }
  return (
    <ul className={styles.list}>
      {events.map((event, idx) => (
        <li key={`${event.created_at}-${idx}`} className={styles.item}>
          <div className={styles.row}>
            <span className={styles.gate}>{humanize(event.event_type)}</span>
            <StatusBadge status={event.decision} />
            <span className={styles.time}>{formatDate(event.created_at)}</span>
          </div>
          {event.reasons.length > 0 && (
            <ul className={styles.reasons}>
              {event.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}
