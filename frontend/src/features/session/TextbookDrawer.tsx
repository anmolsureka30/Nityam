import { useEffect, useState } from "react";
import { Button, Label } from "../../components/ui";
import { textbookPage } from "../../lib/data";
import s from "./TextbookDrawer.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

/* The NCERT chapter, on the same surface as everything else.
 *
 * Highlighting here has to behave exactly like highlighting the notebook —
 * the tutor gets the context either way. That is why "Ask Nityam about this"
 * hands back the selected region rather than just closing the drawer. */
export default function TextbookDrawer({
  onClose, onPull,
}: {
  onClose: () => void;
  onPull: (sel: { id: string; text: string; concept: string; figure?: boolean }) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const page = textbookPage;
  const sel = page.selectable.find((x) => x.id === selected) ?? null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <button className={s.veil} aria-label="Close textbook" onClick={onClose} />
      <aside className={s.drawer} role="dialog" aria-label="Textbook">
        <div className={s.head}>
          <div>
            <div className={s.book}>{page.book}</div>
            <Label style={{ marginTop: 4 }}>{page.chapter}</Label>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div className={s.pager}>
              <button className={s.pageBtn} aria-label="Previous page">‹</button>
              <span className={s.pageNum}>{page.page} / {page.pageCount}</span>
              <button className={s.pageBtn} aria-label="Next page">›</button>
            </div>
            <button className={s.close} onClick={onClose} aria-label="Close">✕</button>
          </div>
        </div>

        <div className={s.body}>
          <div className={s.sheet}>
            <div className={s.sectionLabel}>{page.sectionLabel}</div>
            <h3 className={s.sectionTitle}>{page.sectionTitle}</h3>
            <p className={s.lead}>{page.lead}</p>

            {page.selectable.map((item) => (
              <button
                key={item.id}
                className={cx(s.selectable, selected === item.id && s.selectableOn)}
                aria-pressed={selected === item.id}
                onClick={() => setSelected(selected === item.id ? null : item.id)}
              >
                {item.figure ? (
                  <span className={s.figBox}>
                    <Label>Fig. 4.10 · parabolic path</Label>
                  </span>
                ) : (
                  item.text
                )}
              </button>
            ))}
          </div>
        </div>

        <div className={s.actions}>
          {sel ? (
            <>
              <span className={s.hint}>
                {sel.figure ? "Figure selected." : "Passage selected."} Nityam will read it in context.
              </span>
              <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>Clear</Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => { onPull(sel); setSelected(null); onClose(); }}
              >
                Ask Nityam about this
              </Button>
            </>
          ) : (
            <span className={s.hint}>Tap a passage or the figure to bring it into your notebook.</span>
          )}
        </div>
      </aside>
    </>
  );
}
