// Tiny module-level pub/sub for log entries.
//
// Why a module singleton + not React context: the API client in lib/api.ts
// is a plain TypeScript module and shouldn't depend on React. It emits log
// entries through this bus; the LogsContext provider subscribes and pushes
// them into React state.

export type LogSource = "frontend" | "backend" | "api" | "system";
export type LogLevel = "info" | "success" | "warning" | "error";

export interface LogEntry {
  readonly id: string;
  readonly timestamp: string;
  readonly source: LogSource;
  readonly level: LogLevel;
  readonly message: string;
  readonly meta?: Readonly<Record<string, unknown>>;
}

export type LogListener = (entry: LogEntry) => void;

const listeners = new Set<LogListener>();
let counter = 0;

function nextId(): string {
  counter += 1;
  return `${Date.now().toString(36)}-${counter.toString(36)}`;
}

export function emit(input: Omit<LogEntry, "id" | "timestamp">): void {
  const entry: LogEntry = {
    ...input,
    id: nextId(),
    timestamp: new Date().toISOString(),
  };
  for (const l of Array.from(listeners)) {
    try {
      l(entry);
    } catch {
      // A misbehaving listener must not break the producer.
    }
  }
}

export function subscribe(listener: LogListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
