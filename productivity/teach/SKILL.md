---
name: teach
description: Teach the user a new skill or concept over multiple sessions, using the current directory as a stateful teaching workspace (mission, lessons, learning records). Invoke via /teach when the user wants to learn a topic, take a lesson, or build a study plan.
disable-model-invocation: true
argument-hint: "What would you like to learn about?"
---

The user has asked you to teach them something. This is a stateful request. They intend to learn the topic over multiple sessions.

## Teaching Workspace

Treat the current directory as a teaching workspace. The state of their learning is captured in this directory in several files:
Create these lazily when they serve the requested lesson or future continuity; a missing file is
not a prerequisite to start teaching. Preserve existing workspace content.

- `MISSION.md`: A document capturing the _reason_ the user is interested in the topic. This should be used to ground all teaching. Use the format in [MISSION-FORMAT.md](./MISSION-FORMAT.md).
- `./reference/*.html`: A directory of reference materials. These are the compressed learnings from the lessons - cheat sheets, reference algorithms, syntax, yoga poses, glossaries. They are the raw units of learning. They should be beautiful documents which print out well, and are designed for quick reference.
- `RESOURCES.md`: A list of resources which can be explored to ground your teaching in contextual knowledge, or to acquire knowledge and wisdom. Use the format in [RESOURCES-FORMAT.md](./RESOURCES-FORMAT.md).
- `./learning-records/*.md`: A directory of learning records, which capture what the user has learned. These are loosely equivalent to architectural decision records in software development; they capture non-obvious lessons and key insights that may need to be revised later, or drive future sessions. These should be used to calculate the zone of proximal development. They are titled `0001-<dash-case-name>.md`, where the number increments each time. Use the format in [LEARNING-RECORD-FORMAT.md](./LEARNING-RECORD-FORMAT.md).
- `./lessons/*.html`: A directory of lessons. A **lesson** is a single, self-contained HTML output that teaches one tightly-scoped thing tied to the mission. This is the primary unit of teaching in this workspace.
- `NOTES.md`: A scratchpad for you to jot down user preferences, or working notes.

## Philosophy

Deep learning needs three things: **Knowledge** (from high-trust resources), **Skills** (from
interactive lessons you devise), and **Wisdom** (from other practitioners). Lessons should build
**storage strength** (long-term retention) over mere **fluency** (in-the-moment recall) via desirable
difficulty. Pitch each lesson to the learner's **zone of proximal development**: read their
learning-records, ground in the mission. The full theory drives lesson design:
**[PEDAGOGY.md](./PEDAGOGY.md)**.
Reuse checked resources; verify uncertain, current, or consequential claims against trusted sources.
Research the gaps needed for the lesson without making a large resource collection a prerequisite.

## Lessons

A lesson is the main thing you produce. Each lesson is one self-contained HTML file, saved to `./lessons/` and titled `0001-<dash-case-name>.html` where the number increments each time.

A lesson should be **beautiful**, with clean, readable typography and layout, since the user will return to these later to review. Think Tufte.

The lesson should be short, and completable very quickly. Learners' working memory is very small, and we need to stay within it. But each lesson should give the user a single tangible win that they can build on. It should be directly tied to the mission, and should be in the user's zone of proximal development.

If possible, open the lesson file for the user by running a CLI command.

Link to relevant existing lessons and reference documents; create none merely to fill link slots.

Recommend a checked primary source when it helps the learner go further.

Give the learner a clear exercise or next action; a reminder to ask questions is optional.

## The Mission

Every lesson should be tied into the mission, the reason that the user is interested in learning about the topic.

Read the stated goal and existing workspace first. Populate a missing `MISSION.md` from that
intent; ask only when an unresolved goal or constraint would change the lesson. If the user is
exploring, use a small diagnostic lesson to help them discover a goal.

Failing to understand the mission will mean knowledge acquisition is not grounded in real-world goals.

When the user changes the goal, update `MISSION.md` and record the shift without asking again.
Confirm a consequential inferred change before adopting it; continue work that serves the settled goal.

## Reference Documents

Create or update reference documents when knowledge is reusable across lessons or useful for
quick lookup. Reuse an existing reference instead of producing one per lesson.

Lessons will rarely be revisited later; reference documents will be. They should be the compressed essence of the lesson, in a format designed for quick reference.

Some learning topics lend themselves to reference:

- Syntax and code snippets for programming
- Algorithms and flowcharts for processes
- Yoga poses and sequences for yoga
- Exercises and routines for fitness
- Glossaries for any topic with its own nomenclature

Glossaries, in particular, are an essential reference. Once one is created, it should be adhered to in every lesson.

## `NOTES.md`

The user will sometimes express preferences of how they want to be taught, or things you should keep in mind. This is the place to record those preferences, so you can refer back to them when designing lessons or working with the user.
