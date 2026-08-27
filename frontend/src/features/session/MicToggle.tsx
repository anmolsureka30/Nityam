import s from "./MicToggle.module.css";

const cx = (...p: (string | false | undefined)[]) => p.filter(Boolean).join(" ");

/* Mute, sitting with the tutor rather than with the drawing tools.
 *
 * It lives beside her because that is what it is about — whether she can hear
 * you — and not in the toolbar, which is about marking up the page. It is a
 * mute rather than a push-to-talk: the mic opens with the session, because a
 * voice tutor that needs a button pressed before it will listen is one a
 * student reasonably concludes is broken.
 *
 * The dot tracks the real input level while live. A control that looks the same
 * whether or not sound is arriving is the reason a dead mic is impossible to
 * tell from a slow answer. */
export default function MicToggle({
  muted, listening, level, onToggle,
}: {
  muted: boolean;
  /** The mic is actually open. Distinct from `!muted`: permission can be
   *  refused, in which case we are unmuted and still not listening. */
  listening: boolean;
  level: number;
  onToggle: () => void;
}) {
  const blocked = !muted && !listening;
  // Speech sits low in linear amplitude, so a meter that only moves near the
  // top of its range never moves at all.
  const meter = Math.min(1, level * 6);

  return (
    <button
      type="button"
      className={cx(s.mic, listening && s.live, muted && s.muted, blocked && s.blocked)}
      onClick={onToggle}
      aria-pressed={muted}
      aria-label={muted ? "Unmute your microphone" : "Mute your microphone"}
      title={
        blocked
          ? "No microphone. Check Chrome's microphone permission."
          : muted
            ? "She cannot hear you — click to unmute"
            : "She can hear you — click to mute"
      }
      style={listening ? ({ "--level": meter } as React.CSSProperties) : undefined}
    >
      <span className={s.dot} aria-hidden="true" />
      <span className={s.label}>
        {blocked ? "No mic" : muted ? "Muted" : "Listening"}
      </span>
    </button>
  );
}
