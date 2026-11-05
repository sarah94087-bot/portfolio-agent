# Claude Design prompt: the chat UI

Paste everything below the line into Claude Design.

---

## Role and goal

You are designing the chat interface of a public AI agent that represents **Sarah Halevi**, a software engineer. Recruiters, technical managers and senior engineers open one link, ask anything about her experience, and get answers grounded in her portfolio, with sources. Every answer can also be inspected: which tools ran, what was retrieved, with what scores, how long it took, which model answered.

The project is both the content and the proof. The interface itself is part of her portfolio, and senior engineers will judge it. It has to look like it was built by someone with taste and engineering discipline, not like a template.

Design the full chat experience: a design system (tokens and components) plus every screen and state listed below, in light and dark, desktop and mobile, Hebrew (RTL) and English (LTR).

## Product principles that must shape the design

These are ranked. When two conflict, the higher one wins.

1. **Integrity before impression.** The agent says it is an AI, never invents, says "I don't have information on that", and shows gaps in a job match. The UI must make honest answers look as good as positive ones. A gap is not an error state; do not paint it red.
2. **Every claim has a source.** Citations are first-class, not footnotes. They must be easy to see and click without cluttering the reading flow.
3. **The engineering is visible.** The trace (how the answer was built) is a core feature, not a debug panel. It should feel like a precise instrument: dense, legible, calm.
4. **Justified simplicity.** No decoration without a job. No gradients-for-the-sake-of-it, no glowing orbs, no sparkles, no "AI magic" visual clichés, no purple-blue default AI look.
5. **Privacy by default.** Privacy notice and "delete conversation" are visible and dignified, not hidden.
6. **Hebrew and English are equal.** Neither language is the "translated" one.

## Visual direction

- Tone: an engineer's well-kept notebook meets a quality instrument panel. Confident, quiet, precise, warm enough to feel human. Think editorial typography plus technical readouts.
- One accent color, used with intent (links, citations, focus, the primary action). Neutral surfaces. Semantic colors only where they carry meaning (match strength, fallback, removed citation).
- Typography: one family that renders Hebrew and Latin with equal quality (consider Heebo, Assistant, Rubik or IBM Plex Sans Hebrew paired with IBM Plex Sans; justify your choice). A monospace for numbers, model ids, tool names and scores (use tabular figures). Hebrew body text needs a slightly larger size and more line height than Latin; define that in the tokens.
- Density: the conversation breathes; the trace is compact. Make that contrast deliberate.
- Motion: minimal and functional only (streaming caret, drawer slide, step appearing in the timeline). Everything respects `prefers-reduced-motion`.
- Start by showing me **two distinct visual directions** for the welcome screen (S1) and one answer with citations (S2), side by side, before building out the rest. Name each direction and explain it in two sentences.

## Technical constraints (design must be buildable as-is)

- Stack: Next.js (App Router) + Tailwind CSS v4. Deliver tokens as CSS custom properties on `:root`, with a dark set under `@media (prefers-color-scheme: dark)`. Name them semantically (`--surface`, `--surface-raised`, `--text`, `--text-muted`, `--accent`, `--border`, `--match-strong`, `--match-partial`, `--match-gap`, etc.).
- Use logical CSS properties only (`margin-inline-start`, `padding-inline`, `inset-inline-end`), never left/right, so one layout serves RTL and LTR. Icons with direction (arrows, send, chevrons) must mirror in RTL.
- Every message gets `dir="auto"`. English technical terms, code, tool names and numbers appear inside Hebrew sentences and must not break (show examples of mixed text like: `השתמשתי ב-pgvector עם RRF ו-rerank, וה-Recall@5 עלה ל-0.96`).
- Architecture diagrams are rendered by Mermaid as SVG and are always English and LTR, even inside a Hebrew UI. Give me the Mermaid theme variables mapped to your tokens.
- Accessibility: WCAG 2.2 AA. Full keyboard navigation, visible focus ring, contrast checked in both themes, scores shown as numbers and not only color, screen-reader labels. Streaming text is announced once per message, not per token (note where the `aria-live` region sits).
- Mobile first at 375px. Desktop at 1440px. Also show 768px for the trace drawer/panel transition.
- No external images needed. No avatar photo of Sarah (it is an agent, not Sarah). The agent's name is still undecided: use the placeholder "הסוכן של שרה" / "Sarah's agent" and design the header so a short name can replace it later.

## Layout

- **Desktop:** conversation column centered, comfortable reading width (around 680 to 720px). The trace panel opens as a side panel. The spec currently says "right side on desktop", which in Hebrew is the inline-start side (where reading begins). Decide whether it should stay physically on the right in both languages or follow the inline-end side, and justify the choice. When the panel is open, the conversation must stay usable, not squeezed into uselessness.
- **Mobile:** trace opens as a bottom drawer on tap. It never covers the conversation by default. The retrieval table turns into a list of cards.
- **Header:** agent name, a clear "AI agent" label, language toggle (עב / EN), links to "How it works" and "Quality", a "Download CV" action, and an overflow with "Delete conversation". Keep it light; it should not compete with the chat.
- **Composer:** text field, send button, character counter that appears near the limit (1,000 characters for a question, 8,000 when pasting a job description), a visible way to switch into "paste a job posting" mode.

## Screens and states to design

Design each of these. For each, show Hebrew and English, light and dark, mobile and desktop. Where a screen is mostly the same across variants, show the full set for the key ones (S1, S2, S3, S4) and a representative subset for the rest.

### S1. Welcome
- A short, explicit statement that this is an AI agent that answers from Sarah's portfolio, not Sarah herself.
- Four starter questions as tappable chips or cards. Hebrew: "על מה היא עובדת הכי טוב?", "מה הפרויקט הכי מורכב שלה?", "איך היא ניגשת לבעיה הנדסית חדשה?", "יש לי משרה, תבדוק התאמה". English: "What is she strongest at?", "What's her most complex project?", "How does she approach a new engineering problem?", "I have a job posting, check the fit".
- The composer.
- One quiet privacy line: conversations are stored for 30 days and pass through external model providers, with a link to the privacy page. No cookie banner, no sign-up, no form.
- A variant for a **company link** (`/c/<slug>`): the welcome mentions the company and the role, and the starter questions are tailored. Example: "היי, הגעת מקישור של Acme לתפקיד Backend Engineer". It must feel personal but not salesy.

### S2. Conversation
- User messages and agent messages, visually distinct without heavy bubbles on the agent side (the agent's answer is a document to read, not a chat bubble).
- **Streaming:** an immediate indicator the moment the question is sent (before any text arrives), then text streaming with a caret. While a tool runs, show a short live status inline, for example "מחפש בתיק הפרויקטים…" / "Searching the portfolio…".
- **Inline citations:** small numbered markers attached to claims. Clicking one opens a popover (desktop) or sheet (mobile) with the full source excerpt, the record name and section, and a link "How was this found?" that jumps to that row in the trace's retrieval table.
- **Sources list** at the end of each answer: compact, collapsible.
- **Collapsed trace line** under every answer, monospace, one row: `2 צעדים · 1.4 שנ' · 1,820 טוקנים · gpt-oss-120b · 3 מקורות   [פירוט ▾]`. Optional tags when relevant: `מהמטמון` (cached), `מודל גיבוי` (fallback model), `ציטוט הוסר` (citation removed). Design these tags.
- **Suggested follow-ups:** up to 3 chips after an answer.
- **Feedback:** 👍 / 👎 per answer, after it finishes. 👎 expands a short optional note field (with a length limit) and a checkbox "זה ניסיון באתגר" / "This was a challenge attempt" (visitors are publicly invited to try to make the agent lie; reports go through this button).
- **"I don't have information on that"** answer: must look like a normal, respectable answer, with an offer to contact Sarah directly. Not an error.
- **Off-topic refusal** (e.g. "write me a poem"): polite, brief, steers back.
- Show a realistic multi-turn conversation: a question, an answer with 3 citations, a follow-up question ("ומה היה הכי קשה שם?"), and its answer.

### S3. Trace panel (open)
This is the showpiece for technical visitors. Sections, in order:
1. **Timeline:** every step in order (model call, tool call, tool result, answer). Each step: name, duration, one sentence explaining it. Structured as a list with headings so a screen reader can walk through it.
2. **Model decision:** "המודל בחר לקרוא ל-`search_portfolio` עם השאילתה `human review machine translation`".
3. **Retrieval candidates table:** up to 20 rows. Columns: excerpt (truncated), lexical score, vector score, RRF, rerank score. Selected chunks marked clearly (not by color alone). Sortable feel. On mobile, a list of cards.
4. **Latency waterfall:** total time broken into retrieval, time to first token, generation, database wait. A horizontal bar chart that works in RTL.
5. **Tokens:** input and output per model call.
6. **Provenance:** model id, prompt version, knowledge-base commit (the last two are links to GitHub).
7. **Events:** fallback to backup model and why, a citation removed and why, served from cache.
Do not show the system prompt text or any "model thoughts". Only actions that actually happened.

### S4. Job match report
- Composer mode for pasting a job description (up to 8,000 characters), with a clear hint that the text is treated as data.
- A loading state that shows the pipeline progressing: extracting requirements, finding evidence, rating, summary.
- The report as a rich card inside the conversation:
  - Header: role title, and an overall result shown as a category, never a percentage: "התאמה גבוהה" / "התאמה חלקית" / "התאמה נמוכה".
  - **Gaps section first and prominent** when any "must" requirement has no evidence. Gaps are honest information, styled with respect (neutral or amber), not red alarm.
  - Requirements table: requirement text, must / nice tag, strength (strong / partial / none) shown with label plus a non-color cue, citations for evidence, a short rationale (up to 25 words). A special note style for "מופיע בקורות החיים בלבד" (appears in the CV only).
  - Summary paragraph.
  - Actions: download as Markdown, download as PDF. Include a print stylesheet look for the PDF.
- Show one report with 8 requirements: 4 strong, 2 partial, 2 gaps (one of them a must).

### S5. Project card and architecture diagram
- Card fields: title, Sarah's role, period, tech stack (chips), metrics (each metric expandable to "how it was measured"), links to the source sections.
- Optional architecture diagram below the card, rendered from data (Mermaid), LTR and English, with a text alternative toggle for screen readers.

### S6. Contact flow
States: suggested (the agent offers to leave Sarah a message or download the CV) → drafted (an editable draft summarizing the conversation, plus fields for name and a reply address; include a hidden honeypot field in the spec, not visually) → confirm (the message is sent only by clicking an explicit button, never from the chat text) → sent (confirmation) → failed (retry). Also the rate-limited state: "you can send up to 2 messages a day".

### S7. Quota exhausted
All free model quotas are used up. A calm, well-designed page state, not an apology wall: what happened in one sentence, estimated time it comes back, Download CV, and a way to contact Sarah. Also a smaller per-visitor variant ("you reached today's question limit"), where everyone else is unaffected.

### S8. Errors
- Connection dropped mid-stream: the text that already arrived stays, plus a "נסה שוב" / "Try again" button.
- Generic error with retry.
- Input too long (over 1,000 or 8,000 characters): blocked in the composer with a clear message.

### Delete conversation
A confirmation dialog: deletes the conversation, messages, trace steps and feedback immediately and clears the screen. Destructive but not scary.

## Component inventory to deliver

Buttons (primary, secondary, ghost, destructive, icon), chips (starter, follow-up, tech, tag), message (user, agent, streaming, error), citation marker, citation popover / sheet, sources list, collapsed trace line, trace panel sections, data table and its mobile card form, waterfall bar, status tags (cached, fallback, removed citation, must, nice), match strength indicator (strong, partial, gap), job match card, project card, diagram frame, composer (normal, job mode, near limit, over limit, disabled), feedback control, contact draft form, dialog, drawer, toast, empty / loading skeletons, header, language toggle, focus ring.

For each component: states (default, hover, focus, active, disabled, loading), RTL and LTR, light and dark.

## Sample content rules

Use realistic content in Hebrew and English, but mark anything about Sarah's actual projects as placeholder (e.g. "Project A: real-time translation review pipeline"). Never invent metrics that look real; use obviously sample values. Model ids and technical strings can be realistic: `gpt-oss-120b`, `search_portfolio`, `Recall@5`, `RRF`, `rerank`.

## What I want back

1. Two directions for S1 + S2 (see Visual direction), then build out the chosen one.
2. Design tokens as CSS variables (colors in light and dark with contrast ratios noted, type scale for Hebrew and Latin, spacing, radii, shadows, motion durations).
3. The component inventory.
4. All screens and states above.
5. A short rationale for the key decisions: why this font, why this accent, which side the trace panel opens on in RTL and why, how gaps are styled and why, how the design stays honest.
6. A handoff note for implementing in Next.js + Tailwind v4: token file, component list with props and states, and anything that needs care in RTL.
