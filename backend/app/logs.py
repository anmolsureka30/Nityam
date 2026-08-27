"""Logging: a readable terminal, plus one complete `.log` file per session.

Two audiences, so two formats.

**The terminal** stays skimmable — three numbers and one line per interesting
event, because you are watching it while you talk to the tutor:

    14:48:21.430    +0.31s   T+0.3s  INFO nityam: → TOOL CALL ask_tutor(…)
    14:48:25.213    +3.70s   T+4.1s  INFO adk…google_llm: Response received.

  * the wall clock, to milliseconds — so a line can be lined up with the moment
    something looked wrong on screen
  * **+Δ, since the previous line** — the one that actually finds the problem.
    An 11-second gap in that column is the answer to "why was she quiet".
  * T+, since this turn began — the total the student has been waiting.

The turn clock resets whenever the student is heard or types, so T+ reads as
"how long since I said something" rather than an ever-growing session total.

**The file** is the forensic record: `backend/logs/<session>_<start>.log`, one
per WebSocket connection, at DEBUG, with nothing truncated — full tool
arguments, full tool results, every board patch, every stage direction, the
frame accounting for the microphone. The terminal deliberately drops all of
that; when a session goes wrong you want it back.

Both end with the same thing the terminal can never show you: a **turn
timeline**, written at session close, attributing every second of the session
to a turn and every turn's cost to model calls, tool calls or the student
thinking. That table is the answer to "where is the latency".

### How a record finds its session

`SESSION` is a `ContextVar` set once in the WebSocket handler. asyncio tasks
inherit the context they were created in, so all four per-connection tasks —
and the brain's own `run_async` invocation nested inside them — stamp the right
session id without a single call site having to pass it. Concurrent students
therefore get clean, separate files rather than one interleaved mess.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

LOG_DIR = Path(
    os.getenv("NITYAM_LOG_DIR")
    or Path(__file__).resolve().parent.parent / "logs"
)

# Set in app/main.py's WebSocket handler; read by the per-session file handlers.
SESSION: ContextVar[str] = ContextVar("nityam_session", default="")

TERMINAL_FMT = (
    "%(asctime)s.%(msecs)03d %(gap)9s %(turn)8s  %(levelname)s %(name)s: %(message)s"
)
FILE_FMT = (
    "%(asctime)s.%(msecs)03d %(gap)9s %(turn)8s  %(levelname)-7s %(name)s: %(message)s"
)


class Elapsed(logging.Formatter):
    """Adds the gap and turn columns.

    One instance is shared by every handler so the gap is measured across all
    loggers rather than per-logger — otherwise a handoff from `nityam` to
    `nityam.brain` resets it and hides the gap that matters most. It also means
    the same numbers appear in the terminal and in the file, so a line can be
    matched between them.
    """

    def __init__(self, fmt: str = TERMINAL_FMT, datefmt: str = "%H:%M:%S") -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        # Computed once per record, by whichever handler formats it first, and
        # then reused: two handlers formatting the same record must not report
        # two different gaps.
        if not hasattr(record, "gap"):
            now = time.monotonic()
            record.gap = f"+{now - _CLOCK.previous:.2f}s"
            record.turn = f"T+{now - _CLOCK.turn:.1f}s"
            # Only INFO and above advance the clock, so the gap column means the
            # same thing in the file as in the terminal. Without this the mic
            # frame counter — a DEBUG line every few seconds, invisible on the
            # terminal — lands between "Sending out request" and "Response
            # received" and splits a 6.1s model call into two meaningless
            # fragments in the very file you opened to measure it.
            if record.levelno >= logging.INFO:
                _CLOCK.previous = now
        return super().format(record)


class _Clock:
    def __init__(self) -> None:
        self.previous = time.monotonic()
        self.turn = time.monotonic()


_CLOCK = _Clock()
TERMINAL = Elapsed(TERMINAL_FMT)
FILE = Elapsed(FILE_FMT, datefmt="%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------- turn ledger

@dataclass
class Turn:
    """One student utterance and everything it cost."""

    index: int
    at: float                       # seconds since the session opened
    heard: str
    first_word: float | None = None  # seconds until she started speaking
    model_calls: list[tuple[str, float]] = field(default_factory=list)
    spans: list[tuple[str, float]] = field(default_factory=list)

    @property
    def model_seconds(self) -> float:
        return sum(s for _, s in self.model_calls)


@dataclass
class SessionLog:
    """The per-session file handler plus the ledger printed when it closes."""

    session_id: str
    student_id: str
    path: Path
    handler: logging.Handler
    started: float = field(default_factory=time.monotonic)
    turns: list[Turn] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    # ---- ledger

    def heard(self, text: str) -> None:
        self.turns.append(
            Turn(index=len(self.turns) + 1, at=time.monotonic() - self.started,
                 heard=text)
        )

    def spoke(self, _text: str) -> None:
        if self.turns and self.turns[-1].first_word is None:
            self.turns[-1].first_word = (
                time.monotonic() - self.started - self.turns[-1].at
            )

    def model_call(self, model: str, seconds: float) -> None:
        if self.turns:
            self.turns[-1].model_calls.append((model, seconds))

    def span(self, name: str, seconds: float) -> None:
        if self.turns:
            self.turns[-1].spans.append((name, seconds))

    def count(self, what: str, n: int = 1) -> None:
        self.counts[what] = self.counts.get(what, 0) + n

    # ---- summary

    def summary(self) -> str:
        total = max(time.monotonic() - self.started, 0.001)
        rule = "─" * 74
        lines = [
            "",
            "═" * 74,
            f"  TURN TIMELINE  {self.session_id} · {self.student_id} · "
            f"{_mmss(total)} · {len(self.turns)} turn(s)",
            "═" * 74,
            "  turn        at   1st word      models   student said",
            rule,
        ]
        worst: tuple[float, Turn] | None = None
        for turn in self.turns:
            first = (
                f"{turn.first_word:6.1f}s" if turn.first_word is not None else "      —"
            )
            models = (
                f"{turn.model_seconds:6.1f}s x{len(turn.model_calls)}"
                if turn.model_calls
                else "         "
            )
            lines.append(
                f"  {turn.index:>4}  {_mmss(turn.at):>8}   {first}   {models}   "
                f'"{turn.heard[:40]}"'
            )
            for name, seconds in turn.spans:
                lines.append(f"  {'':>38}↳ {name} {seconds:.1f}s")
            cost = max([s for _, s in turn.spans] or [turn.model_seconds])
            if worst is None or cost > worst[0]:
                worst = (cost, turn)

        model_total = sum(t.model_seconds for t in self.turns)
        model_n = sum(len(t.model_calls) for t in self.turns)
        lines.append(rule)
        lines.append(
            f"  model time {model_total:7.1f}s in {model_n} call(s) — "
            f"{model_total / total * 100:.0f}% of the session"
        )
        lines.append(
            "  produced   " + ("   ".join(
                f"{name} {n}" for name, n in sorted(self.counts.items())
            ) if self.counts else "nothing reached the board")
        )
        if worst is not None and worst[0] > 0.5:
            lines.append(
                f"  worst wait {worst[0]:7.1f}s on turn {worst[1].index} "
                f'"{worst[1].heard[:36]}"'
            )
        lines.append("═" * 74)
        lines.append(f"  full log: {self.path}")
        return "\n".join(lines)

    def close(self) -> None:
        summary = self.summary()
        # Into the file raw, not through a formatter: the table has its own
        # alignment and a timestamp column per line would destroy it. Written
        # first so the file is self-contained even after the terminal scrolls.
        try:
            self.handler.stream.write(summary + "\n")
            self.handler.flush()
        except Exception:  # noqa: BLE001 - a closed file must not break shutdown
            pass
        for logger in _attached():
            logger.removeHandler(self.handler)
        self.handler.close()
        # Only now, so the terminal copy is not duplicated into the file.
        logging.getLogger("nityam").info("session closed%s", summary)


def _mmss(seconds: float) -> str:
    return f"{int(seconds) // 60:02d}:{seconds % 60:04.1f}"


# ------------------------------------------------------------ live accounting

class _Watcher(logging.Handler):
    """Attributes model-call time to the turn that paid for it.

    ADK logs "Sending out request, model: X" and "Response received from the
    model." around every generate_content, and that pair is the single largest
    cost in a turn — 3 to 5 seconds each, three of them deep. Rather than reach
    into ADK, watch its log: this handler produces no output, it only keeps the
    ledger. Non-invasive, and it cannot drift from what the log actually says
    because it *is* what the log says.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self._open: dict[str, tuple[str, float]] = {}

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - accounting must never break logging
            return
        session_id = getattr(record, "session", None) or SESSION.get("")
        if "Sending out request, model:" in message:
            model = message.split("model:", 1)[1].split(",", 1)[0].strip()
            self._open[session_id] = (model, time.monotonic())
        elif "Response received from the model" in message:
            started = self._open.pop(session_id, None)
            log = _OPEN.get(session_id)
            if started and log:
                log.model_call(started[0], time.monotonic() - started[1])
        elif "Trying to connect to live model" in message:
            self._open[session_id] = ("live", time.monotonic())


class _SessionFilter(logging.Filter):
    """One session's records only. This is what keeps concurrent students apart."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id

    def filter(self, record: logging.LogRecord) -> bool:
        return (getattr(record, "session", None) or SESSION.get("")) == self.session_id


# --------------------------------------------------------------------- setup

_OPEN: dict[str, SessionLog] = {}


def _attached() -> list[logging.Logger]:
    """Every logger a session file has to hang off.

    Root covers ours and ADK's (they propagate). uvicorn does not propagate —
    it configures its own handlers — so it needs naming explicitly or the
    connection open/close lines never reach the file.
    """
    return [logging.getLogger(name) for name in ("", "uvicorn", "uvicorn.error")]


def setup(level: int = logging.INFO) -> None:
    """Terminal at `level`, our own loggers at DEBUG so the files get everything.

    Root stays at INFO deliberately: `google_genai` and `websockets` log every
    frame at DEBUG, and a frame here is 20ms of base64 microphone audio. That
    is hundreds of megabytes per session and nothing you would ever read.
    """
    logging.basicConfig(level=level)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(TERMINAL)
        # Explicit, not inherited: propagation skips the ancestor logger's
        # level check, so a DEBUG record from `nityam` would reach a NOTSET
        # handler and print. The terminal must stay at `level`.
        handler.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.setFormatter(TERMINAL)

    logging.getLogger("nityam").setLevel(logging.DEBUG)

    root = logging.getLogger()
    if not any(isinstance(h, _Watcher) for h in root.handlers):
        root.addHandler(_Watcher())


def open_session(session_id: str, student_id: str, **header) -> SessionLog:
    """Start a log file for one connection. Call once, from the WS handler."""
    SESSION.set(session_id)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    path = LOG_DIR / f"{stamp}_{session_id}.log"

    _prune()

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(FILE)
    handler.addFilter(_SessionFilter(session_id))
    for logger in _attached():
        logger.addHandler(handler)

    session = SessionLog(session_id, student_id, path, handler)
    _OPEN[session_id] = session

    log = logging.getLogger("nityam")
    log.info("session log: %s", path)
    for key, value in header.items():
        log.debug("  %s: %s", key, value)
    return session


KEEP = int(os.getenv("NITYAM_LOG_KEEP", "60"))


def _prune() -> None:
    """Keep the newest KEEP files. A session file is a few tens of kilobytes and
    a demo day is a lot of reconnects; without this the directory grows forever
    and the one you want is buried."""
    try:
        existing = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for stale in existing[:-KEEP] if len(existing) > KEEP else []:
        try:
            stale.unlink()
        except OSError:
            pass


def close_session(session_id: str) -> None:
    session = _OPEN.pop(session_id, None)
    if session is not None:
        session.close()


def current() -> SessionLog | None:
    return _OPEN.get(SESSION.get(""))


# ------------------------------------------------------------------ call-site

def heard(text: str) -> None:
    """The student said or typed something. Restarts T+ and opens a turn."""
    _CLOCK.turn = time.monotonic()
    session = current()
    if session is not None:
        session.heard(text)


# The old name, kept because main.py's transcription branch reads better with
# it and because it is called where the text is not yet in hand.
def turn_started(text: str = "") -> None:
    heard(text)


def spoke(text: str) -> None:
    """She said something out loud — records time-to-first-word for this turn."""
    session = current()
    if session is not None:
        session.spoke(text)


def count(what: str, n: int = 1) -> None:
    session = current()
    if session is not None:
        session.count(what, n)


@contextmanager
def span(name: str):
    """Time a named stretch of work and attribute it to the current turn.

    Used around the whole brain consultation, which is the one thing on the
    critical path that the student experiences directly as silence.
    """
    started = time.monotonic()
    log = logging.getLogger("nityam.span")
    log.debug("▶ %s", name)
    try:
        yield
    finally:
        elapsed = time.monotonic() - started
        log.info("■ %s took %.2fs", name, elapsed)
        session = current()
        if session is not None:
            session.span(name, elapsed)
