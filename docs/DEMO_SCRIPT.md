# Avishkar demo script

A 6-minute run-through, the backup plan, and the questions judges are likely to ask.

## Before you go

- [ ] Laptop charged, charger packed. Sleep disabled (`Settings → System → Power → Never`).
- [ ] `scripts\start.bat` works; console shows `model loaded`, `field accuracy`,
      `unknown-photo check on`, `AI assistant on`.
- [ ] `.venv\Scripts\python -m pytest` passes.
- [ ] Phone on **your own hotspot**, not venue Wi-Fi. Laptop on the same hotspot.
- [ ] `scripts\tunnel.bat` gives an `https://` link; open it once on the demo phone so fonts
      and icons are cached; allow camera, location and microphone.
- [ ] Printed QR code of the tunnel link for judges' phones.
- [ ] **Props:** three real leaves in a zip bag — one diseased tomato or potato leaf, one
      healthy leaf, one cotton or onion leaf. Plus printed photos as backup.
- [ ] Open a second tab on the laptop with `/docs` (API) and `docs/MODEL_CARD.md`.

## The demo (about 6 minutes)

| Time | Show | Say |
|---|---|---|
| 0:00 | Home screen; tap **मराठी** (the app opens in English on first visit) | "A farmer in Maharashtra with a sick tomato plant has three options: guess, ask the shop that sells the spray, or travel to the KVK. We built a fourth: point the phone at the leaf." |
| 0:30 | Tap the camera, hold the leaf too far, then too close in shadow | "Most wrong diagnoses start as bad photos. The camera checks light, glare, distance, shake and focus and gives one instruction at a time." |
| 1:00 | Frame turns turmeric; take the photo | |
| 1:15 | Result with heatmap on | "Diagnosis in under two seconds on a laptop CPU, no internet. The bright area is where the network looked — on the lesion, not the background. That is Grad-CAM." |
| 1:45 | Tap **ऐका** (Listen) | "Many farmers cannot read comfortably. Every advisory is spoken in Marathi or Hindi." |
| 2:15 | Scroll to the cost card, change acres to 3 | "It turns the remedy into a shopping list: how much, and roughly what it costs for their field. And an organic option." |
| 2:45 | Spray-timing card | "A correct spray two hours before rain is money washed away. This uses the live forecast to say when to spray." |
| 3:15 | AI second opinion box | "A second, independent AI checks the same photo without being told our answer. When they disagree, we say so." |
| 3:45 | Tap the mic, ask in Marathi: *"फवारणी कधी करावी?"* | "Farmers can ask by voice. The answer uses only the doses in our verified database, and it knows the weather." |
| 4:30 | Photograph your hand or a pen | "Now the honest part. A normal classifier would still name a disease. Ours says: this is not a leaf I know — offline." |
| 5:00 | Photograph the cotton/onion leaf | "Our offline model knows 14 crops. For cotton, onion, pomegranate, sugarcane and soybean diseases, the AI recognises them and shows the remedy." |
| 5:30 | Map tab | "With permission, each diagnosis adds an anonymous dot to a village-level map, so a KVK can see an outbreak early." |
| 5:50 | Close | "Built for a phone in a field: Marathi first, voice first, honest about uncertainty." |

## If something fails

| Failure | Do this |
|---|---|
| No internet at all | Everything except the AI box, weather, map tiles and Marathi server voice still works. Say: "The core diagnosis runs on this laptop — it does not need the internet." |
| Tunnel down | Use `http://localhost:8000` on the laptop, or the LAN address on the phone (camera falls back to the normal camera app) |
| Real leaf gives a wrong answer | Say so. Show the second opinion and the low-confidence warning. "This is exactly why we built the checks." Then use a printed photo |
| Groq error | "The AI is an optional layer; the diagnosis is independent of it." Move on |
| Server crashed | Rerun `start.bat` (~10 s). The tunnel URL keeps working |

## Questions judges will ask

**Why is your accuracy 99 % if field accuracy is much lower?**
99 % is on PlantVillage, where every leaf is photographed on a plain background in studio
light. On PlantDoc, which uses real field photos, the original model scored 30 %. We
fine-tuned it on field photos and measured again (see `MODEL_CARD.md`). Reporting both numbers
is the honest answer; the checks exist because the field number is not 99 %.

**Why MobileNetV3 and not a bigger model?**
It has to run on a laptop CPU at the exhibition and eventually on a phone: 5.4 M parameters,
17 MB, well under a second per image. Transfer learning from ImageNet gives the filters for
free, so a bigger model buys little on 54 k images.

**How do you stop the AI from giving a dangerous dose?**
The phone only sends the disease name. The server looks up the advisory in our database and
gives it to the model with instructions to use only those products and doses. We tested it
with a request for a banned pesticide in Hindi; it refused and pointed to the Kisan Call Centre.

**How does "not a leaf I know" work?**
For each disease the checkpoint stores the average feature vector of its training images.
A new photo whose features are far from all of them, or whose energy score is low, is flagged.
Thresholds are set so only about 3 % of real leaves are flagged per test.

**What is the heatmap?**
Grad-CAM: the gradient of the winning class with respect to the last convolutional layer tells
us which of its 7×7 regions pushed the decision. The server sends 49 numbers; the phone draws
the spotlight.

**What about farmers without internet?**
The laptop (or a KVK server) runs the model; phones connect over local Wi-Fi. Only the AI,
weather and map need the internet. On-device inference is on the roadmap.

**Where do the remedies come from? Who checked them?**
Standard ICAR / KVK advisory doses, written into a structured file that is test-checked for
consistency. We removed Streptocycline because India no longer permits antibiotics on crops.
The five Maharashtra-crop entries still need an agronomist's review — we say so in the data.

**What are the confusing classes?**
Tomato early blight vs target spot (both brown ringed lesions), and early vs late blight on
field photos. The second opinion catches the second one in our own test photo.

**Privacy?**
No accounts. Photos are not stored on the server. The map is opt-in and keeps only the disease
and a ~5 km cell.
