import { useState } from "react";
import { Button, Label } from "../../components/ui";
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
  onSend, listening, onToggleMic, onEnd,
}: {
  tool: MarkTool | null;
  onTool: (t: MarkTool | null) => void;
  onClear: () => void;
  hasMarks: boolean;
  packet: ContextPacket | null;
  packetSummary: string;
  onAskAboutMark: () => void;
  onSend: (text: string) => void;
  listening: boolean;
  onToggleMic: () => void;
  onEnd: () => void;
}) {
  const [draft, setDraft] = useState("");

  return (
    <>
      {hasMarks && packet && (
        <div className={s.marked}>
          <Label tone="accent">You marked on the page</Label>
          <div className={s.markedRow}>
            <span className={s.markedText}>{packetSummary}</span>
            <Button variant="primary" size="sm" onClick={onAskAboutMark}>Ask about this</Button>
          </div>
          {packet.resolved.length > 0 && (
            <div className={s.confidence}>
              Confidence {Math.round(packet.confidence * 100)}%
              {packet.nearby.length > 0 && ` · also near “${packet.nearby[0].text}”`}
            </div>
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
          <button
            type="button"
            className={cx(s.mic, listening && s.micOn)}
            aria-pressed={listening}
            aria-label={listening ? "Stop listening" : "Talk to Nityam"}
            onClick={onToggleMic}
          >
            ◍
          </button>
        </form>

        <span className={s.divider} />
        <button className={s.end} onClick={onEnd}>End session</button>
      </div>
    </>
  );
}
