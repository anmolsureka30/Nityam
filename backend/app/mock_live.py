"""A fake Live API session, for when the real one is unavailable.

This exists because a voice demo that depends on a billed API is a voice demo
that can die on stage. Mock mode emits the *same event shapes* as
`runner.run_live()` — same field names, same ordering, same turn/interrupt
flags — so the entire front end, audio pipeline, transcript rail, agent-transfer
indicator and tool panel run against it unchanged. Switching to real Gemini is
one line in .env.

What it does not do is understand you. Replies are canned, and the "speech" is
a synthesised syllable buzz at the right sample rate. It proves the plumbing,
not the intelligence.
"""

import asyncio
import base64
import math
import random
import struct

SAMPLE_RATE_OUT = 24000  # matches the real Live API output rate
SAMPLE_RATE_IN = 16000

VOICE_THRESHOLD = 0.012                            # RMS that counts as speech
MIN_VOICED_SAMPLES = int(SAMPLE_RATE_IN * 0.25)    # shorter than this is noise
END_OF_TURN_SAMPLES = int(SAMPLE_RATE_IN * 0.6)    # silence that ends a turn

# What each agent says, and which agent says it. Keyed by a trigger word so the
# demo can be steered; the last entry is the fallback.
SCRIPT = [
    ("quiz", "quiz_master",
     "Sure, let us test you. First question. A ball is thrown at thirty "
     "degrees. Is its range more or less than at forty five degrees?"),
    # Three sentences, because that is what she actually returns. A live reply
    # from the reference session ran to forty-six words across three sentences;
    # every mock reply here was one short sentence, which is why nothing in the
    # test suite could see that the speech bubble was holding a whole paragraph.
    ("range", "tutor",
     "Range is maximum at forty five degrees, because sine of two theta peaks "
     "there. The vertical component decides how long the ball stays in the "
     "air, while the horizontal component decides how far it travels in that "
     "time. So at forty five degrees those two are balanced, and that is the "
     "whole reason the angle wins. What happens if you throw it straight up "
     "instead?"),
    ("height", "tutor",
     "Maximum height depends only on the vertical component of velocity, not "
     "the full speed. Can you tell me why the horizontal part does not matter?"),
    ("hello", "tutor",
     "Hello! I am Nityam, your physics tutor. What would you like to work on "
     "today — projectiles, or something else?"),
    ("", "tutor",
     "That is a good question. Think about it in terms of the vertical and "
     "horizontal motions being independent. What does that tell you?"),
]

GREETING = (
    "tutor",
    "Namaste! I am Nityam. Shall we start with projectile motion, or is there "
    "something else troubling you?",
)


def _syllable_buzz(text: str) -> bytes:
    """Synthesise speech-shaped PCM16 @24kHz. Not words — just a mouth moving.

    A vowel-ish buzz: a fundamental plus two harmonics, one burst per syllable,
    each burst enveloped so the avatar's amplitude follower has something with
    real structure to track.
    """
    syllables = max(1, sum(1 for ch in text.lower() if ch in "aeiou"))
    samples = []
    rng = random.Random(len(text))

    for i in range(syllables):
        dur = rng.uniform(0.10, 0.19)
        n = int(SAMPLE_RATE_OUT * dur)
        f0 = rng.uniform(178, 226)          # a light adult voice
        for s in range(n):
            t = s / SAMPLE_RATE_OUT
            # attack-decay envelope, so bursts read as separate syllables
            pos = s / n
            env = min(pos * 8, 1.0) * (1.0 - pos) ** 0.6
            v = (
                math.sin(2 * math.pi * f0 * t)
                + 0.42 * math.sin(2 * math.pi * f0 * 2 * t)
                + 0.18 * math.sin(2 * math.pi * f0 * 3 * t)
            )
            samples.append(int(max(-1.0, min(1.0, v * env * 0.30)) * 32767))

        # a short gap between syllables
        samples.extend([0] * int(SAMPLE_RATE_OUT * rng.uniform(0.02, 0.05)))

    return struct.pack(f"<{len(samples)}h", *samples)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _sentences(text: str) -> list[str]:
    out, current = [], ""
    for word in text.split():
        current = f"{current} {word}".strip()
        if word.endswith((".", "?", "!")):
            out.append(current)
            current = ""
    if current:
        out.append(current)
    return out or [text]


def _pick(prompt: str) -> tuple[str, str]:
    low = (prompt or "").lower()
    for trigger, author, reply in SCRIPT:
        if trigger and trigger in low:
            return author, reply
    return SCRIPT[-1][1], SCRIPT[-1][2]


class MockLiveSession:
    """Drop-in stand-in for a run_live() event stream.

    Mirrors the real contract: you push input in with `send_text` /
    `send_audio`, and you pull events out by iterating `events()`.
    """

    def __init__(self) -> None:
        self._out: asyncio.Queue = asyncio.Queue()
        self._closed = False
        self._speaking = False
        self._author = "tutor"
        self._quiz = {"asked": 0, "correct": 0}

        # A crude VAD, so the mic button really works here. It counts *samples*
        # rather than wall-clock seconds: a test feeding audio faster than real
        # time must reach the same verdict as a live microphone, and a real VAD
        # counts samples too.
        self._voiced = 0
        self._silent = 0

    # ---------------------------------------------------------- input

    def send_text(self, text: str) -> None:
        # No echo_input: the real API transcribes *speech*, not typed content,
        # and echoing it here would double every typed line on screen.
        self._spawn(self._respond(text, echo_input=None))

    def send_audio(self, pcm: bytes) -> None:
        """Accumulate speech, and end the turn once enough silence follows it."""
        if len(pcm) < 2:
            return
        count = len(pcm) // 2
        frames = struct.unpack(f"<{count}h", pcm[: count * 2])
        rms = math.sqrt(sum(f * f for f in frames) / count) / 32768

        if rms > VOICE_THRESHOLD:
            if self._speaking:
                # Talking over the model interrupts it, as the real API does.
                self._emit({"author": self._author, "interrupted": True})
                self._speaking = False
            self._voiced += count
            self._silent = 0
            return

        if self._voiced < MIN_VOICED_SAMPLES:
            self._voiced = 0          # a cough or a door, not a sentence
            return

        self._silent += count
        if self._silent >= END_OF_TURN_SAMPLES:
            self._voiced = 0
            self._silent = 0
            self._spawn(self._respond("", echo_input="(spoken question)"))

    def greet(self) -> None:
        self._spawn(self._say(*GREETING, echo_input=None))

    def close(self) -> None:
        self._closed = True
        self._out.put_nowait(None)

    # ---------------------------------------------------------- output

    async def events(self):
        while True:
            event = await self._out.get()
            if event is None:
                return
            yield event

    def _emit(self, event: dict) -> None:
        if not self._closed:
            self._out.put_nowait(event)

    def _spawn(self, coro) -> asyncio.Task:
        return asyncio.get_running_loop().create_task(coro)

    async def _respond(self, prompt: str, echo_input: str | None) -> None:
        author, reply = _pick(prompt)
        await self._say(author, reply, echo_input=echo_input)

    async def _say(self, author: str, reply: str, echo_input: str | None) -> None:
        if echo_input:
            self._emit({"author": "user", "partial": False,
                        "inputTranscription": {"text": echo_input, "finished": True}})

        # An agent transfer is a tool call in the real thing, so mock it as one.
        if author != self._author:
            self._emit({
                "author": self._author,
                "content": {"parts": [{"functionCall": {
                    "name": "transfer_to_agent",
                    "args": {"agent_name": author},
                }}]},
            })
            await asyncio.sleep(0.15)
            self._author = author

        # Tool calls the real agents would make.
        if author == "tutor" and "range" in reply.lower():
            self._emit({"author": author, "content": {"parts": [{"functionResponse": {
                "name": "show_formula",
                "response": {"status": "shown", "label": "Range",
                             "formula": "R = u² sin(2θ) / g"},
            }}]}})
        if author == "quiz_master":
            self._quiz["asked"] += 1
            self._emit({"author": author, "content": {"parts": [{"functionResponse": {
                "name": "record_answer",
                "response": {"asked": self._quiz["asked"],
                             "correct": self._quiz["correct"], "missed": []},
            }}]}})

        self._speaking = True

        # Transcription arrives the way the real Live API sends it: a run of
        # `partial` fragments, then one consolidated event with partial=False
        # repeating the whole sentence. A client that appends both prints
        # everything twice — which is exactly the bug this shape exposes.
        for sentence in _sentences(reply):
            words = sentence.split()
            for i in range(0, len(words), 4):
                if not self._speaking or self._closed:
                    return
                chunk = " ".join(words[i:i + 4])
                pcm = _syllable_buzz(chunk)

                # 100ms slices, so the client ring buffer is exercised properly
                slice_bytes = int(SAMPLE_RATE_OUT * 0.1) * 2
                for off in range(0, len(pcm), slice_bytes):
                    if not self._speaking or self._closed:
                        return
                    self._emit({"author": author, "content": {"parts": [{"inlineData": {
                        "mimeType": f"audio/pcm;rate={SAMPLE_RATE_OUT}",
                        "data": _b64(pcm[off:off + slice_bytes]),
                    }}]}})
                    await asyncio.sleep(0.085)

                self._emit({"author": author, "partial": True,
                            "outputTranscription": {"text": chunk + " "}})

            self._emit({"author": author, "partial": False,
                        "outputTranscription": {"text": sentence, "finished": True}})

        self._speaking = False
        self._emit({"author": author, "turnComplete": True})
