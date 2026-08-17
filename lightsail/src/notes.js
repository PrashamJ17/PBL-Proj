/** Speaker notes for the deck, taken verbatim from the spoken script. */
const script = require("./script.js");
module.exports = script.map(
  (s) => `[${s.n}/20 · target ${s.seconds}s]  ${s.cue}\n\n${s.text}`
);
