/* Wspólne, testowalne funkcje transkrypcji bez zależności od API lub modeli. */
(function(root,factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.LectureTranscriptCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this,function() {
  "use strict";
  const SAMPLE_RATE = 16000;
  const SEGMENT_SECONDS = 28;
  function planSegments(duration,limit=SEGMENT_SECONDS) {
    if (!Number.isFinite(duration) || duration <= 0 || !Number.isFinite(limit) || limit <= 0 || limit > 29) throw new Error("Nieprawidłowy czas nagrania.");
    const segments=[];
    for (let start=0;start<duration;start+=limit) segments.push({start,duration:Math.min(limit,duration-start)});
    return segments;
  }
  function formatTime(seconds) {
    const n=Math.max(0,Math.floor(seconds));
    return String(Math.floor(n/3600)).padStart(2,"0")+":"+String(Math.floor(n%3600/60)).padStart(2,"0")+":"+String(n%60).padStart(2,"0");
  }
  function appendVerbatim(previous,text) {
    const next=String(text||"").trim();
    if (!next) return String(previous||"");
    return [String(previous||"").trimEnd(),next].filter(Boolean).join(" ");
  }
  return Object.freeze({SAMPLE_RATE,SEGMENT_SECONDS,planSegments,formatTime,appendVerbatim});
});
