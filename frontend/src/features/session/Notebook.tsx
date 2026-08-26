import { Fragment, useMemo } from "react";
import { Label } from "../../components/ui";
import type { Anchor, ContextPacket, MarkTool, Notebook as NotebookDoc, NotebookBlock } from "../../lib/types";
import { projectile, studentFinding } from "../../lib/data";
import AnnotationLayer, { type Stroke } from "./AnnotationLayer";
import ProjectileSim from "./ProjectileSim";
import s from "./Notebook.module.css";

export interface PulledNote {
  id: string;
  label: string;
  source: string;
  body: string;
  quote?: string;
  figure?: boolean;
}

/** Splits a paragraph so each anchored term becomes a pointable element.
 *
 *  Matching is first-occurrence and word-bounded for short alphanumeric spans:
 *  the anchor "v" must land on the standalone symbol, not on the "v" inside
 *  "leaves". Getting this wrong silently anchors the wrong word, and the
 *  student's gesture then resolves to something they never pointed at. */
function segment(text: string, anchors: Anchor[] = []) {
  type Seg = { text: string; anchor?: Anchor };
  let segs: Seg[] = [{ text }];

  for (const anchor of anchors) {
    const bounded = /^[A-Za-z0-9]{1,3}$/.test(anchor.span);
    const re = new RegExp(
      bounded ? `\\b${anchor.span}\\b` : anchor.span.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
    );
    const next: Seg[] = [];
    let placed = false;
    for (const seg of segs) {
      if (placed || seg.anchor) { next.push(seg); continue; }
      const m = re.exec(seg.text);
      if (!m) { next.push(seg); continue; }
      const before = seg.text.slice(0, m.index);
      const after = seg.text.slice(m.index + m[0].length);
      if (before) next.push({ text: before });
      next.push({ text: m[0], anchor });
      if (after) next.push({ text: after });
      placed = true;
    }
    segs = next;
  }
  return segs;
}

function Anchored({
  text, anchors, blockId, hot,
}: { text: string; anchors?: Anchor[]; blockId: string; hot: Set<string> }) {
  const segs = useMemo(() => segment(text, anchors), [text, anchors]);
  return (
    <>
      {segs.map((seg, i) =>
        seg.anchor ? (
          <mark
            key={i}
            data-anchor={seg.anchor.id}
            data-block={blockId}
            className={`${s.anchor} ${hot.has(seg.anchor.id) ? s.anchorHot : ""}`}
            title={seg.anchor.concept}
          >
            {seg.text}
          </mark>
        ) : (
          <Fragment key={i}>{seg.text}</Fragment>
        ),
      )}
    </>
  );
}

export default function Notebook({
  doc, hostRef, tool, strokes, onStroke, onPacket, pulled, finding, hot, onExplored,
}: {
  doc: NotebookDoc;
  hostRef: React.RefObject<HTMLDivElement | null>;
  tool: MarkTool | null;
  strokes: Stroke[];
  onStroke: (s: Stroke) => void;
  onPacket: (p: ContextPacket) => void;
  pulled: PulledNote[];
  finding: boolean;
  hot: Set<string>;
  onExplored: (angle: number) => void;
}) {
  const anchorIndex = useMemo(() => {
    const map = new Map<string, Anchor>();
    for (const page of doc.pages) {
      for (const block of page.blocks) {
        if ("anchors" in block && block.anchors) {
          for (const a of block.anchors) map.set(a.id, a);
        }
      }
    }
    return map;
  }, [doc]);

  const renderBlock = (block: NotebookBlock) => {
    switch (block.kind) {
      case "heading":
        return <h2 key={block.id} className={s.heading}>{block.text}</h2>;

      case "tutor_text":
        return (
          <p key={block.id} className={s.para}>
            <Anchored text={block.text} anchors={block.anchors} blockId={block.id} hot={hot} />
          </p>
        );

      case "equation":
        return (
          <div key={block.id} className={s.equation}>
            <span className={s.equationTex} data-block={block.id}>
              <Anchored text={block.tex} anchors={block.anchors} blockId={block.id} hot={hot} />
            </span>
            {block.caption && <Label>{block.caption}</Label>}
          </div>
        );

      case "artifact":
        return <ProjectileSim key={block.id} spec={projectile} onExplored={onExplored} />;

      case "callout":
        return (
          <div
            key={block.id}
            className={`${s.callout} ${block.tone === "correction" ? s.calloutCorrection : s.calloutFinding}`}
          >
            <Label tone={block.tone === "correction" ? "warn" : undefined}>{block.label}</Label>
            <p className={s.calloutText}>{block.text}</p>
          </div>
        );

      case "pulled":
        return null; // pulled notes are appended live, below

      case "next":
        return (
          <div key={block.id} className={`${s.sheet} ${s.next}`} style={{ margin: 0 }}>
            <Label>{block.label}</Label>
            <h3 className={s.nextTitle} style={{ marginTop: 10 }}>{block.title}</h3>
            <p className={s.para} style={{ margin: 0, fontSize: 15.5, color: "var(--ink-mid)" }}>
              {block.text}
            </p>
          </div>
        );
    }
  };

  return (
    <div className={s.scroll} ref={hostRef}>
      {doc.pages.map((page) => {
        const isNextPage = page.blocks.every((b) => b.kind === "next");
        if (isNextPage) return <div key={page.page}>{page.blocks.map(renderBlock)}</div>;

        return (
          <article className={s.sheet} key={page.page}>
            <div className={s.sheetHead}>
              <Label>{page.eyebrow}</Label>
              <Label>Page {page.page} of {doc.pages[doc.pages.length - 1].page}</Label>
            </div>

            {page.blocks.map(renderBlock)}

            {/* Anything the student pulled in from the textbook lands here,
                after the tutor's own writing, so authorship stays legible. */}
            {pulled.map((note) => (
              <div className={s.pulled} key={note.id}>
                <div className={s.pulledHead}>
                  <Label>{note.label}</Label>
                  <Label>{note.source}</Label>
                </div>
                {note.figure && (
                  <div className={s.figure}>
                    <Label>Cropped where you highlighted</Label>
                  </div>
                )}
                {note.quote && <blockquote className={s.pulledQuote}>{note.quote}</blockquote>}
                <p className={s.pulledBody}>{note.body}</p>
              </div>
            ))}

            {finding && (
              <div className={`${s.callout} ${s.calloutFinding}`}>
                <Label>{studentFinding.label}</Label>
                <p className={s.calloutText}>{studentFinding.text}</p>
                <div className={s.calloutFoot}>
                  <Label>{studentFinding.footnote}</Label>
                </div>
              </div>
            )}
          </article>
        );
      })}

      <AnnotationLayer
        hostRef={hostRef}
        tool={tool}
        anchors={anchorIndex}
        page={doc.pages[0].page}
        strokes={strokes}
        onStroke={onStroke}
        onPacket={onPacket}
      />
    </div>
  );
}
