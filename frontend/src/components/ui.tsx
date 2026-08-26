import type { CSSProperties, ReactNode } from "react";
import s from "./ui.module.css";

const cx = (...parts: (string | false | undefined)[]) => parts.filter(Boolean).join(" ");

/** Small uppercase mono label. The design's workhorse for metadata. */
export function Label({
  children, tone, style,
}: { children: ReactNode; tone?: "accent" | "warn"; style?: CSSProperties }) {
  return (
    <div
      className={cx(s.label, tone === "accent" && s.labelAccent, tone === "warn" && s.labelWarn)}
      style={style}
    >
      {children}
    </div>
  );
}

export function Card({
  children, size = "md", quiet, style, as: As = "div",
}: {
  children: ReactNode;
  size?: "md" | "lg";
  quiet?: boolean;
  style?: CSSProperties;
  as?: "div" | "section" | "article";
}) {
  return (
    <As className={cx(s.card, size === "lg" && s.cardLg, quiet && s.cardQuiet)} style={style}>
      {children}
    </As>
  );
}

export function ActionCard({
  eyebrow, title, body, footer, primary, onClick,
}: {
  eyebrow: ReactNode;
  title: string;
  body: string;
  footer?: ReactNode;
  primary?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(s.actionCard, primary && s.actionCardPrimary)}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {primary && <span className={s.dot} />}
        <Label tone={primary ? "accent" : undefined}>{eyebrow}</Label>
      </div>
      <div className={s.cardTitle}>{title}</div>
      <div className={s.cardBody}>{body}</div>
      {footer && <div style={{ marginTop: "auto", paddingTop: 12 }}>{footer}</div>}
    </button>
  );
}

export function Button({
  children, onClick, variant = "default", size, block, type = "button", disabled, title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "default" | "primary" | "ghost";
  size?: "sm";
  block?: boolean;
  type?: "button" | "submit";
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cx(
        s.btn,
        variant === "primary" && s.btnPrimary,
        variant === "ghost" && s.btnGhost,
        size === "sm" && s.btnSm,
        block && s.btnBlock,
      )}
      style={disabled ? { opacity: 0.45, cursor: "default" } : undefined}
    >
      {children}
    </button>
  );
}

/** Mastery bar. The colour band is semantic — where the student stands —
 *  and deliberately not the brand accent. */
export function MasteryBar({
  name, pct, delta, hideName,
}: { name?: string; pct: number; delta?: number; hideName?: boolean }) {
  const band = pct < 50 ? s.fillLow : pct < 75 ? s.fillMid : s.fillHigh;
  return (
    <div className={s.masteryRow}>
      {!hideName && (
        <div className={s.masteryHead}>
          <span className={s.masteryName}>{name}</span>
          <span className={s.masteryPct}>
            {pct}%
            {delta !== undefined && delta !== 0 && (
              <span style={{ color: delta > 0 ? "var(--good)" : "var(--danger)", marginLeft: 6 }}>
                {delta > 0 ? "+" : ""}{delta}
              </span>
            )}
          </span>
        </div>
      )}
      <div className={s.track}>
        <div className={cx(s.fill, band)} style={{ width: `${Math.max(2, Math.min(100, pct))}%` }} />
      </div>
    </div>
  );
}

export function Chip({
  children, tone,
}: { children: ReactNode; tone?: "accent" | "warn" }) {
  return (
    <span className={cx(s.chip, tone === "accent" && s.chipAccent, tone === "warn" && s.chipWarn)}>
      {children}
    </span>
  );
}

export function Stat({
  label, value, note,
}: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className={s.stat}>
      <Label>{label}</Label>
      <div className={s.statValue}>{value}</div>
      {note && <div className={s.statNote}>{note}</div>}
    </div>
  );
}
