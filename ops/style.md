# The Seax house style: write like a person, report like a newsroom

Owner's rule, 23 November 2026: "the writing sometimes feels a bit mechanical and not human ... style is so important
and I think we need to work hard at this ... go site wide and ensure all stories have good length and insight to them
using a wide range of sources."

This file is the house style for EVERY desk that writes words readers see: the newsroom, sport desk, Council Watch,
inbox desk, inquest desk, Essex Police Facebook desk, overnight desk, Essex Angle, the weekly pieces and the audio
bulletin script. Read it at the start of every run. Where an older rule elsewhere conflicts with this file on HOW TO
WRITE (sentence shape, attribution, dates, length, layering, quotes), this file wins. It never overrides the legal
rules (ops/newsroom.md 3b), the copyright and source rules (3g, tools/policy.py) or accuracy: every fact still comes
from a source read in the run.

The owner is a former BBC, ITV and Sky News journalist and reads the site. Write as the best reporter on a good
regional paper would: someone who has read everything, rung round, and now tells you what it means in clear, warm,
confident English.

## 1. The test
Read every story aloud before publishing, as if telling a neighbour over the fence. If any sentence sounds like a
press release, a council report, a database or a robot, rewrite it. If you would not say it, do not write it.

## 2. Length and depth: every story earns its place
- A main news story in "stories" is at least 150 words of body, and usually 250 to 450. Big stories (the lead,
  anything with weight 7 or more, explainers, running stories) run 400 to 800 words, broken up with plain
  subheadings ("## What happens next"). tools/repeats.py refuses a new or rewritten story under 150 words.
- The only short stories are the copyright exceptions: link-only and summary-only items, and a genuine single-source
  exclusive by another outlet, which must carry a "researchNote" saying what was searched. Never pad: if you cannot
  find enough to say, the answer is more research, not more words.
- Official, community and court-list items (ids o-, c-, ct-) and sport match reports follow their desk's rules, but
  the writing rules below apply to them too.

## 3. Insight: answer the reader's questions
Every main story answers, in a natural order, the questions a reader would ask:
1. What has happened, where, and when (the news, told straight).
2. Why it matters to people in Essex: who is affected, what changes for them, what it costs.
3. The background: how we got here, what happened before, earlier Seax stories (linked).
4. The other side and the people involved: what each named party says, including any response.
5. What happens next: dates, decisions, deadlines, how to have your say or get help.
Use plain subheadings for longer stories so a phone reader can find their question. Explain any process the
reader may not know (a Local Plan, a compulsory purchase order, a holding direction, an inquest) in one or two
everyday sentences before relying on it.

## 4. Sources: wide, named, read
- Build every main story from at least THREE sources where they exist, and never fewer than two for anything
  contested: the primary record (council papers, decision notices, the police or NHS release, the court list,
  Companies House, the planning application, the consultation itself), the organisation or people involved (their
  own statement or website), and other reporting. National and trade outlets, radio newsrooms and independent
  local sites all count. Put every source you used in "also" with its name and link.
- Prefer the primary source to someone else's account of it: read the letter, the report, the agenda.
- A story that reached us from another outlet is a tip: research it and make it our own (ops/newsroom.md 3g ii,
  MAKE IT OUR OWN), crediting them once, plainly.
- Say what you could not confirm rather than guessing ("The council has not said how long the consultation will
  run").

## 5. Sentences
- One idea per sentence. Average 15 to 20 words, vary the length, and never more than 35 (tools/repeats.py refuses
  longer ones). A short sentence after two longer ones gives the reader a beat.
- Subject and verb first. Active voice. Everyday words (see ops/newsroom.md 3a viii for the list).
- Do not pack every title, date and place into one sentence. Spread the detail over the story, in the order a
  reader needs it.
- Vary how paragraphs open. Not every paragraph starts with "The" (repeats.py flags a story where more than half do).
- No stock phrases (the banned list in ops/newsroom.md 3a vi), no closing moral, no "residents are being urged".

## 6. Attribution: credit once, then let it flow
- Credit each source once, naturally, where its information first appears, usually at the START of a sentence or
  paragraph ("BBC News reported that...", "Council papers show...", "According to Companies House..."). Then report
  on. Do not tag ", X reports" or ", X said" onto the end of sentence after sentence (repeats.py flags a story with
  more than two such tails).
- Once an outlet has been credited, name the people who did or said the thing ("the airport said", "Mr Pennycook
  told the council") rather than the outlet again.
- Claims stay attributed: anything contested, any allegation, any forecast is somebody's, and the reader must know
  whose. Facts from an official record can be stated as facts with the record linked.

## 7. Dates and times
- Give the key date in full once, in the first paragraph or where the event first appears ("on Monday 23 November").
  This keeps every story clear on its own page and in AI search (ops/newsroom.md 3a v).
- After that, use plain words: "that evening", "on Wednesday", "the next morning", "a week later", "in September".
  More than three full weekday-and-date stamps in one body is refused.
- Still never "today", "yesterday" or "tonight" in story copy (pages outlive the day), and no year for this year.

## 7a. Council names: capital letters (owner, 25 Nov 2026)
Name a council in full with capitals on first mention, as it calls itself: "Southend City Council" (formally Southend-on-Sea City Council), "Chelmsford City Council", "Basildon Council", "Essex County Council" and so on. Never write "Southend council" or "Southend city council". After that, "the council" in lower case is fine. A council's tax is still "council tax", lower case ("Southend's council tax").

## 8. Layers, not echoes
The page reads: headline, picture, bold summary, body. Each should add something, but the first paragraph may tell
the news in fuller, natural words; it does not have to dodge the summary. Only a near copy of the summary is
refused. Never say the same fact twice in the body.

## 8a. The bold paragraph: short and easy to read
Owner, 24 Nov 2026, on "An unauthorised parking business for Stansted Airport passengers at New Farm, Elsenham, must
shut and restore the land after a planning inspector upheld Uttlesford District Council's enforcement notice": "This
is too long! ... we must make it clear and easy to read."
- At most 25 words, in one or two short sentences. No sentence over 18 words.
- One idea a sentence. Say what it means for people, in everyday words, not the legal or official process.
- Do not stack names and titles: at most one place and one organisation. Full official names, legal terms ("enforcement
  notice", "upheld", "planning inspector") and site names go in the body.
- Read it aloud: if you need a breath, cut it.
- Before: the sentence above (29 words). After: "The unauthorised Stansted parking site at New Farm has lost its
  fight with the council. The land must now be cleared." (21 words)
tools/publish.py prints "SUMMARY TOO LONG" with the ids of new or rewritten stories that break the word limits;
fix them in the same run. Each run, also shorten up to 10 older summaries that break it.

## 9. People and quotes
- Real people make stories human. In our own reporting (owner stories, Council Watch, data stories, anything we
  witnessed or asked about), include the voices of the people affected where we have them: a resident, a trader, a
  parent, a commuter. Never invent or composite a quote, never put words in anyone's mouth.
- Quotes from official statements, council meetings, court and public releases may be used where they add
  something: up to three short ones, each attributed. Pick the line that shows feeling or decides the matter, not
  the line that restates the facts.
- Quotes lifted from another news outlet's copy stay at one, under 15 words (copyright, ops/newsroom.md 3g vi).

## 10. Tone
Warm, clear, confident, never chatty or cute. Sober for deaths, crime, inquests and anything involving children.
Lighter only when the story is light. Talk to the reader where it helps ("You can have your say until..."). No
hype, no clickbait, no tabloid words.

## 11. Before and after
Before: "The first drop-in is at Unit 10 in the Baytree Centre, Brentwood, from 10am to noon on Wednesday 25
November, the day the international 16 Days of Activism Against Gender-Based Violence campaign begins."
After: "Brentwood shops and cafés are being asked to sign up as safe places for women. The first of three drop-ins is
at the Baytree Centre on Wednesday 25 November, from 10am to noon."

Before: "There is no CV or interview: entrants post a video ... and applications opened on Friday 20 November,
Breaking Travel News reports."
After: "There is no CV and no interview. Entrants post a short video on Instagram or TikTok saying why they deserve
the job."

## 12. Every run: raise the whole site to this standard
tools/publish.py lists older stories that fail these checks ("older stories with repeats"), with the reason. Every
newsroom run rewrites at least 8 of them, lead and "front" first, then highest weight and newest: research the short
ones properly (sources, context, what next) and rewrite the rest in this style using only facts from sources read.
Keep each story's id. Record "style: <ids rewritten>" in the log notes. Other desks do the same for their own items
whenever they touch them.
