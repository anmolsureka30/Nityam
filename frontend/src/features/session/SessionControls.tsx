import { useState } from "react";
import { Button, Label } from "../../components/ui";
import { describeSource } from "../../lib/grounding";
import type { ContextPacket, MarkTool } from "../../lib/types";
import s from "./SessionControls.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

const TOOLS: { id: MarkTool; glyph: string; label: string }[] = [
  { id: "marker", glyph: "✎", label: "Marker" },
  { id: "circle", glyph: "○", label: "Circle" },
  { id: "lasso", glyph: "◇", label: "Lasso" },
];

export default function SessionControls({
  tool, onTool, onClear, hasMarks, packet, packetSummary, onAskAboutMark,
  onSend, onEnd, thinking,
}: {
  tool: MarkTool | null;
  onTool: (t: MarkTool | null) => void;
  onClear: () => void;
  hasMarks: boolean;
  packet: ContextPacket | null;
  packetSummary: string;
  onAskAboutMark: () => void;
  onSend: (text: string) => void;
  onEnd: () => void;
  /** She has delegated and is waiting. That wait is real — 15-20 seconds — so
   *  it has to be visible or the page reads as broken. */
  thinking: boolean;
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
            <span className={s.thinkingText}>Working that out…</span>
          </span>
        </div>
      )}

      {hasMarks && packet && (
        <div className={s.marked}>
          <Label tone="accent">You marked on the page</Label>
          <div className={s.markedRow}>
            <span className={s.markedText}>{packetSummary}</span>
            <Button variant="primary" size="sm" onClick={onAskAboutMark}>Ask about this</Button>
          </div>
          {/* A DOM-measured sweep is exact, so there is no confidence score to
              report any more — what is worth showing is WHERE it came from, so
              the student can see the tutor read the right part of the page. */}
          {packet.regions.length > 0 && (
            <div className={s.confidence}>{describeSource(packet)}</div>
          )}
        </div>
      )}

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
