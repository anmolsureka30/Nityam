import { turnDomId } from "../components/memory-views/TurnTranscript";

/** Scrolls to and briefly flashes the turn a piece of long-term evidence
 * cites — works when that turn is rendered anywhere on the page (Working
 * or Episodic memory, both live in the State tab). If the turn isn't
 * currently rendered (citing a different, not-selected session), this is
 * a no-op — there's nothing to scroll to. */
export function jumpToTurn(sessionId: string, turn: number): void {
  const el = document.getElementById(turnDomId(sessionId, turn));
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("evidence-jump-highlight");
  window.setTimeout(() => el.classList.remove("evidence-jump-highlight"), 1600);
}
