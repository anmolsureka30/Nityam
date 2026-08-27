import type { FieldChange } from "../lib/types";
import styles from "./DiffView.module.css";

export function DiffView({ changes }: { changes: FieldChange[] }) {
  if (changes.length === 0) {
    return <p className={styles.empty}>No changes yet.</p>;
  }
  return (
    <ul className={styles.list} data-testid="diff-view">
      {changes.map((change, i) => (
        <li key={i} className={styles[change.kind]} data-testid="diff-row">
          {change.label}
        </li>
      ))}
    </ul>
  );
}
