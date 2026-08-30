import { Fragment, useMemo, useState, type ReactNode } from "react";
import { Label } from "../../components/ui";
import type { EvidenceEvent } from "../../lib/artifact";
import { projectile } from "../../lib/data";
import type { PageBlock } from "../../lib/notebookReducer";
import type { Anchor, ContextPacket, MarkTool, Notebook as NotebookDoc } from "../../lib/types";
import AnnotationLayer, { type Stroke } from "./AnnotationLayer";
import ArtifactBlock from "./ArtifactBlock";
import ProjectileSim from "./ProjectileSim";
import Lightbox, { type LightboxSource } from "./Lightbox";
import TextbookFigure from "./TextbookFigure";
import s from "./Notebook.module.css";

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

/* `H_max` on a blackboard means H with a subscript, and it was rendering as
 * the literal characters — "H underscore max" — everywhere an equation or a
 * paragraph mentioned one. BoardAgent writes blackboard notation rather than
 * LaTeX (no renderer, deliberately), so the underscore IS the notation and
 * this is the one piece of it that needs interpreting.
 *
 * Handles `H_max` and `v_{0y}`. Kept to subscripts on purpose: superscripts
 * are already written as `u²` with the real character, and a general maths
 * renderer is a much larger change than the problem calls for. */
const SUBSCRIPT = /([A-Za-z0-9)\]])_(?:\{([^}]{1,16})\}|([A-Za-z0-9]{1,8}))/g;

function subscripted(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(SUBSCRIPT)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    out.push(m[1]);
    out.push(<sub key={`${keyBase}-${at}`}>{m[2] ?? m[3]}</sub>);
    last = at + m[0].length;
  }
  if (last === 0) return [text];
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function Anchored({
  text, anchors, blockId, hot,
}: { text: string; anchors?: Anchor[]; blockId: string; hot: Record<string, number> }) {
  const segs = useMemo(() => segment(text, anchors), [text, anchors]);
  return (
    <>
      {segs.map((seg, i) =>
        seg.anchor ? (
          <mark
            key={i}
            data-anchor={seg.anchor.id}
            data-block={blockId}
            className={`${s.anchor} ${seg.anchor.id in hot ? s.anchorHot : ""}`}
            title={seg.anchor.concept}
          >
            {subscripted(seg.text, `${blockId}-a${i}`)}
          </mark>
        ) : (
          <Fragment key={i}>{subscripted(seg.text, `${blockId}-t${i}`)}</Fragment>
        ),
      )}
    </>
  );
}

export default function Notebook({
  doc, hostRef, tool, strokes, onStroke, onPacket, hot,
  waiting, interest, onEvidence, onSimulation,
}: {
  doc: NotebookDoc;
  hostRef: React.RefObject<HTMLDivElement | null>;
  tool: MarkTool | null;
  strokes: Stroke[];
  onStroke: (s: Stroke) => void;
  onPacket: (p: ContextPacket) => void;
  /** anchorId -> expiry timestamp. Two-way pointing: the student marks a term,
   *  and the tutor lights up the same term. */
  hot: Record<string, number>;
  /** True until the tutor has written anything, so the page can say so rather
   *  than looking broken. */
  waiting: boolean;
  interest: string;
  onEvidence: (event: { artifactId: string; event: string; detail?: string }) => void;
  onSimulation: (state: Record<string, number>) => void;
}) {
  /* One at a time, held here rather than inside the figure, so opening a second
     figure replaces the first instead of stacking two viewers. */
  const [zoomed, setZoomed] = useState<{ source: LightboxSource; caption?: string } | null>(
    null,
  );

  const renderBlock = (block: PageBlock) => {
    const struck = block.struck ? s.struck : "";

    switch (block.kind) {
      case "heading":
        return (
          <h2 key={block.id} data-block={block.id} data-kind="heading"
              className={`${s.heading} ${struck}`}>
            {block.text}
          </h2>
        );

      case "tutor_text":
        return (
          <p key={block.id} data-block={block.id} data-kind="tutor_text"
             className={`${s.para} ${struck}`}>
            <Anchored text={block.text} anchors={block.anchors} blockId={block.id} hot={hot} />
          </p>
        );

      case "equation":
        return (
          <div key={block.id} className={`${s.equation} ${struck}`}>
            <span className={s.equationTex} data-block={block.id} data-kind="equation">
              <Anchored text={block.tex} anchors={block.anchors} blockId={block.id} hot={hot} />
            </span>
            {block.caption && (
              <Label style={{ marginTop: "var(--s-3)" }}>{block.caption}</Label>
            )}
          </div>
        );

      case "artifact":
        // An IR means ArtifactAgent generated this one; without it, fall back to
        // the hand-written kernel so mock mode still has something to explore.
        return block.ir ? (
          <ArtifactBlock
            key={block.id}
            /* The shadow root hides the artifact's own text from readPage, so a
               gesture here reports the block with no quote. That is correct and
               deliberate — "you marked the simulation" beats a quote of its
               internal axis labels. */
            ir={block.ir}
            artifactId={block.artifactId}
            interest={interest}
            struck={block.struck}
            onEvidence={(event: EvidenceEvent) =>
              onEvidence({
                artifactId: block.artifactId,
                event: event.event,
                detail: event.detail ?? (event.concept_ids ?? []).join(", "),
              })
            }
          />
        ) : (
          <div key={block.id} data-block={block.id} data-kind="artifact" className={struck}>
            <ProjectileSim
              spec={projectile}
              onExplored={(angle) => {
                onSimulation({ angle });
                onEvidence({
                  artifactId: block.artifactId,
                  event: "discovered_optimum",
                  detail: `settled at ${Math.round(angle)}°`,
                });
              }}
              onChange={(angle) => onSimulation({ angle, speed: projectile.speed })}
            />
          </div>
        );

      case "callout":
        return (
          <div
            key={block.id}
            data-block={block.id}
            data-kind="callout"
            className={`${s.callout} ${
              block.tone === "correction" ? s.calloutCorrection : s.calloutFinding
            } ${struck}`}
          >
            <Label tone={block.tone === "correction" ? "warn" : undefined}>{block.label}</Label>
            <p className={s.calloutText}>{block.text}</p>
          </div>
        );

      case "pulled":
        return (
          <div key={block.id} data-block={block.id} data-kind="pulled" className={`${s.pulled} ${struck}`}>
            <div className={s.pulledHead}>
              <Label>{block.label}</Label>
              <Label>{block.source}</Label>
            </div>
            {/* Two ways in: the student clipped a region (an image), or the
                tutor named a page (rendered here). Either way it opens: a
                textbook page at notebook size is unreadable, which made the
                tutor's best move — "look at figure 3.9" — the one thing the
                student could not actually do. */}
            {block.image ? (
              <button
                type="button"
                className={s.figureOpen}
                onClick={() =>
                  setZoomed({
                    source: { kind: "image", src: block.image! },
                    caption: block.source || block.body,
                  })
                }
                title="Click to enlarge"
                aria-label={`Enlarge ${block.body || "this figure"}`}
              >
                <img
                  className={s.figureImg}
                  src={block.image}
                  alt={block.body || "Figure from the textbook"}
                />
                <span className={s.figureZoom} aria-hidden="true">⤢</span>
              </button>
            ) : block.pdf && block.page ? (
              <button
                type="button"
                className={s.figureOpen}
                onClick={() =>
                  setZoomed({
                    source: { kind: "pdf", pdf: block.pdf!, page: block.page! },
                    caption: block.source,
                  })
                }
                title="Click to enlarge"
                aria-label={`Enlarge ${block.source || `textbook page ${block.page}`}`}
              >
                <TextbookFigure pdf={block.pdf} page={block.page} clip={block.clip} />
                <span className={s.figureZoom} aria-hidden="true">⤢</span>
              </button>
            ) : null}
            {block.quote && <blockquote className={s.pulledQuote}>{block.quote}</blockquote>}
            {block.body && <p className={s.pulledBody}>{block.body}</p>}
          </div>
        );

      case "next":
        return (
          <div
            key={block.id}
            data-block={block.id}
            data-kind="next"
            className={`${s.sheet} ${s.next} ${struck}`}
            style={{ margin: 0 }}
          >
            <Label>{block.label}</Label>
            <h3 className={s.nextTitle} style={{ marginTop: 10 }}>{block.title}</h3>
            <p className={s.para} style={{ margin: 0, fontSize: 15.5, color: "var(--ink-mid)" }}>
              {block.text}
            </p>
          </div>
        );

      default:
        // A block kind the backend added and this build does not know yet.
        // Skipping quietly is better than crashing the lesson.
        return null;
    }
  };

  const lastPage = doc.pages.length ? doc.pages[doc.pages.length - 1].page : 1;

  return (
    <div className={s.scroll} ref={hostRef}>
      {doc.pages.map((page) => {
        const isNextPage =
          page.blocks.length > 0 && page.blocks.every((b) => b.kind === "next");
        if (isNextPage) {
          return <div key={page.page}>{(page.blocks as PageBlock[]).map(renderBlock)}</div>;
        }

        return (
          <article className={s.sheet} key={page.page} data-page={page.page}>
            <div className={s.sheetHead}>
              <Label>{page.eyebrow}</Label>
              <Label>Page {page.page} of {lastPage}</Label>
            </div>

            {(page.blocks as PageBlock[]).map(renderBlock)}

            {/* The board fills as she teaches. Say that, rather than showing a
                blank sheet that reads as a failed load. */}
            {waiting && page.page === 1 && (
              <p className={s.waiting}>
                Your page starts empty — everything here gets written as you two
                work through it. Press the mic and ask her something.
              </p>
            )}

          </article>
        );
      })}

      <AnnotationLayer
        hostRef={hostRef}
        tool={tool}
        strokes={strokes}
        onStroke={onStroke}
        onPacket={onPacket}
      />

      {/* Last, and fixed-position, so it sits over the avatar and the controls
          as well as the page. */}
      {zoomed && (
        <Lightbox
          source={zoomed.source}
          caption={zoomed.caption}
          onClose={() => setZoomed(null)}
        />
      )}
    </div>
  );
}
