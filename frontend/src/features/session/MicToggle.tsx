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
 * IT IS A CIRCLE WITH A MICROPHONE IN IT. It used to be a pill reading
 * "Listening" / "Muted", which is a status readout wearing the clothes of a
 * control: you had to read a word to find out what it did, and nothing about it
 * said "click me to stop her hearing you". A struck-through mic is understood
 * without reading anything, and the word underneath now confirms the state
 * rather than carrying it alone.
 *
 * The ring tracks the real input level while live. A control that looks the
 * same whether or not sound is arriving is the reason a dead mic is impossible
 * to tell from a slow answer. */
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
    <div className={s.dock}>
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
        {/* The ring breathes with what the mic is picking up, so silence and a
            dead device look different. */}
        <span className={s.ring} aria-hidden="true" />
        <svg className={s.glyph} viewBox="0 0 24 24" aria-hidden="true">
          {/* Capsule, stand and base — a microphone at any size. */}
          <rect x="9" y="3" width="6" height="10" rx="3" />
          <path d="M5.5 11a6.5 6.5 0 0 0 13 0" />
          <line x1="12" y1="17.5" x2="12" y2="21" />
          <line x1="8.5" y1="21" x2="15.5" y2="21" />
          {/* The slash. Drawn as two strokes — a light one beneath in the
              button's own colour — so it reads as cutting THROUGH the mic
              rather than lying on top of it. */}
          {muted && <line className={s.slashCut} x1="4" y1="3.4" x2="20" y2="20.6" />}
          {muted && <line className={s.slash} x1="4" y1="3.4" x2="20" y2="20.6" />}
        </svg>
      </button>
      <span className={cx(s.caption, muted && s.captionMuted, blocked && s.captionBlocked)}>
        {blocked ? "No mic" : muted ? "Muted" : "Listening"}
      </span>
    </div>
  );
}
