import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { conceptName } from "../../lib/conceptCatalog";
import { useAuth } from "../../lib/auth/AuthContext";
import { fetchSessionRecap, type SessionRecap } from "../../lib/memory";
import s from "./SessionExport.module.css";

/* The board as a document, built to be printed and nothing else.
 *
 * WHY THIS IS A SEPARATE PAGE. Printing the live session screen produces a
 * mess: it is a fixed-height scroller inside a flex layout with an avatar, a
 * composer and a toolbar, and the print stylesheet ends up fighting five
 * modules' worth of screen layout to undo it. Every block that renders
 * specially — an equation, a callout, a pulled figure — has to survive that
 * fight intact, and the ones that get it wrong are exactly the ones worth
 * keeping.
 *
 * So this renders the stored board from scratch, in one flow, with print
 * typography and nothing to undo. Real text throughout — the equations stay
 * selectable and searchable, and subscripts stay subscripts — which is the
 * argument against rasterising the screen with html2canvas: that would turn a
 * page of physics into a picture of a page of physics.
 *
 * It opens the print dialog itself, once the fonts have settled. "Save as PDF"
 * is the destination in every browser's print dialog, so there is no library
 * here and nothing to keep up to date. */

interface Block {
  id: string;
  kind: string;
  text?: string;
  tex?: string;
  caption?: string;
  label?: string;
  tone?: string;
  struck?: boolean;
  source?: string;
  body?: string;
  title?: string;
}

/** `H_max` and `v_{0y}` as real subscripts. The board writes blackboard
 *  notation rather than LaTeX, so the underscore is the notation — and on
 *  paper, of all places, it should not read as an underscore. */
const SUB = /([A-Za-z0-9)\]])_(?:\{([^}]{1,16})\}|([A-Za-z0-9]{1,8}))/g;

function Maths({ text }: { text: string }) {
  const out: (string | React.ReactElement)[] = [];
  let last = 0;
  for (const m of text.matchAll(SUB)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    out.push(m[1]!);
    out.push(<sub key={at}>{m[2] ?? m[3]}</sub>);
    last = at + m[0].length;
  }
  if (last === 0) return <>{text}</>;
  if (last < text.length) out.push(text.slice(last));
  return <>{out}</>;
}

function BoardBlock({ block }: { block: Block }) {
  const struck = block.struck ? s.struck : "";
  switch (block.kind) {
    case "heading":
      return <h2 className={`${s.heading} ${struck}`}>{block.text}</h2>;
    case "equation":
      return (
        <div className={`${s.equation} ${struck}`}>
          <div className={s.tex}><Maths text={block.tex ?? ""} /></div>
          {block.caption && <div className={s.caption}>{block.caption}</div>}
        </div>
      );
    case "callout":
      return (
        <div className={`${s.callout} ${block.tone === "correction" ? s.correction : ""} ${struck}`}>
          {block.label && <div className={s.calloutLabel}>{block.label}</div>}
          <p className={s.calloutText}><Maths text={block.text ?? ""} /></p>
        </div>
      );
    case "pulled":
      // The figure itself is a PDF page render that only exists in the live
      // session. Naming what it was beats a broken image box.
      return (
        <div className={s.pulled}>
          <div className={s.pulledLabel}>{block.label ?? "From your textbook"}</div>
          {block.source && <div className={s.pulledSource}>{block.source}</div>}
          {block.body && <p className={s.pulledBody}>{block.body}</p>}
        </div>
      );
    case "artifact":
      return (
        <div className={s.pulled}>
          <div className={s.pulledLabel}>Interactive simulation</div>
          <p className={s.pulledBody}>
            {block.title ?? "A simulation you explored in this session."} It
            needs a screen to run, so it is named here rather than pictured.
          </p>
        </div>
      );
    default:
      return (
        <p className={`${s.para} ${struck}`}><Maths text={block.text ?? ""} /></p>
      );
  }
}

export default function SessionExport() {
  const { user } = useAuth();
  const { sessionId = "" } = useParams();
  const [recap, setRecap] = useState<SessionRecap | null>(null);
  const [failed, setFailed] = useState("");

  useEffect(() => {
    if (!user?.uid || !sessionId) return;
    let live = true;
    fetchSessionRecap(user.uid, sessionId)
      .then((r) => live && setRecap(r))
      .catch((e) => live && setFailed((e as Error).message));
    return () => { live = false; };
  }, [user?.uid, sessionId]);

  const topic = recap?.topic || "Session";
  const when = recap?.ended_at ? new Date(recap.ended_at) : null;

  // The browser names the PDF after document.title.
  useEffect(() => {
    if (!recap) return;
    const had = document.title;
    const day = when ? when.toISOString().slice(0, 10) : "";
    document.title = `Nityam — ${topic}${day ? ` — ${day}` : ""}`;
    return () => { document.title = had; };
  }, [recap, topic]);

  // Print once the document is actually on screen. Waiting on fonts matters:
  // printing mid-swap lays the page out in the fallback face and reflows the
  // equations, which is precisely the mess this page exists to avoid.
  useEffect(() => {
    if (!recap) return;
    let cancelled = false;
    const go = () => { if (!cancelled) window.print(); };
    const fonts = (document as Document & { fonts?: FontFaceSet }).fonts;
    if (fonts?.ready) fonts.ready.then(() => setTimeout(go, 250));
    else setTimeout(go, 600);
    return () => { cancelled = true; };
  }, [recap]);

  if (failed) return <div className={s.state}>Couldn't load this session ({failed}).</div>;
  if (!recap) return <div className={s.state}>Preparing your notes…</div>;
  if (!recap.found) return <div className={s.state}>No such session.</div>;

  // The stored board is a durable record of what was on screen that day, so
  // the API hands it back untyped on purpose — it must keep deserialising
  // after the block schema grows a field this build has never heard of.
  const pages = (recap.board?.pages ?? []) as unknown as { page: number; blocks: Block[] }[];
  const blocks = pages.flatMap((p) => p.blocks ?? []);

  return (
    <div className={s.sheet}>
      <header className={s.head}>
        <div className={s.brand}>Nityam</div>
        <h1 className={s.topic}>{topic}</h1>
        <div className={s.meta}>
          {when && when.toLocaleDateString([], {
            weekday: "long", day: "numeric", month: "long", year: "numeric",
          })}
          {recap.mode && ` · ${recap.mode}`}
        </div>
      </header>

      {recap.summary && (
        <section className={s.summary}>
          <div className={s.sectionLabel}>What we did</div>
          <p>{recap.summary}</p>
        </section>
      )}

      {blocks.length > 0 ? (
        <section className={s.board}>
          {blocks.map((b) => <BoardBlock key={b.id} block={b} />)}
        </section>
      ) : (
        <section className={s.board}>
          <p className={s.para}>
            {/* Sessions that closed before boards were stored have none, and
                saying so is better than printing a blank sheet. */}
            Nothing was written on the board in this session, or it closed
            before boards were kept.
          </p>
        </section>
      )}

      {recap.changes.length > 0 && (
        <section className={s.changes}>
          <div className={s.sectionLabel}>What changed</div>
          <ul>
            {recap.changes.map((c) => (
              <li key={`${c.kind}:${c.concept_id}`}>
                <strong>{conceptName(c.concept_id)}</strong>
                {c.from ? ` — ${c.from} to ${c.to}` : ` — now ${c.to}`}
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className={s.foot}>
        Nityam · your own class, your own notes
      </footer>
    </div>
  );
}
