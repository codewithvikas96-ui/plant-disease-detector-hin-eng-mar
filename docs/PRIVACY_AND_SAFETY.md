# Privacy and safety

This app tells farmers what to spray on their food crops. A wrong answer costs money, can
harm the person spraying, and can leave residue on food. This document lists what data the
app handles and every safeguard against unsafe advice.

## 1. What data goes where

| Data | Stays on the phone | Sent to the laptop server | Sent to third parties | Stored |
|---|---|---|---|---|
| Leaf photo | Thumbnail in history | Shrunk copy, for diagnosis | Groq (vision second opinion), only if AI is on | **Not stored** on the server |
| Scan history | Yes (`localStorage`) | No | No | Phone only; "Clear history" deletes it |
| Location | Rounded to ~1 km | Only for weather, chat and (if opted in) the map | Open-Meteo (weather), Groq (chat context) | Map: snapped to a ~5 km cell |
| Voice question | No | Audio, for transcription | Groq (Whisper) | Not stored |
| Chat messages | On screen only | Yes | Groq | Not stored |
| Advisory text for speech | No | Yes | Google (gTTS) | MP3 cached on the server by text hash |
| IP address | — | Yes (normal HTTP) | Cloudflare, if using the tunnel | Kept in memory for rate limiting only |

**No accounts, no names, no phone numbers, no advertising, no analytics.**

### The outbreak map

- **Off by default.** The farmer switches it on in the Map tab. The switch explains what is
  shared.
- A report contains only: disease class, date, a grid cell, and whether the CNN or the AI
  named it. No photo, IP, device ID or exact location.
- The location is rounded on the phone (~1 km) and then snapped on the server to the centre of
  a 0.05° cell (~5.5 km), so a single farm cannot be recovered.
- Healthy results are never reported. Low-confidence results are not reported.
- Limit: 10 reports per visitor per minute.

**Before public deployment:** the map accepts reports from anyone with the link. Add
moderation or require confirmation by a KVK officer before treating it as authoritative.

## 2. Advice safety

| Risk | Safeguard |
|---|---|
| Model names a disease it is unsure of | Below 60 % calibrated confidence, a warning replaces certainty and points to an officer |
| Photo is not a leaf the model knows | Offline unknown-photo check (prototype similarity + energy) warns before the advisory |
| CNN is wrong on field photos | Fine-tuned on field photos; the AI vision model gives an independent second opinion and the disagreement is shown |
| AI invents a dose | The chat model receives the advisory from `remedies.json` and is instructed to use only those products and doses; the phone cannot supply advisory text |
| Banned or restricted products | None in the data (test-enforced); the chat is instructed never to recommend banned pesticides. Streptocycline removed in v2.0 |
| Farmer sprays at the wrong time | Spray-timing card: no rain for 4 h, wind < 15 km/h, 8–32 °C |
| Operator safety | Chat reminds about gloves, mask, wind, rain and the pre-harvest interval |
| Over-reliance on the app | Every result carries a disclaimer to confirm with the KVK or agriculture officer; the chat refers serious cases to the Kisan Call Centre (1800-180-1551) |
| Off-topic or manipulated chat | The chat declines non-farming questions; tested against a prompt-injection request for a banned pesticide |

### Known limits

- **Field accuracy is far below lab accuracy.** See `MODEL_CARD.md`. Treat the diagnosis as a
  first opinion.
- **The 15 Maharashtra-crop advisories were written from general recommendations** and have
  not yet been reviewed by an agronomist.
- **Prices are approximate** and change by brand, pack size and season.
- The AI can still make mistakes in Marathi grammar or detail. It is not a licensed advisor.

## 3. Security

| Area | Measure |
|---|---|
| API key | `GROQ_API_KEY` lives in `.env` (git-ignored), is only read by the server, and is never sent to the phone |
| Quota abuse | 20 AI requests per visitor per minute; real visitor IP read from `CF-Connecting-IP` only when the request comes from the local tunnel |
| Model file | Loaded with `torch.load(weights_only=True)`, so a tampered checkpoint cannot run code |
| Uploads | Type and size checked (images ≤ 12 MB, audio ≤ 5 MB); images decoded with Pillow only |
| Third-party scripts | Leaflet from cdnjs pinned with Subresource Integrity hashes |
| Server address | The laptop's LAN IP is printed to the console only, never returned by the API, so the public tunnel does not leak it |
| XSS | Server text is inserted with `textContent`, never as HTML |

Report a security issue to the project team privately rather than in a public issue.
