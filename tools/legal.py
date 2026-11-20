#!/usr/bin/env python3
"""Legal gate for crime, court and inquest stories (owner's go-ahead, 20 Nov 2026).

The site publishes with nobody reading the copy first, so the most likely automated mistakes in the riskiest stories
are checked by rule before anything goes live. tools/publish.py calls check() for every desk: a NEW or REWRITTEN
story that fails is HELD BACK (left out of this edition, the rest publishes) and the reason is printed so the desk
can fix it and send it again. Stories already live and unchanged are never removed, only reported.

This is a safety net for obvious errors. It is not legal advice and does not replace the rules in ops/newsroom.md 3b.

Rules (each returns a plain-English reason):
  1 SOURCE      a crime, court or inquest story must come from an official source or have a body written from a
                report that was read; a one-line summary of somebody else's crime report is not enough
  2 GUILT       words that state guilt (killer, murderer, rapist, thief, fraudster and the like) need a conviction
                or an admission in the same story
  3 CHILDREN    nobody under 18 is named in a crime or court story unless an official source named them (a missing
                person appeal, for example); never in an inquest story
  4 ACTIVE CASE someone charged or on trial but not convicted: no previous convictions, criminal record or
                "known to police" background, which could prejudice a trial
  5 ANONYMITY   a sexual offence story must not carry details that could identify the complainant (their
                relationship to the accused, their school, workplace or street)
"""
import hashlib, json, re

SECTIONS = ("stories", "official", "courts", "community")
OFFICIAL_RX = re.compile(
    r"\b(police|constabulary|crown prosecution|cps\b|court|judiciary|coroner|fire and rescue|ambulance|coastguard|council|"
    r"national crime agency|hse\b|health and safety executive|environment agency|trading standards|iopc|independent office for police conduct|"
    r"serious fraud office|hmrc|home office|ministry of justice|safer essex roads|nmc\b|nursing and midwifery|probation|prison)\b", re.I)
OFFICIAL_HOST_RX = re.compile(r"(\.police\.uk|\.gov\.uk|judiciary\.uk|cps\.gov\.uk|facebook\.com/(EssexPoliceUK|ECFRS)|\.nhs\.uk|parliament\.uk)", re.I)
CRIME_RX = re.compile(
    r"\b(arrest\w*|charged|charge[sd]? with|accused|suspect\w*|court|magistrates|crown court|trial|jury|jailed|sentenc\w+|convict\w+|guilty|"
    r"murder\w*|manslaughter|stabb\w+|assault\w*|rape[sd]?|sexual\w*|robber\w*|burglar\w*|fraud\w*|theft|stolen|drug deal\w*|"
    r"inquest|coroner|misconduct|indecent|grooming|abus\w+|harass\w+|stalk\w+|dangerous driving|drink.driv\w+)\b", re.I)
INQUEST_RX = re.compile(r"\b(inquest|coroner)\b", re.I)
GUILT_RX = re.compile(r"\b(killer|murderer|rapist|paedophile|pedophile|sex offender|attacker|abuser|thief|thieves|fraudster|conman|burglar|robber|"
                      r"drug dealer|arsonist|stalker|thug|yob|predator|pervert)s?\b", re.I)
CONVICTED_RX = re.compile(r"\b(convicted|conviction|found guilty|pleaded guilty|pled guilty|admitted|admits|jailed|sentenced|was guilty|"
                          r"guilty of|guilty plea|imprisoned|given a .{0,40}(sentence|order)|banned from|struck off)\b", re.I)
ACTIVE_RX = re.compile(r"\b(charged with|has been charged|have been charged|was charged|were charged|appeared (at|before|in)|due (to appear|in court|before)|"
                       r"on trial|goes on trial|stands trial|denies|denied the|pleaded not guilty|remanded|bailed to appear|accused of)\b", re.I)
PRIORS_RX = re.compile(r"\b(previous conviction\w*|previously convicted|previously jailed|criminal record|known to (the )?police|history of (violence|offending|crime)|"
                       r"prior conviction\w*|was jailed in (19|20)\d\d|served time|career criminal|repeat offender)\b", re.I)
SEX_RX = re.compile(r"\b(rape[sd]?|raping|sexual(ly)? (assault\w*|abus\w+|offence\w*|activity|touching|communication)|indecent(ly)? assault\w*|indecent images|"
                    r"grooming|upskirt\w*|voyeur\w*|sexual exploitation)\b", re.I)
IDENT_RX = re.compile(r"\b(his|her|their) (own )?(daughter|stepdaughter|step-daughter|son|stepson|niece|nephew|granddaughter|grandson|sister|brother|cousin|wife|ex-wife|"
                      r"husband|girlfriend|ex-girlfriend|boyfriend|partner|ex-partner|mother|neighbour|lodger|tenant|colleague|employee|pupil|student|patient|babysitter|"
                      r"foster (child|daughter|son))\b", re.I)
# the relationship only matters when it describes the person offended against ("raped his stepdaughter", "abuse of her pupil")
VICTIM_RX = re.compile(r"\b(rap\w+|assault\w+|abus\w+|groom\w+|touch\w+|molest\w+|offences? against|images of|attack\w+|exploit\w+|victim was|complainant was)\b[^.]{0,50}?" + IDENT_RX.pattern, re.I)
NAME_AGE_RX = re.compile(r"\b([A-Z][a-z]+(?:[ -][A-Z][a-z'-]+){1,2}),? (?:aged |age )?(\d{1,2})\b(?! (?:arrests|charges|people|officers|years|months|weeks|days|per|of|November|December|January|February|March|April|May|June|July|August|September|October))")
MINOR_OK_IDS = {"chelmsford-toddler-cyprus-hotel-window-inquest"}  # owner's one-off decisions go here (see ops/newsroom.md)


def text_of(it):
    parts = [it.get("headline"), it.get("summary")] + list(it.get("body") or []) + list(it.get("points") or [])
    return " \n ".join(str(p) for p in parts if p)


def fingerprint(it):
    return hashlib.sha1(text_of(it).encode("utf-8")).hexdigest()


def is_official(it):
    return bool(OFFICIAL_RX.search(str(it.get("source") or "") + " " + str(it.get("org") or ""))) or bool(OFFICIAL_HOST_RX.search(str(it.get("url") or "")))


PERSON_CASE_RX = re.compile(r"\b(arrest\w*|charged with|has been charged|was charged|were charged|accused|suspect\w*|magistrates|crown court|on trial|jury|jailed|"
                            r"sentenc\w+|convict\w+|guilty|murder\w*|manslaughter|stabb\w+|rape[sd]?|raping|sexual\w*|inquest|coroner|misconduct|indecent|grooming)\b", re.I)


def in_scope(it, sec):
    """A story about a person's alleged or proven offence, a court case or an inquest (not every police or council item)."""
    head = str(it.get("headline") or "") + " " + str(it.get("summary") or "")
    return bool(PERSON_CASE_RX.search(head)) or (sec == "courts" and bool(PERSON_CASE_RX.search(text_of(it))))


def problems(it, sec):
    t = text_of(it); out = []
    official = is_official(it)
    has_body = any(str(p).strip() for p in (it.get("body") or []))
    if not official and not has_body:
        out.append("SOURCE: a crime, court or inquest story needs an official source or a body written from a report you read; a one-line summary is not enough")
    g = GUILT_RX.search(t)
    if g and not CONVICTED_RX.search(t):
        out.append(f"GUILT: \"{g.group(0)}\" states guilt but the story reports no conviction or admission; describe what the person is accused of instead")
    if ACTIVE_RX.search(t) and not CONVICTED_RX.search(t):
        p = PRIORS_RX.search(t)
        if p:
            out.append(f"ACTIVE CASE: the story says someone is charged or on trial and also mentions \"{p.group(0)}\"; remove background that could prejudice a trial")
    if it.get("id") not in MINOR_OK_IDS:
        for m in NAME_AGE_RX.finditer(t):
            age = int(m.group(2))
            if age < 18 and (INQUEST_RX.search(t) or not official):
                out.append(f"CHILDREN: \"{m.group(0)}\" names someone under 18" + (" in an inquest story" if INQUEST_RX.search(t) else " and the source is not official") +
                           "; remove the name (say \"a " + str(age) + "-year-old\")")
                break
    if SEX_RX.search(t):
        i = VICTIM_RX.search(t)
        if i:
            out.append(f"ANONYMITY: a sexual offence story says \"{i.group(0)}\", which could identify the complainant, who has lifelong anonymity; remove the relationship and any school, workplace or street detail")
    return out


def check(out, live, ok=()):
    """Returns (held, warned): lists of (section, id, headline, [reasons]). held = new or rewritten stories that fail;
    warned = stories already live and unchanged that fail (left in place)."""
    live_fp = {}
    for sec in SECTIONS:
        for it in (live.get(sec) or []):
            if isinstance(it, dict) and it.get("id"):
                live_fp[it["id"]] = fingerprint(it)
    held, warned = [], []
    for sec in SECTIONS:
        for it in (out.get(sec) or []):
            if not isinstance(it, dict) or not it.get("id") or it["id"] in ok or not in_scope(it, sec):
                continue
            probs = problems(it, sec)
            if not probs:
                continue
            row = (sec, it["id"], str(it.get("headline") or ""), probs)
            (warned if live_fp.get(it["id"]) == fingerprint(it) else held).append(row)
    return held, warned


if __name__ == "__main__":
    import sys, os
    ed = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "edition.json"), encoding="utf-8"))
    held, _ = check(ed, {})
    n = sum(1 for sec in SECTIONS for it in (ed.get(sec) or []) if isinstance(it, dict) and in_scope(it, sec))
    print(f"{n} crime, court and inquest stories checked; {len(held)} would be held")
    for sec, sid, h, probs in held:
        print(f"- [{sec}] {sid}: {h}")
        for p in probs:
            print("    " + p)
