import { useState } from "react";
import type { MarkTool } from "../../lib/types";
import type { Specialist } from "../../lib/live/specialists";
import { thinkingLine } from "../../lib/live/specialists";
import s from "./SessionControls.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

const TOOLS: { id: MarkTool; glyph: string; label: string }[] = [
  { id: "marker", glyph: "✎", label: "Marker" },
  { id: "circle", glyph: "○", label: "Circle" },
  { id: "lasso", glyph: "◇", label: "Lasso" },
];

export default function SessionControls({
  tool, onTool, onClear, hasMarks,
  onSend, onEnd, thinking, specialist,
}: {
  tool: MarkTool | null;
  onTool: (t: MarkTool | null) => void;
  onClear: () => void;
  hasMarks: boolean;
  onSend: (text: string) => void;
  onEnd: () => void;
  /** She has delegated and is waiting. That wait is real — 6-20 seconds — so
   *  it has to be visible or the page reads as broken. */
  thinking: boolean;
  /** What she said she was going off to do, in her own words. Shown instead of
   *  a generic placeholder: "Working that out…" told the student nothing they
   *  could not already see, while the line she actually produced —
   *  "Certainly, I can show you the derivation of the range formula" — was
   *  sitting unused in the tool call. */
  /** Which specialist she has delegated to, when known. Picks the fallback
   *  phrase in thinkingLine() below when `bridge` is absent — `null`/absent
   *  means either she isn't thinking, or an unrecognized delegate tool was
   *  reached (never breaks the UI, just loses the enrichment). */
  specialist?: Specialist | null;
}) {
  const [draft, setDraft] = useState("");

  return (
    <>
      {/* Her own transcript of the student used to live here as proof the mic
          worked. The mic is live and visibly metered now, so echoing every
          sentence back was just a second subtitle track. What is still worth
          saying is that she has gone away to think. */}
      {thinking && (
        <div className={s.heard}>
          <span className={s.thinking}>
            <i /><i /><i />
            <span className={s.thinkingText}>
              {thinkingLine(specialist ?? null)}
            </span>
          </span>
        </div>
      )}

      {/* The "You marked … / Ask about this" card is gone. Highlighting now
          sends the swept text and the sentences around it to the tutor
          immediately, as context that does not complete her turn — so the
          student marks a term, asks "what is this", and she already has the
          referent. Asking them to press a button first meant the spoken
          question arrived with nothing attached. */}
      <div className={s.bar}>
        <div className={s.tools} role="toolbar" aria-label="Annotation tools">
          {TOOLS.map((t) => (
            <button
              key={t.id}
              className={cx(s.tool, tool === t.id && s.toolOn)}
              aria-pressed={tool === t.id}
              title={`${t.label} — mark the page and ask about it`}
              onClick={() => onTool(tool === t.id ? null : t.id)}
            >
              {t.glyph} {t.label}
            </button>
          ))}
          {hasMarks && (
            <button className={s.tool} onClick={onClear}>Clear</button>
          )}
        </div>

        <span className={s.divider} />

        <form
          style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, minWidth: 0 }}
          onSubmit={(e) => {
            e.preventDefault();
            const text = draft.trim();
            if (!text) return;
            onSend(text);
            setDraft("");
          }}
        >
          <div className={s.field}>
            <span aria-hidden="true" style={{ color: "var(--ink-dim)", fontSize: 13 }}>⌨</span>
            <input
              className={s.input}
              value={draft}
              placeholder="Ask Nityam anything"
              aria-label="Ask Nityam"
              onChange={(e) => setDraft(e.target.value)}
            />
          </div>
          {/* A real submit button, not decoration: without one the form has no
              implicit-submission target, so pressing Enter in the field did
              nothing at all. */}
          <button
            type="submit"
            className={s.send}
            disabled={!draft.trim()}
            aria-label="Send to Nityam"
            title="Send"
          >
            ↵
          </button>
        </form>

        <span className={s.divider} />
        <button className={s.end} onClick={onEnd}>End session</button>
      </div>
    </>
  );
}
