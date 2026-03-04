# Plan Summary (from plan.drawio.xml)

This document summarizes the intent captured in `plan.drawio.xml` and explains what the project aims to build.

**High-level goal**
Build an Anki add-on that helps users learn from mixed content (topics, items, PDFs, videos) with a custom scheduling flow that balances priority and randomness, supports extraction of interesting content into new notes, and keeps the experience flexible and cross-platform.

**Key constraints**
- Must work on Android and other platforms as much as possible.
- Maximize the use of existing Anki capabilities instead of reinventing features.
- Preserve user freedom to read and explore content outside of the scheduler.

**Core concepts**
- `Topic`: a high-level learning unit, sometimes special (PDF or video based).
- `Item`: a regular card that is tested with right/wrong answers.
- `Extract`: a child note created from a piece of content, pointing back to its source.
- `Priority` and `Tag`: user-controlled signals that influence scheduling.

**User flow (Learn session)**
1. User clicks Learn.
2. Scheduler decides whether to show a topic or an item.
3. If a topic is shown, it can be a special topic (PDF/Video) or standard.
4. While reviewing a topic, the user can extract something interesting.
5. When extracting, the user selects priority and optionally a tag.
6. The extract is created and linked back to its source.
7. If an item is shown, the user answers and the scheduler continues.

**Scheduling and selection logic**
- Decide whether to show a topic or item.
- For the chosen type, decide whether to use priority or random selection.
- If priority is used, optionally filter by tag.
- If a filter yields no results, disable that filter and try the next one.
- Use due dates and additional sorting criteria where needed.
- Consider a weighted distribution model ("debt"-based) so tags/categories track target proportions without ever reaching zero probability.

**Scheduling UI ideas**
- Slider to balance `Topics` vs `Items`.
- Toggles for "Completely random" selection.
- Tag picker for targeting a topic area (e.g., Psychology, Health, Spiritual).
- Display tag distribution and other sorting criteria.
- Restart points for the sorting algorithm.

**Content capture ideas**
- Embed YouTube videos directly inside Anki cards.
- Snapshot text and store a URL, with a "copy to highlight" workflow.
- Bookmarking a page as a utility feature.

**PDF support**
- Extract text from PDFs and link extracts back to the topic.
- Potentially use `PyMuPDF` for extraction.

**Architecture sketch**
- Entities: `Card`, `Topic`, `Item`, `Done statistics`.

**Planned work items (tickets)**
- Create a simple initialization/settings dialog.
- Set up infrastructure.
- Implement PDF reader support.
- Epic 2: Cross-card linking and extraction workflow (Parent <-> Child).
- Epic 3: Custom weighted Tools -> Learn session (card picker).
- Epic 4: Per-card priority system (user controlled).

**Fixes and polish**
- Search plugin cleanup.
- Remove "shige"/noisy pieces.
- Fix image crop selection.
- Add automatic postpone.
- Support extracting text into a separate note.
- Study how prioritization affects scheduling outcomes.

**Open questions**
- How should PDFs be cycled and prioritized?
- Should there be a special "reading-only" topic type where completion does not matter?
- Do PDFs need special tag-based sorting?

