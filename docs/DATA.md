# Knowledge data

Everything the app tells a farmer comes from three JSON files in `backend/data/`. They are
data, not code, so an agronomist or a KVK officer can correct them without programming — and
a test suite checks every edit.

| File | Holds | Edited by |
|---|---|---|
| `remedies.json` | Every class: names, symptoms, remedy, prevention, treatments — in 3 languages | Agronomist |
| `prices.json` | Approximate price per gram/ml of each product | Anyone who knows local prices |
| `organic.json` | Organic options per pathogen type | Agronomist |

After any edit, run the tests (`.venv\Scripts\python -m pytest`) and restart the server.

---

## `remedies.json`

```json
{
  "_meta": { "version": "2.0", "disclaimer": { "en": "…", "hi": "…", "mr": "…" }, "...": "..." },

  "Tomato___Early_blight": {
    "healthy": false,
    "severity": "medium",
    "pathogen": "Alternaria solani (fungus)",
    "pathogen_type": "fungal",
    "crop":       { "en": "Tomato", "hi": "टमाटर", "mr": "टोमॅटो" },
    "disease":    { "en": "Early Blight", "hi": "…", "mr": "…" },
    "symptoms":   { "en": "…", "hi": "…", "mr": "…" },
    "remedy":     { "en": "… Mancozeb 75% WP at 2.5 g per litre …", "hi": "…", "mr": "…" },
    "prevention": { "en": "…", "hi": "…", "mr": "…" },
    "treatments": [
      { "product": "Mancozeb 75% WP", "dose": 2.5, "unit": "g" },
      { "product": "Chlorothalonil 75% WP", "dose": 2, "unit": "g" }
    ],
    "spray_l_per_acre": 200,
    "plantvillage": true
  }
}
```

| Field | Values | Notes |
|---|---|---|
| key | `Crop___Condition` | Must match the CNN class name exactly for PlantVillage classes |
| `healthy` | bool | Healthy entries have `severity: "none"` and no treatments |
| `severity` | `none`, `low`, `medium`, `high` | Colours the result card |
| `pathogen` | text | Shown in italics; include the organism type in brackets |
| `pathogen_type` | `fungal`, `oomycete`, `bacterial`, `vector`, `mite`, `none` | Picks the organic option |
| `crop` … `prevention` | `{en, hi, mr}` | All three required. Remedy doses are **per litre of water** |
| `treatments` | list | The alternatives named in `remedy.en` ("X **or** Y"), with the same doses |
| `unit` | `g`, `ml`, `l` | `l` is a ready-mixed spray such as Bordeaux 1% |
| `spray_l_per_acre` | number | 200 for field crops, 400 for orchards |
| `plantvillage` | bool | `false` for crops only the AI vision model can name |

### Rules enforced by `tests/test_remedies.py`

- Every text field is present and non-empty in `en`, `hi` and `mr`.
- Every treatment's product name and dose appears in `remedy.en` — the cost card and the
  spoken remedy can never disagree.
- Every product has a price in `prices.json`.
- No antibiotic is recommended; Streptocycline may only appear as "Do not use Streptocycline".
- Healthy entries have no treatments; disease entries have an organic option.

### Writing a good advisory

- Short sentences, everyday village words. It is read aloud.
- Give the dose exactly: product name with formulation, grams or ml **per litre**.
- Give the repeat interval ("repeat after 10 days").
- Say what to do first when it matters ("remove the lowest infected leaves").
- When there is no chemical cure (viruses, Esca, red rot), say so plainly and give the
  vector control or sanitation steps instead.
- Never recommend a product banned or restricted in India.

---

## `prices.json`

```json
{
  "_meta": { "currency": "INR", "note": "…", "updated": "2026-09" },
  "Mancozeb 75% WP": { "per_unit": 0.5, "unit": "g" }
}
```

`per_unit` is rupees per gram (`g`), millilitre (`ml`), litre (`l`) or piece. The cost the
farmer sees is:

```
quantity per acre = dose per litre × spray_l_per_acre
cost per acre     = quantity per acre × per_unit          (× the farmer's acres, on the phone)
```

Example: Mancozeb 2.5 g/L × 200 L = 500 g × ₹0.5 = **₹250 per acre per spray**.

Prices are approximate retail. Update `updated` when you change them, and prefer the price of
the pack size a smallholder actually buys.

---

## `organic.json`

One entry per `pathogen_type`, with text in three languages and costed items:

```json
"fungal": {
  "items": [ { "product": "Pseudomonas fluorescens 1% WP", "dose": 10, "unit": "g" } ],
  "text":  { "en": "…", "hi": "…", "mr": "…" }
}
```

---

## Adding a disease or crop

1. **Write the entry** in `remedies.json` with all fields in all three languages. Use a key
   `Crop___Condition`. Set `plantvillage: false`.
2. **Add prices** for any new product to `prices.json`.
3. **Run the tests.** Fix anything they report.
4. The **AI vision model** can now name it (it receives every key in the file). The chat
   will answer questions about it using your advisory.
5. **To teach the offline CNN**, collect 100+ photos per class, put them in
   `training/data/extra/<Crop___Condition>/`, and run
   `python training/finetune_field.py --extra-dir training/data/extra`. The classifier grows
   new outputs while keeping what it knows. Copy the new checkpoint into `backend/models/`.

## Sources and review status

| Data | Basis | Review |
|---|---|---|
| 38 PlantVillage classes | Commonly recommended doses in ICAR / Krishi Vigyan Kendra advisories | Written for the project; confirm locally |
| 15 Maharashtra classes | Common ICAR and state agricultural university recommendations | **Needs agronomist review** before field use |
| Prices | Approximate 2026 Maharashtra retail | Check with a local dealer |

Changes in version 2.0: Streptocycline removed from the three bacterial-spot remedies (India
no longer permits streptomycin and tetracycline on crops); structured treatments, pathogen
type and spray volume added to every class; 15 classes added.
