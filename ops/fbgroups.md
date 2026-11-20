# Facebook groups desk

The Seax Page is a member of about 150 Essex Facebook groups. Meta has no API for posting into groups, so the desk posts through the owner's Chrome (Claude in Chrome), logged in to Facebook and acting as The Seax Page. It runs as a scheduled task five times a day (see "Automated runs"). The one-tap queue at theseax.com/groups/ (groups/index.html) shows the same matching for anyone posting by hand.

Owner's instructions (20 Nov 2026): post Seax stories into the relevant Essex groups automatically, wherever it is good to do so, optimising for group rules, time-sensitive stories and people's genuine information needs; join other relevant groups too. Posts go out as The Seax Page only, never the owner's personal profile, and never into groups run by Essex Live.

## Files
- data/fb-groups.json: the groups (members, rules, status, limits, owner, approval behaviour). The queue page reads it live.
- data/fb-group-log.json: every group post and join. "posts": {g: group key, s: story id, t: epoch ms, h: headline, result: live | pending | declined | removed}. "paused": true stops all posting (see Stop rules).
- groups/index.html: the queue. Matches stories to groups, varies the wording per group and tags each link ?ref=fbg-<group key> so GoatCounter shows which groups send readers.

## Group fields
- status: "on" (ready), "caution" (strict rules, low limit), "hold" (cannot post yet, e.g. no post box for the Page, join pending, account too new), "off" (never post: Essex Live, rules ban news links or Pages, auto-declines, dead).
- kind: town and crime groups need the story's place or headline to contain one of the "match" words; county groups take only the lead and top two front-page stories; politics takes council, planning and politics stories; events groups take What's On stories.
- perWeek: most posts in any seven days. onlyTags / avoidTags: story tags allowed or barred. days: weekdays the group allows (0 = Sunday). approval: "instant", "admin approval" or "auto-declined", recorded as posts are made. owner: the "Group by" banner, when there is one.

## Hard limits
- At most 12 group posts a day across all groups, at most 3 in any one run, at least 8 minutes between posts.
- At most 3 groups per story, at most one county-wide group per story.
- One post per group per day, at least 20 hours apart; never the same story twice in a group; never more than the group's perWeek.
- Never identical wording in two groups. Write each post fresh from the story: plain English, the useful fact first, no hype, no hashtags, no emoji, no "click here". End with the tagged link.
- Every fact in a post must be in the story itself. Never add a quote, a reason or a claim ("X says it shows...") the story does not carry.
- The owner's computer is a Mac: to clear a composer use cmd+a then Backspace (ctrl+a does nothing). Facebook keeps unsent drafts and restores them when the composer reopens, so before typing check the composer is empty; if it is not, clear it first. Read the whole draft in a screenshot before pressing Post.
- Every post must show the story's real picture as the link preview. If the preview does not load or shows no picture, close the composer without posting and skip that post.

## Crime checker push (owner, 20 Nov 2026: "the top story could go everywhere, saying you can select your neighbourhood"; scaled back at 17:41: "I don't want to push it as we've just launched; select those that will push it through no problems and won't be held")
Until the end of Sunday 22 November, the story "essex-recorded-crime-september-2026-police-data" may also go to groups beyond the usual 3, but ONLY groups whose "approval" is "instant" in data/fb-groups.json (posts from The Seax have gone live there straight away) and that are town or crime groups for an area the story covers. Never to groups with approval "admin approval", "auto-declined" or unknown (blank), never to "caution" groups, never to events or politics groups. Every other hard limit still applies (12 a day, 3 a run, 8 minutes apart, one post per group per day and 20 hours apart, perWeek), and public safety items still go first. If any post in this push is declined, removed or held, stop the push at once and report it.
- At the time of writing that means: Laindon and Basildon (196202630394637), Our Thurrock Community (1601081196881282), Little Thurrock Community Forum (1488274811502316, but not on the same day as Our Thurrock), Harlow Community (1236677473201839). If another town group's approval becomes "instant" during the weekend (a Seax post there went live at once), it may join.
- Make each post local: lead with that area's own figures from data/crime/essex-2026-09.json (the same numbers the story's crime checker shows), September 2026 against September 2025, using the neighbourhood that matches the group (Basildon; Chafford Hundred and Grays for Thurrock groups; Harlow's neighbourhood by name). Say plainly what rose and what fell. Never "soaring", "crime wave" or similar.
- Then one line on the checker, e.g. "You can look up any of Essex's 56 police neighbourhoods, crime by crime, with our new crime checker." End with the tagged link plus "#check" so it opens at the checker. Write every post fresh.

## What to post (in this order)
1. Public safety and disruption happening now or today: road closures and crashes (say if reopened), police appeals for witnesses, missing people (only while still missing: check the story is still on theseax.com and search for a "found" update first; never post a missing-person appeal more than 12 hours old without that check), fires, water or power cuts, school closures, weather warnings.
2. Time-bound information people can act on: events this weekend, consultations closing soon, service changes, bin and transport changes, health services (NHS Essex), council decisions affecting a town.
3. Strong local interest: a town's own news, Southend United and Colchester United match previews on match days, results the morning after.
- A story must still be live on theseax.com (not in tools/takedown.txt) and be under 12 hours old (under 6 hours for safety and disruption items, which go first). Stories from the previous day only if still current (e.g. a road still closed).
- Groups that hold posts for admin approval get time-sensitive items only in the 07:41 or 09:41 run, so approval can land in time (a match preview posted at 11:15 is no use if approved after kick-off).
- Never post the Brentwood School abuse review story ("brentwood-school-safeguarding-review-british-fencing-own-review") into groups (owner's site lead, sensitive).
- Never post: court stories (Court tag), anything about a person charged but not yet convicted, inquests, stories involving children's welfare, anything the legal gate holds, sponsored or deals content, and the same story into overlapping groups of one town in one day (rotate them).
- Match the group: town and crime groups only get stories from their own area; events groups only events; the politics group only council, planning and politics; county groups only the day's biggest Essex story.

## Automated runs
Scheduled task "Seax Facebook groups desk", every day at 07:41, 09:41, 12:41, 17:41 and 18:41 UK time (clear of the Essex Police Facebook desk, which uses Chrome at :05 past 8, 12, 16 and 20), needs the owner's computer awake with Chrome open. Each run:
1. Get the repo (seaxbot/theseax) and read this file, data/fb-groups.json and data/fb-group-log.json. If "paused" is true, stop and report why.
2. In Chrome, open facebook.com/notifications. For each "An admin declined your post" or "removed your post": open it, read the reason, mark the post's result, and set that group to "off" with the reason in "note" (one decline is enough). Mark pending posts that have since appeared as "live". A group that holds posts and leaves one pending for over 48 hours drops to perWeek 1.
3. Read edition.json from the freshly pulled repo (the shell cannot reach theseax.com; Chrome can, at theseax.com/groups/) and choose up to 3 posts by the rules above, counting today's posts in the log against the daily 12.
4. For each: open the group, check the top-left of the composer says "The Seax" (if it shows a personal name, stop the run), write the post, wait for the picture preview, press Post. Note whether it went live or "submitted to group admins for approval". Log it at once.
5. Commit data/fb-group-log.json and data/fb-groups.json changes with a short message and push.
6. Report in a few lines: what was posted where, any declines, anything paused.

## Joining groups
- At most 2 new groups a week, in the 12:41 run, only to cover a town with no active community group (as of 20 Nov 2026: Brightlingsea, Wivenhoe, Manningtree, Frinton and Walton, Thaxted, Ongar, Chigwell and Buckhurst Hill, South Woodham Ferrers, Benfleet, Leigh-on-Sea, Shoeburyness, Grays town centre, Tilbury, Stanford-le-Hope, Ingatestone, Writtle, Danbury).
- Only real community groups for that town, ideally over 3,000 members and active (posts most days). Check the "Group by" banner (never Essex Live; another news outlet is fine, note it as owner) and the rules (skip groups that ban links, news, promotion or Pages).
- Never answer join questions with anything untrue. If a group asks questions the Page cannot honestly answer (e.g. "do you live in X?"), skip it.
- Add each joined group to data/fb-groups.json with status "on", perWeek 2, and record the join in the log. Do not post in a group on the day it was joined.

## Stop rules
Set "paused": true in data/fb-group-log.json with the reason, push, stop the run, and report, if Facebook shows any of: a warning or restriction on the Page or the account, "you're temporarily blocked", a security check or CAPTCHA, a login screen, or more than 2 declines in one day. Only the owner unpauses. Never attempt a CAPTCHA or a login.

## Upkeep
- Before adding a group, read its "Group by" banner and rules.
- Re-check "hold" groups with no post box once a month.
- Re-audit all groups every few months.
