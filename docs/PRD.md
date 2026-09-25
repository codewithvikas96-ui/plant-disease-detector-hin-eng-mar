# Product Requirements Document — Plant Disease Detector (पीक रोग ओळख)

| | |
|---|---|
| **Version** | 2.0 |
| **Status** | Built; field accuracy work ongoing |
| **Event** | Avishkar 2026 |
| **Owners** | Project team (branch `sachin`) |
| **Last updated** | September 2026 |

---

## 1. Problem

A smallholder farmer in Maharashtra who sees spots on a tomato leaf has three options today:
guess, ask the agri-input shop (who has something to sell), or travel to a Krishi Vigyan
Kendra (KVK). Guessing wrong means spraying the wrong chemical, or spraying too late. Late
blight can destroy a tomato or potato field within a week.

Existing apps mostly work in English, assume the farmer can read, name a disease without
saying how sure they are, and stop at the diagnosis. They do not say how much to spray, what
it will cost, or when the weather allows it.

## 2. Users

| Persona | Situation | What they need |
|---|---|---|
| **Smallholder farmer** (primary) | 1–5 acres, budget Android phone, patchy 2G/3G, reads Marathi slowly or not at all | Point the camera, hear the answer in Marathi, know exactly what to buy and when to spray |
| **KVK / agriculture officer** | Advises hundreds of farmers, sees outbreaks late | An early view of what is spreading where; a tool they can trust and recommend |
| **Agri-input dealer** | Asked "what should I spray?" all day | A second opinion with correct doses, not a sales pitch |
| **Avishkar judge** | Evaluates technical depth and real-world value | Evidence the model works outside the lab, honesty about limits |

## 3. Goals and non-goals

**Goals**

1. Diagnose common leaf diseases from one phone photo in under 2 seconds.
2. Give the full advisory — disease, symptoms, remedy with exact dose, prevention — in
   Marathi, Hindi or English, **readable and listenable**.
3. Never state a confident diagnosis the system has not earned: say "not sure" and "not a
   leaf I know" out loud.
4. Turn the remedy into action: cost per acre, an organic option, and when to spray.
5. Keep working when the internet does not: the core diagnosis runs on the laptop server.

**Non-goals (this version)**

- Replacing the agriculture officer. Every screen says to confirm before spraying.
- Pest identification from insect photos, nutrient deficiency, soil testing.
- Running the CNN on the phone itself (planned, see roadmap).
- User accounts, payments, or selling inputs.

## 4. Scope

**Crops.** 14 crops / 38 classes recognised by the CNN (PlantVillage: apple, blueberry,
cherry, maize, grape, orange, peach, bell pepper, potato, raspberry, soybean, squash,
strawberry, tomato). Five Maharashtra crops — cotton, soybean diseases, sugarcane, onion,
pomegranate (15 classes) — recognised by the AI vision model when online.

**Languages.** English (default on first visit), Marathi, Hindi — every string, the advisory,
and speech. The farmer's choice is remembered on the phone.

## 5. Functional requirements

Priority: **P0** must ship, **P1** should ship, **P2** nice to have.

### 5.1 Capture

| ID | Requirement | Priority | Acceptance criteria |
|---|---|---|---|
| CAP-1 | Take a photo or choose from gallery | P0 | Both paths reach the diagnosis; works on Android Chrome and iOS Safari |
| CAP-2 | Live camera guide | P1 | Checks light, glare, leaf coverage, movement and sharpness ≥ 4 times/s; shows one instruction at a time; shutter turns turmeric when ready |
| CAP-3 | Fallback when the camera API is unavailable | P0 | On plain HTTP or permission denial, opens the phone's own camera app |
| CAP-4 | Shrink photos before upload | P0 | A 4 MB photo uploads as ≤ 200 KB |

### 5.2 Diagnosis

| ID | Requirement | Priority | Acceptance criteria |
|---|---|---|---|
| DX-1 | Classify into 38 classes | P0 | Result in < 2 s on a laptop CPU |
| DX-2 | Show confidence | P0 | Calibrated percentage; colour changes at 60 % and 80 % |
| DX-3 | Low-confidence warning | P0 | Below 60 %, a warning replaces certainty and suggests a clearer photo or an officer |
| DX-4 | Unknown-photo detection, offline | P1 | Non-leaf photos flagged; ≤ 5 % of real leaves falsely flagged |
| DX-5 | Heatmap of where the model looked | P1 | Grad-CAM overlay aligned to the photo, toggleable |
| DX-6 | Top-3 alternatives | P1 | Shown collapsed under the result |

### 5.3 Advisory

| ID | Requirement | Priority | Acceptance criteria |
|---|---|---|---|
| ADV-1 | Symptoms, remedy with dose, prevention | P0 | In the selected language; doses per litre of water |
| ADV-2 | Read aloud | P0 | Marathi works even on phones with no Marathi voice (server TTS fallback) |
| ADV-3 | Cost per acre | P1 | Per product: quantity and ₹ for the farmer's acreage; prices editable in one file |
| ADV-4 | Organic alternative | P1 | By pathogen type, with dose and cost |
| ADV-5 | Disclaimer | P0 | Every result tells the farmer to confirm with KVK / officer |
| ADV-6 | No banned products | P0 | No antibiotic (Streptocycline) or banned pesticide in any advisory — enforced by a test |

### 5.4 AI assistant (online, optional)

| ID | Requirement | Priority | Acceptance criteria |
|---|---|---|---|
| AI-1 | Independent second opinion | P1 | Vision model not told the CNN answer; verdicts: agrees / disagrees / not a leaf / unknown / extended crop |
| AI-2 | Follow-up chat | P1 | Streams in the farmer's language; doses only from the advisory; declines non-farming questions |
| AI-3 | Voice questions | P1 | Speak Marathi/Hindi, answer read back automatically |
| AI-4 | Extended crops | P2 | Cotton, soybean, sugarcane, onion, pomegranate advisories via vision model |
| AI-5 | Quota protection | P0 | ≤ 20 AI requests per visitor per minute; key never sent to the phone |
| AI-6 | Works without a key | P0 | AI panels hidden; everything else unchanged |

### 5.5 Field tools

| ID | Requirement | Priority | Acceptance criteria |
|---|---|---|---|
| FLD-1 | Spray timing | P1 | Next dry, calm daylight window in 48 h; rain warning; humidity disease risk |
| FLD-2 | Scan history | P1 | Last 40 scans on the phone; reopen in any language; works offline for seen advisories |
| FLD-3 | Outbreak map | P2 | Opt-in; only disease + ~5 km cell stored; 7/30/90-day view; nearby alert on home |

### 5.6 Platform

| ID | Requirement | Priority | Acceptance criteria |
|---|---|---|---|
| PLT-1 | Installable PWA | P0 | "Add to Home screen" on Android; opens offline to the shell |
| PLT-2 | Public HTTPS link | P1 | Cloudflare Tunnel; see `DEPLOY.md` |
| PLT-3 | Sunlight-readable UI | P0 | Tap targets ≥ 44 px, body text ≥ 16 px, high contrast |

## 6. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | Diagnosis < 2 s server time; first paint < 3 s on 3G after install |
| Offline | Shell, fonts, icons and seen advisories cached; diagnosis needs the laptop server, not the internet |
| Privacy | No accounts; photos not stored on the server; location rounded before leaving the phone |
| Accessibility | Voice for every advisory; visible focus; reduced-motion respected |
| Maintainability | Remedy data, prices and strings editable without code changes; automated tests |

## 7. Success metrics

| Metric | Target | Current |
|---|---|---|
| Field-photo top-1 accuracy (PlantDoc test) | ≥ 60 % | See `MODEL_CARD.md` |
| Field-photo top-3 accuracy | ≥ 85 % | See `MODEL_CARD.md` |
| Lab accuracy (PlantVillage) | ≥ 97 % | See `MODEL_CARD.md` |
| Non-leaf photos flagged as unknown | ≥ 80 % | See `MODEL_CARD.md` |
| Time from opening app to spoken advisory | < 30 s | Demo measurement |
| Advisory doses matching the knowledge base | 100 % | Enforced by `tests/test_remedies.py` |

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Wrong diagnosis leads to wrong spray | Crop loss, cost, health | Confidence threshold, unknown check, second opinion, disclaimer, officer referral |
| AI invents a dose | Unsafe advice | Doses only from `remedies.json`; the server supplies the advisory, not the phone |
| Groq model retired | AI features break | Model IDs in `.env`; startup check warns |
| Venue Wi-Fi fails at demo | Dead demo | Laptop + own hotspot; core works without internet |
| Extended-crop advisories not expert-reviewed | Inaccurate advice | Marked in data; review by an agronomist before field use |
| Outbreak map abused with fake reports | Misleading map | Rate limit, opt-in only; moderation needed before public use |

## 9. Roadmap

| Phase | Items |
|---|---|
| **Next** | Bundle fonts/icons/Leaflet locally (Vite) for full offline; agronomist review of extended crops; collect Maharashtra field photos |
| **Later** | Train the CNN on cotton, onion, pomegranate, sugarcane (`finetune_field.py --extra-dir`); on-device model (ONNX/TFLite); WhatsApp share of advisory |
| **Future** | KVK dashboard for outbreak monitoring; nutrient deficiency and pest photos; Play Store app via Capacitor |
