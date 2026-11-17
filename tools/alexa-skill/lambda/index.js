// The Seax "Essex News" Alexa custom skill. Plays the latest audio bulletin.
// It reads https://theseax.com/audio/alexa.json (the same feed the Flash Briefing skill uses, written by
// tools/bulletin.py) and tells the speaker to play the MP3 that feed points to. No other moving parts.
const https = require("https");

const FEED = "https://theseax.com/audio/alexa.json";
const NAME = '<sub alias="See Ax">Seax</sub>';

function latest() {
  return new Promise((resolve, reject) => {
    const req = https.get(FEED + "?t=" + Date.now(), { timeout: 4000 }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error("feed status " + res.statusCode)); }
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (c) => { body += c; });
      res.on("end", () => {
        try {
          const data = JSON.parse(body);
          const item = Array.isArray(data) ? data[0] : data;
          if (!item || !/^https:\/\/theseax\.com\/audio\/[\w.-]+\.mp3$/.test(item.streamUrl || "")) throw new Error("no stream in feed");
          resolve(item);
        } catch (e) { reject(e); }
      });
    });
    req.on("timeout", () => req.destroy(new Error("feed timeout")));
    req.on("error", reject);
  });
}

const reply = (response) => ({ version: "1.0", response });
const say = (ssml, end = true, extra = {}) =>
  reply({ outputSpeech: { type: "SSML", ssml: "<speak>" + ssml + "</speak>" }, shouldEndSession: end, ...extra });
const silent = () => reply({});
const stop = () => reply({ directives: [{ type: "AudioPlayer.Stop" }], shouldEndSession: true });

function playDirective(url, title, offset) {
  return {
    type: "AudioPlayer.Play",
    playBehavior: "REPLACE_ALL",
    audioItem: {
      stream: { url, token: url, offsetInMilliseconds: offset || 0 },
      metadata: {
        title: title || "The Seax Essex news bulletin",
        subtitle: "Essex News, Sport, Life.",
        art: { sources: [{ url: "https://theseax.com/icons/icon-512.png" }] },
      },
    },
  };
}

async function play(withSpeech) {
  try {
    const item = await latest();
    const d = playDirective(item.streamUrl, item.titleText, 0);
    if (!withSpeech) return reply({ directives: [d], shouldEndSession: true });
    return say("Here's the latest Essex news from The " + NAME + ".", true, {
      directives: [d],
      card: { type: "Simple", title: item.titleText || "The Seax bulletin", content: "More at theseax.com" },
    });
  } catch (e) {
    console.log("FEED ERROR", e.message);
    return withSpeech ? say("Sorry, the Essex news bulletin isn't available right now. Please try again in a few minutes, or visit the " + NAME + " dot com.") : silent();
  }
}

// carry on from where it was paused, but only if that bulletin is still the latest one (older files are deleted)
async function resume(event, withSpeech) {
  const ap = (event.context && event.context.AudioPlayer) || {};
  try {
    const item = await latest();
    if (ap.token === item.streamUrl && ap.playerActivity !== "FINISHED" && ap.offsetInMilliseconds > 0) {
      return reply({ directives: [playDirective(item.streamUrl, item.titleText, ap.offsetInMilliseconds)], shouldEndSession: true });
    }
  } catch (e) { /* play() reports the problem */ }
  return play(withSpeech);
}

const HELP = "This is Essex News from The " + NAME + ". I play the latest two minute bulletin of Essex news, updated four times a day. " +
  "Say play the news to hear it, or stop to finish. What would you like to do?";

exports.handler = async (event) => {
  const req = event.request || {};
  const type = req.type || "";
  if (type === "LaunchRequest") return play(true);
  if (type === "SessionEndedRequest") return silent();
  if (type === "System.ExceptionEncountered") { console.log("ALEXA EXCEPTION", JSON.stringify(req.error || {})); return silent(); }
  if (type.startsWith("AudioPlayer.")) {
    if (type === "AudioPlayer.PlaybackFailed") console.log("PLAYBACK FAILED", JSON.stringify(req.error || {}));
    return silent();
  }
  if (type.startsWith("PlaybackController.")) {   // buttons on the device or remote: no speech allowed
    if (type === "PlaybackController.PlayCommandIssued") return resume(event, false);
    if (type === "PlaybackController.PauseCommandIssued") return stop();
    return silent();
  }
  if (type === "IntentRequest") {
    const name = (req.intent && req.intent.name) || "";
    switch (name) {
      case "PlayBulletinIntent":
      case "AMAZON.StartOverIntent":
        return play(name === "PlayBulletinIntent");
      case "AMAZON.ResumeIntent":
        return resume(event, true);
      case "AMAZON.PauseIntent":
      case "AMAZON.StopIntent":
      case "AMAZON.CancelIntent":
        return stop();
      case "AMAZON.HelpIntent":
        return say(HELP, false, { reprompt: { outputSpeech: { type: "PlainText", text: "Say play the news, or stop." } } });
      case "AMAZON.NextIntent":
      case "AMAZON.PreviousIntent":
        return say("There is one bulletin at a time. A new one arrives four times a day.");
      case "AMAZON.LoopOnIntent":
      case "AMAZON.LoopOffIntent":
      case "AMAZON.ShuffleOnIntent":
      case "AMAZON.ShuffleOffIntent":
      case "AMAZON.RepeatIntent":
        return say("Sorry, I can't do that with the news bulletin.");
      case "AMAZON.NavigateHomeIntent":
        return stop();
      default:
        return say("Sorry, I didn't catch that. Say play the news to hear the latest Essex bulletin, or stop to finish. What would you like to do?", false,
          { reprompt: { outputSpeech: { type: "PlainText", text: "Say play the news, or stop." } } });
    }
  }
  return silent();
};
