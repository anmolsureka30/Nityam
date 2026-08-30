# Stop Personalising the Content. Start Personalising the Teaching.

### Forty years of learning science says the hard part isn't picking the right question. It's picking the right *move* — and an Indian classroom is where that gap costs the most.

---

Sit at the back of a Class 5 maths lesson in a government school in Nagpur. Sixty-odd children, one teacher, one blackboard, forty minutes.

Now look at what those children can actually do. [ASER 2024](https://www.ideasforindia.in/topics/human-development/aser-2024-more-than-a-post-pandemic-recovery-in-learning), which surveyed 649,491 children across 605 rural districts, found about 45% of Class 5 students can read a Class 2 text, and roughly a third of Class 3 students can do subtraction. These are the best numbers ASER has recorded in two decades — the recovery is real — and they still mean the teacher in that room is teaching to a median student who does not exist. Some kids are three grade levels behind. Two are bored out of their minds.

She knows this. She isn't a bad teacher. She has sixty-two children and forty minutes.

This is the problem every "personalised learning" product claims to solve, and almost all of them solve the easy half.

## The easy half, and the myth that made it feel like enough

The easy half is *what*: which question next, at which difficulty, in which order. Adaptive difficulty. Skill trees. A dashboard that goes green.

That half matters, and India has the world's strongest evidence for it. Pratham's **Teaching at the Right Level** — group children by what they can actually do rather than which grade they're enrolled in — has been through six randomised evaluations across seven states, [producing gains of 0.15 to 0.70 standard deviations](https://www.nber.org/papers/w22746), among the largest effects ever rigorously measured in education. Meeting a child where they are isn't a nice-to-have.

But somewhere along the way "personalisation" picked up a second meaning, and this one is junk: the idea that each child has a *channel* — visual, auditory, kinesthetic — and learns better when you deliver through it. It's the most durable neuromyth in education. Pashler, McDaniel, Rohrer and Bjork went looking for evidence in a [now-famous review](https://journals.sagepub.com/doi/full/10.1111/j.1539-6053.2009.01038.x) and found that the studies testing the claim properly mostly contradicted it. Their conclusion was blunt: there is no adequate evidence base for putting learning-styles assessment into practice.

So when I say *multimodal*, I want to be precise about what I don't mean. I don't mean profiling a kid as a visual learner and shipping them more diagrams. I mean two other things, and both are load-bearing.

## One: some ideas only exist in more than one channel

You cannot teach projectile motion in prose. Richard Mayer's [cognitive theory of multimedia learning](https://www.digitallearninginstitute.com/blog/mayers-principles-multimedia-learning) rests on working memory having separate visual and auditory channels, and the *modality principle* falls straight out: people learn better from a diagram with spoken narration than from the same diagram with the words printed beside it. Not because some students are auditory — because printed words and pictures compete for one channel, and spoken words don't.

The medium isn't a preference to be matched. It's a property of the idea, and getting it wrong burns capacity that should have gone into thinking.

## Two: it's how the tutor *perceives* the student

This is the one nobody builds for, and it matters more.

A good tutor is not primarily an information source. They're a sensor. They watch your pen stop. They hear the pause before "…yes?" They see you point at line three of the derivation instead of line four. The field that studies this — [multimodal learning analytics](https://ccl.northwestern.edu/2016/Worsley.Abrahamson.Blikstein.Grover.Schneider.Tissenbarum.ICLS2016.pdf) — keeps finding that gesture, gaze, speech prosody and drawing carry information about understanding that correct/incorrect logs simply do not contain.

Now put that in an Indian classroom, where it stops being an interesting research finding and becomes the whole ballgame. The answer arrives in Hinglish. Or in Marathi with the technical nouns in English, because that's how the textbook is written and how NEP 2020's mother-tongue-first policy actually plays out in a real room. Half the reasoning is spoken; the other half is a diagram scratched in a notebook margin that nobody will ever type. A system that only ingests typed English hasn't lost a feature. It has thrown away most of the signal and most of the students.

## The move, not the material

Here's why the sensing matters so much: almost every good technique is *state-dependent*. Its correctness depends entirely on where the learner is at that instant.

Worked examples are the fastest way to teach a novice a procedure — and the moment that learner gains some competence, the same examples start *hurting* them. That's the [expertise reversal effect](https://www.ollielovell.com/johnsweller6/): the right move flips based on a state you can only know by watching. Manu Kapur's [productive failure](https://boldscience.org/wp-content/uploads/2025/04/Productive-Failure.pdf) says let students flail at a problem *before* you teach the concept — but only if they know enough to generate interesting wrong answers. Michelene Chi's [ICAP framework](https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-05/itow-applying-the-icap-framework-to-improve-classroom-learning-chi-boucher.pdf) ranks engagement — interactive > constructive > active > passive — which is the empirical bones under why Socratic questioning works. But a Socratic question aimed at a student who is genuinely lost isn't Socratic. It's cruel.

Kurt VanLehn [put a number on the granularity](https://www.tandfonline.com/doi/abs/10.1080/00461520.2011.611369). Human tutoring: d = 0.79. Step-based computer tutoring, engaging with each step of your reasoning: d = 0.76 — essentially the same. Answer-based systems, which only know whether you got it right: far behind.

The gap between a great tutor and a mediocre one isn't the content. It's choosing, second by second, between *hint*, *ask*, *show*, *let them struggle*, and *stop and go back three weeks*. That's what "treat a student the way they want to be treated" should actually mean. Not their stated channel preference — the move their current state calls for.

## Which is exactly where AI tutors go wrong

We now have evidence on both sides of this, and the split is instructive.

Bastani and colleagues ran nearly a thousand Turkish high-schoolers through GPT-4 maths practice and [published it in PNAS](https://www.pnas.org/doi/10.1073/pnas.2422633122). Students with unrestricted GPT-4 did great during practice — then scored **17% worse than students who never had AI at all** once it was taken away. A crutch. The guardrailed version, giving teacher-designed hints instead of answers, largely erased the harm.

The good news is the same finding wearing a different hat. Harvard's [PS2 Pal](https://www.nature.com/articles/s41598-025-97652-6) beat in-class active learning in an RCT — and was instructed to give away exactly one step at a time. The [World Bank's Nigeria trial](https://voxdev.org/topic/education/how-ai-tutors-improved-learning-nigeria) got 0.31 SD in six weeks at $48 a student, with prompts written to force reasoning. Stanford's [Tutor CoPilot](https://arxiv.org/pdf/2410.03017) lifted mastery most for the *weakest* tutors, and across 350,000 messages the mechanism was visible: more probing questions, less generic praise.

One conclusion, four studies: the difference between an AI tutor that teaches and one that quietly deskills a child is not model quality. It's pedagogical restraint. Each of these works because it was stopped from doing the thing language models most want to do, which is answer.

## And the part that has to come next: memory you can audit

A tutor's real advantage over any single conversation is the two hundred hours before it. They remember that you fake confidence when you're lost. That your sign errors are fluency, not concept. That the thing you never understood was fractions, in Class 4.

Those signals are detectable — Ryan Baker's group can identify [wheel-spinning](https://learninganalytics.upenn.edu/ryanbaker/210-Article%20Text-1526-1-18-20180624_V7.pdf), a student grinding a skill they'll never get unaided, and separate it from productive persistence. The question is what a system does with them.

Here's what worries me about this generation of "AI that remembers you": a language model will confidently tell you a child is weak at trigonometry on the basis of nothing. Vibes-based memory about a real student, accumulating unchecked across a school year, is worse than no memory — because a teacher will believe it.

So the bar has to be higher. If a system claims *she confuses velocity with acceleration*, it should be able to point at the moment: Tuesday, minute nineteen, the sentence she actually said. Every belief citable back to the evidence that produced it. Which buys a second thing worth as much as the first — a memory made of citations is one a teacher, a parent, or the student herself can open up and *correct*.

## What it adds up to

Not a chatbot with a syllabus bolted on. Something closer to three commitments:

**Perceive across modes** — voice, a shared board the tutor writes on and the student draws on, the pointing and the pauses — because that's where the diagnostic signal lives, and because the answer is spoken in three languages and drawn in the margin.

**Choose the move, not just the material** — worked example or productive struggle, hint or question, forward or three weeks back — with the restraint every successful trial above had hard-coded in.

**Remember with receipts**, so a year of accumulated belief about a child is something a human can inspect rather than something a model asserts.

Bloom's two-sigma result [never really replicated at two sigma](https://www.educationnext.org/two-sigma-tutoring-separating-science-fiction-from-science-fact/); the honest meta-analytic number for tutoring is nearer 0.4. Fine. I'll take 0.4 for sixty-two children instead of two.

That's the ambition, really. Not replacing the teacher in that Nagpur classroom. Giving every child in it the front row.

---

*If you work in this space — learning science, multimodal systems, Indian classrooms — I'd genuinely like to hear where you think this is wrong.*
