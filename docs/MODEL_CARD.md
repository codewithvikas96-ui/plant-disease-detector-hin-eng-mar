# Model card — Plant Disease Detector CNN

What the model is, how it was trained, how well it works on real photos, and where it fails.
All numbers are from `backend/models/plant_disease_model.json`, written by the training run.

## Summary

| | |
|---|---|
| **Task** | Classify one leaf photo into 38 crop/disease classes |
| **Architecture** | MobileNetV3-Large (5.4 M parameters, 17 MB), ImageNet-pretrained |
| **Input** | RGB photo, resized so the short side is 255 px, centre-cropped to 224 × 224 |
| **Output** | 38 probabilities (temperature-calibrated), top-3, Grad-CAM 7×7 map, unknown-photo flag |
| **Speed** | ~50–130 ms per photo on a laptop CPU, including Grad-CAM |
| **Version** | 2.0 — PlantVillage training + field fine-tuning (September 2026) |

## Intended use

- **For:** a first opinion for smallholder farmers and agriculture staff in India on common
  leaf diseases of the 14 supported crops, always followed by confirmation from a KVK or
  agriculture officer before spraying.
- **Not for:** final diagnosis, crops outside the list, pests photographed on their own,
  nutrient deficiencies, fruit or stem diseases, or any automated spraying decision.

## Training data

| Stage | Data | Images | Notes |
|---|---|---|---|
| 1. Base training | [PlantVillage](https://github.com/spMohanty/PlantVillage-Dataset), colour split | 54,305 (80/20 stratified split) | Leaves photographed one at a time on a plain background in controlled light |
| 2. Field fine-tuning | [PlantDoc](https://github.com/pratikkayal/PlantDoc-Dataset) train split | 1,984 train / 352 validation | Real photos from the web: field backgrounds, several leaves, hands, shadows |
| | PlantVillage sample | 1,824 train / 456 holdout | 60 per class, mixed 1:1 with PlantDoc so the model does not forget |

PlantDoc's 28 classes all map onto PlantVillage classes (`PLANTDOC_MAP` in
`training/finetune_field.py`). Ten PlantVillage classes have no PlantDoc equivalent (for
example orange greening, grape esca, tomato target spot), so they got no field photos.

**Crops:** apple, blueberry, cherry, maize, grape, orange, peach, bell pepper, potato,
raspberry, soybean, squash, strawberry, tomato.

## Training procedure

**Stage 1** (`training/train_plantvillage.ipynb`, Colab T4): head-only warm-up, then full
fine-tuning — 5 epochs in total for the shipped checkpoint; cross-entropy with label smoothing
0.1; augmentation with random crops, flips, rotation, colour jitter and random erasing.

**Stage 2** (`training/finetune_field.py`, laptop CPU, ~40 minutes):

| Setting | Value |
|---|---|
| Epochs | 6, best kept by mean of field and lab validation accuracy |
| Optimiser | AdamW, weight decay 1e-4; learning rate 2e-4 backbone, 1e-3 head; one-cycle schedule |
| Batch | 32, each epoch half PlantDoc, half PlantVillage (weighted sampling) |
| Augmentation | Stronger than stage 1: crops down to 35 % of the image, rotation ±30°, colour jitter 0.4, Gaussian blur, random erasing |
| Loss | Cross-entropy, label smoothing 0.1 |

**Calibration.** A single temperature *T* = 0.77 was fitted on the validation sets
(Guo et al., 2017). The probabilities the app shows are `softmax(logits / T)`.

**Unknown-photo statistics.** For each class, the mean of the L2-normalised penultimate
features (1,280-d) of its clean training images is stored as a prototype. A photo is
flagged as unknown when its highest cosine similarity to any prototype is below **0.441**,
or its energy score `T · logsumexp(logits / T)` is below **4.38**. Both thresholds are the
3rd percentile of real validation leaves.

## Results

### Accuracy

| Test set | Before fine-tuning | After fine-tuning |
|---|---|---|
| **Field photos — PlantDoc test** (236), top-1 | 30.1 % | **66.5 %** |
| **Field photos — PlantDoc test**, top-3 | 58.1 % | **87.7 %** |
| Lab photos — PlantVillage holdout (456), top-1 | 99.6 % | 98.7 % |
| Lab photos — full PlantVillage validation (10,861), top-1 | 99.53 % | not re-measured |

Fine-tuning more than doubled accuracy on field photos at a cost of under one point on lab
photos. Top-3 at 87.7 % is why the app shows two alternatives under every diagnosis.

**Validation curve (stage 2):**

| Epoch | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Field validation | 53.7 % | 57.1 % | 62.8 % | 64.2 % | 64.5 % | 64.2 % |
| Lab validation | 98.7 % | 98.5 % | 97.6 % | 98.7 % | 98.2 % | 98.2 % |

### Calibration

| | Expected calibration error |
|---|---|
| Before temperature scaling | 0.075 |
| After (T = 0.77) | **0.021** |

A shown confidence of 80 % is now right about 80 % of the time on the validation data.

### Unknown-photo detection

| Set | Flagged as unknown |
|---|---|
| Real leaves (validation) | 4.8 % (false alarms) |
| Random non-plant photos (60, from picsum.photos) | **80 %** |

The missed 20 % included a city skyline and a skatepark. The app has two more layers for
these: the camera guide measures leaf coverage before the photo is taken, and the AI second
opinion (online) classifies "not a leaf" independently.

## Limitations

1. **Field accuracy is about two in three.** Treat the diagnosis as a first opinion. The app
   warns below 60 % calibrated confidence and shows the top 3.
2. **The PlantDoc test set is small (236 photos) and comes from the web**, not from Indian
   farms. Accuracy on Maharashtra field photos is not yet measured.
3. **Ten classes had no field training photos** and are likely weaker on real photos than the
   table suggests.
4. **Similar diseases are confused**: early vs late blight, tomato vs potato late blight
   (the same pathogen), early blight vs target spot. In our own field photo of tomato early
   blight the model is wrong at low confidence; the AI second opinion names it correctly.
5. **Only one leaf, from above.** Multiple leaves, whole plants, fruit or stems reduce accuracy.
6. **The unknown check misses about 1 in 5 non-plant photos.**
7. **Crops outside the 14** (cotton, onion, sugarcane, pomegranate, soybean diseases) are not
   recognised by this model; the AI vision model covers them when online.
8. The lab holdout sample may overlap images seen in stage-1 training, which would make the
   lab number slightly optimistic.

## Ethical considerations

- A wrong confident diagnosis can lead to an unnecessary or wrong spray, which costs money
  and exposes the farmer and consumers to chemicals. The confidence threshold, unknown check,
  second opinion and the disclaimer on every result exist for this reason.
- Advice is only as good as `backend/data/remedies.json`; the model chooses the class, the
  data supplies the advice. See `DATA.md` for review status.
- No personal data is used in training. PlantDoc and PlantVillage are public research datasets.

## Reproduce

```bat
.venv\Scripts\python training\fetch_plantvillage_sample.py
git clone --depth 1 https://github.com/pratikkayal/PlantDoc-Dataset training\data\plantdoc
.venv\Scripts\python training\finetune_field.py --epochs 6
```

Seed 42. Output: `backend/models/plant_disease_model_field.pt` and `.json`. Results vary by
about ±2 points between runs on CPU.

## References

- Howard et al., *Searching for MobileNetV3*, ICCV 2019.
- Hughes & Salathé, *An open access repository of images on plant health* (PlantVillage), 2015.
- Singh et al., *PlantDoc: A Dataset for Visual Plant Disease Detection*, CoDS-COMAD 2020.
- Selvaraju et al., *Grad-CAM: Visual Explanations from Deep Networks*, ICCV 2017.
- Guo et al., *On Calibration of Modern Neural Networks*, ICML 2017.
- Liu et al., *Energy-based Out-of-distribution Detection*, NeurIPS 2020.
