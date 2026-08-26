/* The tutor's replies, scripted.
 *
 * THIS IS THE SEAM. Everything here is replaced by sub_modules_examples/adk: the same
 * inputs (an utterance, or a ContextPacket from the canvas) go to a live agent
 * over a WebSocket, and the same TutorState comes back out — mood from the
 * avatar rig, caption from the Live API's output transcription, agent from
 * `event.author`.
 *
 * Keeping it behind one module means the session screen never learns whether
 * the tutor is real, so swapping it in touches nothing else.
 */

import type { ContextPacket, TutorState } from "./types";

export const opening: TutorState = {
  agent: "tutor",
  mood: "idle",
  caption:
    "Mr. Deshpande asked why 45° is special and then the bell went. Let's not look it up — drag the angle and watch where it lands furthest.",
};

/** Reply to a gesture on the page. The concept the anchor carries is what
 *  makes this specific rather than generic. */
export function replyToMark(packet: ContextPacket): TutorState {
  const top = packet.resolved[0];

  if (!top) {
    return {
      agent: "tutor",
      mood: "thinking",
      caption:
        "I can see you marked something, but not clearly enough to be sure what. Circle it a bit tighter and I'll pick it up.",
    };
  }

  const byConcept: Record<string, string> = {
    "projectile.launch_speed":
      "That's the launch speed. Tonight it's fixed at 20 m/s — given to you, not chosen by you. So it can't be the thing that decides the answer.",
    "projectile.launch_angle":
      "That's the angle — the one thing in the whole formula you control. Hold that thought and drag the slider.",
    "projectile.max_range":
      "sin(2θ) is the whole story. It's largest when 2θ = 90°, and that happens at exactly one angle. Can you say which?",
  };

  const caption =
    (top.concept && byConcept[top.concept]) ??
    `You marked “${top.text}”. Tell me what you think it does and I'll tell you if you're right.`;

  return { agent: "tutor", mood: "speaking", caption };
}

export function replyToPull(label: string): TutorState {
  return {
    agent: "tutor",
    mood: "speaking",
    caption: `I've put ${label.toLowerCase()} in your notebook. Notice it says the two motions are separate — that's the same idea we're using here, in the textbook's words.`,
  };
}

export function replyToText(text: string): TutorState {
  const low = text.toLowerCase();

  if (low.includes("quiz") || low.includes("test me")) {
    return {
      agent: "quiz_master",
      mood: "speaking",
      caption: "Right, let's test you. First question — at what angle is the range largest, and why?",
    };
  }
  if (low.includes("45")) {
    return {
      agent: "tutor",
      mood: "pleased",
      caption:
        "Yes — 45°, because sin(2θ) peaks when 2θ is 90°. Now try 30° and 60° and tell me what you notice.",
    };
  }
  if (low.includes("why") || low.includes("kyu") || low.includes("kyun")) {
    return {
      agent: "tutor",
      mood: "speaking",
      caption:
        "Good question to ask. Look at the formula: everything is fixed except the angle. Drag it and let the picture answer you.",
    };
  }
  return {
    agent: "tutor",
    mood: "speaking",
    caption: "Got it. Try the slider first — I'd rather you saw it happen than took my word for it.",
  };
}

/** Once the student has been either side of the maximum and come back to it,
 *  they have found the answer themselves. That deserves a different tone. */
export const foundIt: TutorState = {
  agent: "tutor",
  mood: "pleased",
  caption:
    "There it is — that's the furthest it goes, and you found it yourself. Now, why that angle and not a steeper one? Say it in your own words.",
};

export const afterCheckpointRight: TutorState = {
  agent: "tutor",
  mood: "pleased",
  caption:
    "Exactly. The angle is the only thing you control, so the angle is what decides it. I've saved that in your notebook, in your words.",
  masteryNote: "Maximum range · 68 → 84",
};

export const afterCheckpointWrong: TutorState = {
  agent: "tutor",
  mood: "speaking",
  caption:
    "Not quite, and it's worth knowing why. Speed does matter in general — but tonight it's fixed. Look at what's left.",
};
