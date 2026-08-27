import type { Turn } from "../../lib/types";
import { TurnTranscript } from "./TurnTranscript";
import styles from "./WorkingMemoryView.module.css";

export function WorkingMemoryView({ turnBuffer }: { turnBuffer: Turn[] }) {
  return (
    <div className={styles.container}>
      <p className={styles.hint}>
        {turnBuffer.length === 0
          ? "Empty — either nothing has happened yet, or the session just closed and this buffer was cleared."
          : `${turnBuffer.length} turn${turnBuffer.length === 1 ? "" : "s"} in the live buffer, not yet written to episodic memory.`}
      </p>
      <TurnTranscript turns={turnBuffer} />
    </div>
  );
}
