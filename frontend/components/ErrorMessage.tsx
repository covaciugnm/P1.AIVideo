import styles from "./ErrorMessage.module.css";

interface ErrorMessageProps {
  readonly message: string;
  readonly title?: string;
}

export function ErrorMessage({ message, title }: ErrorMessageProps) {
  return (
    <div className={styles.box} role="alert">
      <strong className={styles.title}>{title ?? "Error"}</strong>
      <span className={styles.body}>{message}</span>
    </div>
  );
}
