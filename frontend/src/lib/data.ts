/* The demo lesson.
 *
 * Every value here is what the backend will eventually supply: `shruti`
 * produces the class recap and board captures, the tutor agent produces the
 * notebook, `artifact_generator` produces the simulation. Nothing in
 * components/ or features/ hardcodes content — it all comes from here, so
 * swapping in real endpoints is a change to this file and its callers only.
 */

import type {
  AtRiskStudent, Checkpoint, ClassRecap, Concept, IntensityOption, Notebook,
  ProjectileArtifact, SessionSummary, Student, Teacher, TeacherClassView,
} from "./types";

export const student: Student = {
  id: "stu_arjun",
  firstName: "Arjun",
  initial: "A",
  klass: "11-B",
};

export const teacher: Teacher = {
  id: "tea_deshpande",
  displayName: "R. Deshpande",
  klass: "Class 11-B · Physics",
};

export const daysToUnitTest = 9;

export const classRecap: ClassRecap = {
  subject: "Projectile motion",
  teacherName: "Mr. Deshpande",
  date: "Tue 25 Aug",
  startedAt: "10:35",
  endedAt: "11:20",
  captureCount: 7,
  openQuestion: "Why is 45° special? Think about it tonight.",
  openQuestionContext:
    "Mr. Deshpande derived the range formula, asked the class this, and then the bell went. He never answered it.",
  sources: [
    { id: "cap_board", at: "10:42", label: "Board 10:42" },
    { id: "cap_ncert", at: "", label: "NCERT XI · p.79" },
  ],
};

/* Mastery per concept. `issue` is written to be read by the student — the
   point is that it names the specific failure, not a score. */
export const concepts: Concept[] = [
  {
    id: "PHY-11-K2",
    name: "Maximum range",
    mastery: 68,
    examinable: true,
    issue: "Solves it at 45°, stalls at every other angle.",
  },
  {
    id: "PHY-11-K5",
    name: "Independence of axes",
    mastery: 41,
    examinable: true,
    issue: "Treats horizontal and vertical motion as one coupled problem.",
  },
  {
    id: "PHY-11-K3",
    name: "Time of flight",
    mastery: 83,
    examinable: true,
    issue: "Reliable, except when the launch height is not zero.",
  },
  {
    id: "PHY-11-K7",
    name: "Symmetry of complementary angles",
    mastery: 62,
    examinable: true,
    issue: "Has not yet connected 30° and 60° landing together.",
  },
];

export const readinessPct = 71;

export const readinessPattern =
  "You solve these correctly when the angle is 45°. You stop when it isn't.";

export const readinessRecommendation =
  "Two 20-minute sessions on independence of axes, before Friday's revision class.";

export const intensities: IntensityOption[] = [
  {
    id: "quick",
    label: "Quick",
    minutes: 8,
    promise: "One idea, one worked example. Enough to not be lost tomorrow.",
  },
  {
    id: "standard",
    label: "Standard",
    minutes: 20,
    promise:
      "We work it out together, with the simulation. You'll finish the thing the class didn't.",
    suggested: true,
  },
  {
    id: "deep",
    label: "Deep",
    minutes: 45,
    promise:
      "Range, symmetry and time of flight together — plus the two problems you got wrong last Thursday.",
  },
];

export const projectile: ProjectileArtifact = {
  id: "art_launch_angle",
  title: "Launch angle",
  eyebrow: "Interactive · launch angle",
  speed: 20,
  gravity: 9.8,
  angle: 30,
  angleMin: 15,
  angleMax: 75,
  ghosts: [30, 60],
};

/* The notebook the tutor writes as the session runs. Page 3 is where the
   student lands, because pages 1-2 were the warm-up. */
export const notebook: Notebook = {
  id: "nb_max_range",
  conceptId: "PHY-11-K2",
  pages: [
    {
      page: 3,
      eyebrow: `From your class · ${classRecap.teacherName} · 10:42`,
      blocks: [
        { kind: "heading", id: "b_h", text: "Why does 45° come out on top?" },
        {
          kind: "tutor_text",
          id: "b_intro",
          text:
            "Your teacher wrote this on the board and then the bell went. He didn't tell the class the answer — he said “think about it tonight.” So let's not look it up. Let's build it.",
        },
        {
          kind: "tutor_text",
          id: "b_setup",
          text:
            "A projectile leaves the ground at speed v and angle θ. Horizontally nothing slows it down; vertically, gravity brings it back. Two independent stories, one shared clock.",
          anchors: [
            { id: "a_v", span: "v", concept: "projectile.launch_speed" },
            { id: "a_th", span: "θ", concept: "projectile.launch_angle" },
          ],
        },
        {
          kind: "equation",
          id: "b_eq",
          tex: "R = v² sin(2θ) / g",
          caption: "Range, from today's board",
          anchors: [
            { id: "a_sin", span: "sin(2θ)", concept: "projectile.max_range" },
          ],
        },
        {
          kind: "tutor_text",
          id: "b_prompt",
          text:
            "Everything on the right is fixed by the throw except one thing. Find the one thing you control, and you've found the answer.",
        },
        { kind: "artifact", id: "b_art", artifactId: "art_launch_angle" },
      ],
    },
    {
      page: 4,
      eyebrow: "Next · symmetry of complementary angles",
      blocks: [
        {
          kind: "next",
          id: "b_next",
          label: "Next · symmetry of complementary angles",
          title: "Two throws, one landing spot",
          text:
            "Once you've seen why 45° wins, the next question almost asks itself: which other pairs of angles land in the same place, and why?",
        },
      ],
    },
  ],
};

/* Written by the student, in their own words, when they get there. Kept
   separate from the notebook because authorship matters: this block is the
   only one the tutor did not write. */
export const studentFinding = {
  label: `${student.firstName}'s finding · 21:14`,
  text:
    "Range is largest at 45°, because sin(2θ) is largest when 2θ = 90°. And 30° and 60° land in the same place because they add to 90° — they share the same sin(2θ).",
  footnote: "Saved to your notebook — in your words, not mine",
};

export const checkpoint: Checkpoint = {
  id: "cp_1",
  index: 1,
  total: 3,
  question: "In tonight's problem, what actually decides how far the ball lands?",
  hint: "Speed is fixed at 20 m/s. Pick one — I'd rather you guess than skip.",
  options: [
    {
      id: "wrong",
      letter: "A",
      text: "The launch speed",
      correct: false,
      tag: "Most picked",
      rebuttal:
        "Speed does change the range — you're not wrong about that. But tonight the speed is given to you and fixed at 20 m/s. Look again at what's left in the formula.",
    },
    { id: "right", letter: "B", text: "The angle it's thrown at", correct: true },
    {
      id: "wrong2",
      letter: "C",
      text: "The mass of the ball",
      correct: false,
      rebuttal:
        "Mass cancels out — it isn't anywhere in the range formula. Two balls of different mass thrown identically land together.",
    },
  ],
  footnote: "Nobody sees this but you.",
};

export const summary: SessionSummary = {
  endedAt: "21:26",
  minutes: 22,
  headline: "You finished what the class started.",
  moved: [
    { conceptName: "Maximum range", from: 68, to: 84 },
    { conceptName: "Symmetry of complementary angles", from: null, to: 62 },
  ],
  moment: studentFinding.text,
  stillOpen:
    "Independence of axes — 41%. It's under three of your four weak questions.",
  tomorrow: "Mr. Deshpande will ask about 45° again. You can answer it.",
};

/* ------------------------------------------------------------- teacher */

export const teacherClass: TeacherClassView = {
  topic: "Projectile motion",
  meta: "Tue 25 Aug · 10:35–11:20 · 42 students · 38 revised at home",
  updatedAt: "07:12",
  understanding: 64,
  belowHalf: 11,
  cohort: 42,
  sharedMisconception: "Axes treated as coupled",
  sharedMisconceptionCount: 24,
  medianRevisionMin: 19,
  concepts: [
    { id: "PHY-11-K2", name: "Maximum range", classMastery: 71, trend: 9, boardMinutes: 14 },
    { id: "PHY-11-K5", name: "Independence of axes", classMastery: 44, trend: -2, boardMinutes: 6 },
    { id: "PHY-11-K3", name: "Time of flight", classMastery: 79, trend: 4, boardMinutes: 11 },
    { id: "PHY-11-K7", name: "Symmetry of complementary angles", classMastery: 58, trend: 12, boardMinutes: 5 },
  ],
  distribution: [
    { band: "0-20", count: 2 },
    { band: "21-40", count: 9 },
    { band: "41-60", count: 13 },
    { band: "61-80", count: 12 },
    { band: "81-100", count: 6 },
  ],
  didNotOpen: ["Tanvi R.", "Imran S.", "Neha P.", "Karan V."],
  beforeTheBell:
    "Open with the cliff-edge projectile. Don't re-derive the formula — 34 of 42 already have it.",
};

export const atRisk: AtRiskStudent[] = [
  {
    id: "s1", name: "Imran S.", mastery: 22,
    misconception: "Applies vertical acceleration to horizontal motion",
    evidence: "Board 10:42 · 3 wrong at the same step",
    severity: "critical",
  },
  {
    id: "s2", name: "Tanvi R.", mastery: 28,
    misconception: "Reads sin(2θ) as 2·sin(θ)",
    evidence: "Checkpoint 2 · twice this week",
    severity: "critical",
  },
  {
    id: "s3", name: "Neha P.", mastery: 34,
    misconception: "Assumes maximum height and maximum range share an angle",
    evidence: "Session 24 Aug · abandoned mid-problem",
    severity: "watch",
  },
  {
    id: "s4", name: "Karan V.", mastery: 39,
    misconception: "Treats g as a velocity",
    evidence: "NCERT p.79 · highlighted, never asked",
    severity: "watch",
  },
  {
    id: "s5", name: "Rhea M.", mastery: 45,
    misconception: "Cannot separate the two axes under time pressure",
    evidence: "Timed set · correct untimed",
    severity: "watch",
  },
  {
    id: "s6", name: "Dev A.", mastery: 0,
    misconception: "No data — has not opened Nityam since 18 Aug",
    evidence: "Last session 7 days ago",
    severity: "inactive",
  },
];

export const teacherInsight = {
  observation:
    "24 students treat the axes as coupled, but 34 of 42 can recall the range formula. They have the equation and not the picture.",
  recalledFormula: "34/42",
  action:
    "Two minutes on the cliff-edge projectile at the start of tomorrow's class. Do not re-derive the formula.",
};

/* NCERT page the student can pull from. Real PDFs replace this; the shape is
   what matters — selectable regions that carry a concept. */
export const textbookPage = {
  book: "Physics Part I · Class XI",
  chapter: "Ch 4 · Motion in a plane · p.79",
  page: 79,
  pageCount: 246,
  sectionLabel: "4.10 Projectile motion",
  sectionTitle: "Maximum height and horizontal range",
  lead:
    "The motion of a projectile may be thought of as the result of two separate, simultaneously occurring components of motion.",
  selectable: [
    {
      id: "para",
      concept: "projectile.independence_of_axes",
      text:
        "One component is along a horizontal direction without any acceleration and the other along the vertical direction with constant acceleration due to the force of gravity.",
    },
    {
      id: "fig",
      concept: "projectile.trajectory",
      text: "Fig. 4.10 — the parabolic path of a projectile, with the range R marked on the horizontal axis.",
      figure: true,
    },
  ],
};
