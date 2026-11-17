# Essex News from The Seax (Alexa custom skill)

Plays the latest audio bulletin when someone says "Alexa, open Essex News" (owner's request, 17 Nov 2026).
It sits alongside the Flash Briefing skill and reads the same feed, `audio/alexa.json`, which
`tools/bulletin.py` rewrites with every bulletin. Nothing here needs to change when a bulletin is published.

- Skill ID: amzn1.ask.skill.184986b8-717d-4934-a018-48de25d6fea5 (Alexa-hosted, Node.js, EU Ireland, English UK)
- `lambda/index.js` is the code deployed in the Alexa developer console (Code tab). No dependencies.
- `interaction-model.en-GB.json` is the voice model (Build tab, JSON Editor). Invocation name: "essex news".
- The AudioPlayer interface is switched on (Build tab, Interfaces).

To change it: edit these files, paste them into the console, then Save, Build skill (model) or Deploy (code).
