import styles from "./LoadingState.module.css";

interface LoadingStateProps {
  readonly label?: string;
}

export function LoadingState({ label }: LoadingStateProps) {
  return (
    <div className={styles.wrapper} aria-busy="true">
      <span className={styles.spinner} aria-hidden="true" />
      <span className={styles.label}>{label ?? "Loading…"}</span>
    </div>
  );
}
