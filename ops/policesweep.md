# Essex Police news sweep (17:00 daily)

HOUSE STYLE (owner, 23 Nov 2026): read ops/style.md at the start of every run and write every word readers see to it. It wins over older rules in this file on how to write, never over the legal, copyright or accuracy rules.

Owner's request, 26 Nov 2026: "we must search https://www.essex.police.uk/news/news-search/?ct=News every day at 1700 for stories we may have missed".

Why this desk exists: the hourly newsroom's Essex Police desk (ops/newsroom.md 2i) cannot read the force's website properly. Cloud fetches of essex.police.uk are refused or, for the News search page, served a stale copy (on 26 Nov 2026 the cloud copy topped out at items from about 14 Nov), and the RSS feed is frozen at June 2026 for automated readers. The newsroom logs for 26 Nov show "listingRead": false and "headlinesSeen": 0 on its runs, and some runs skipped the police desk altogether. In a real browser the page is current, newest first, with links and publish times. So this desk reads it once a day through a browser on the owner's computer and writes up whatever the site has missed.

Never use em dashes. Every rule in ops/newsroom.md applies (editorial rules, 3b crime and court legal safety, 3a vii HEADLINES, 3a viii PLAIN ENGLISH, the item format, district balance, NO REPEAT STORIES). Essex Police is an official source (3g ii): a full body is fine with no 100-word limit, written only from what the force's article states, in our own words, attributed ("Essex Police said"), at most one short quote under 15 words.

## 1. Open the page in a browser on the owner's computer
- Use the built-in browser (tools mcp__remote-devices__Claude_Browser__*, or mcp__Claude_Browser__*) if it is reachable; otherwise Claude in Chrome (mcp__claude-in-chrome__*). Load each browser's tools in one ToolSearch call. Open a NEW tab at https://www.essex.police.uk/news/news-search/?ct=News .
- NEVER WebFetch any essex.police.uk address for this desk: it returns the stale copy. If neither browser can be reached (the computer may be asleep), go to step 6.
- Read only. Never fill in forms, sign up, accept anything beyond the cookie banner (decline non-essential cookies if a banner blocks the page), or open other sites.

## 2. List the items
With the browser's javascript tool, wait about 2 seconds for the page to load, then collect each news item once: links whose href matches /news/essex/news/news/20YY/ (each appears twice; dedupe by href), with the item's own block text, which holds headline, one-line summary, category (for example "Court and Convicted") and "News Published: HH:MM DD/MM/YYYY" (UK time). Each page has 10 items, newest first. Go to the next page with the "Next page" link (its href looks like /link/8bcaef0bc9f1453e854962cd9c9469c7.aspx?ct=News&page=2) and keep going until you reach items published before 17:00 two days ago (a 48-hour window, so anything a previous sweep or newsroom missed is caught), at most 6 pages. Return results in small chunks; never return URLs with query strings in tool output if the tool blocks them.

## 3. Find what we have missed
For each item, check whether The Seax already has it: grep edition.json, data/archive.json and data/scheduled/ for the item's URL slug (the last path part, for example "leigh-seizure-cocaine"), and for its distinctive names, places and figures. Also check stories from the Essex Police Facebook desk (desk "owner"), which often has the same case from the force's Facebook page. If we have it but the article adds a genuinely new fact (a sentence, a charge, a found missing person), update that story only as ops/newsroom.md allows, set "updated", and never write a second story on the same case.

Editorial filter: use ops/policefb.md section 2 (what is worth a story and what to skip). Missing people and live appeals first, then serious incidents, charges, court results and sentences, operations and seizures, closure and dispersal orders, figures with a real news line. Skip generic awareness campaigns with no news line, recruitment, crime prevention tips and anything outside Essex. Items older than 48 hours are out unless still live (a missing person, an appeal) and never covered.

## 4. Read and write
Open each chosen article in the browser and read its full text (get_page_text). Write only what the article states. Item "url" is the article's own address (https://www.essex.police.uk/news/essex/news/news/...), source credit "Essex Police", "time" its publish time converted to UTC. Placement as ops/newsroom.md 2i iv ("Court and Convicted" in "courts" unless it weighs 5 or more under 3f; appeals, arrests, charges, crashes and operations in "official" with "kind": "police", "org": "Essex Police", or in "stories"). Full 3b rules every time: charged people are presumed innocent, report only what police state, never identify victims of sexual offences or children (other than a missing child the police are appealing to find), no speculation, and check the case is not already active in a way that makes new detail risky.

Pictures: follow the owner's image rules in ops/newsroom.md (his police blue-lights photos for police stories, maps, the Breaking News picture only for significant stories). If the article carries the force's own appeal picture (missing person, wanted, CCTV) and you are using Claude in Chrome, you may save it with the method in ops/policefb.md step 3, under all of that section's never-use rules; otherwise do not try, and say in the summary that the picture is for the Essex Police Facebook desk.

At most 6 new stories per run, most serious first. Leave the rest listed in the summary for the 17:35 newsroom.

## 5. Publish
Your push must be done by 17:30 UK time, before the 17:35 newsroom (the inbox desk also pushes around 17:20 to 17:33, so git pull --rebase if the push is refused). Write {"items": [...]} to /tmp/policesweep.json and run:
SEAX_NO_BRIEFING=1 python3 tools/publish.py --items /tmp/policesweep.json --desk owner
If it prints REPEATS, drop or fix the repeated items (or add --repeats-ok <id> only when you have checked the flag is wrong). If it prints "REPEAT STORY" (exit 6), drop it, or only for a genuine new development add "followUp" and "newAngle" as ops/newsroom.md 2c iii-b says, and rerun. Commit any picture files and data/portraits.json if publish.py leaves them uncommitted. Close every browser tab you opened.

## 6. If no browser can be reached
Do not WebFetch essex.police.uk. Instead run up to 4 WebSearch queries (mode "extended") such as "Essex Police news today" and "Essex Police court convicted <today's date>", and follow ops/newsroom.md 2i i to iii for anything in the last 24 hours that the site lacks, writing only what the result text states. Start the summary with "ALERT: browser not reachable, Essex Police news search read from search results only".

## 7. Summary
One short paragraph: which browser, pages read and the newest item's time, items in the 48-hour window, how many we already had, stories published (headlines), stories updated, items left for the newsroom and why, and PUSHED with the commit hash. Start with "ALERT:" if the browser could not be reached, the page would not load, or a push failed.
