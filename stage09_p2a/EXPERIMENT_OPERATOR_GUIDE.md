# EXPERIMENT OPERATOR GUIDE — S40 physical session

**Stage:** `SCI_STAGE09_P1_REAL_CAPTURE_READY`
For the person at the bench. Print this. Nothing here is automated.

---

## 0. Before anything

| item | confirm |
|---|---|
| the five targets are on the bench, labelled S00 / S20 / S40-A / S40-B / S60 | ☐ |
| the reference instrument is chosen and its model, resolution, repeatability are known | ☐ |
| a tape measure or rule for the nominal distance | ☐ |
| a thermometer | ☐ |
| the room lighting is stable and no direct sunlight falls on the targets | ☐ |
| nobody will walk between the camera and the target during a capture | ☐ |

**If the instrument's model and resolution are unknown, stop here.** Recording a value you cannot attribute
is worse than recording nothing.

## 1. Sketch of a placement

```
   camera (fixed)                 target
        │                          ┌─────┐
        │◄──── nominal distance ──►│     │   near face on top for S40-A
        │      (tape measure)      │     │   (mirrored for S40-B)
        ▼                          └─────┘
                                   bench surface, flat, no tape inside the ROI
```

## 2. The placement plan (5 per target)

| placement | what to change |
|---|---|
| 1 | nominal: target centred, faces square to the camera |
| 2 | rotate the target ≈ 15° in-plane |
| 3 | tilt ≈ 5–10° about a horizontal axis |
| 4 | shift ≈ 50 mm laterally |
| 5 | change the distance by ≈ 100 mm |

Write what you actually did into `placement_metadata.csv`. If a placement ends up different from the plan,
record the real geometry — the analysis reads the file, not the plan.

## 3. Per-placement procedure

```
1. place the target; hands clear
2. wait ~3 s so nothing is moving
3. run the capture command (it prints the valid ratio per frame)
4. do not touch the target
5. take three independent reference readings at the recorded location
   - re-open the instrument between readings
   - if one reading is far off, take a fourth and record it as an outlier
6. fill placement_metadata.csv
7. re-position for the next placement
```

## 4. The three readings, precisely

The step is measured **between the two faces of the same target**, at the location written in
`measurement_location`. For S40-A/B that location must lie inside the ROI footprint the camera sees, otherwise
you are comparing two different places on a target whose faces are not perfectly parallel.

| do | do not |
|---|---|
| re-open the caliper between readings | take three readings without moving the jaws |
| record every reading, including outliers | average on paper |
| write the instrument model and resolution | leave them blank "to fill later" |
| measure after the capture, target untouched | move the target and then measure |

## 5. What the numbers mean — keep them apart

| quantity | what it is | how it is obtained |
|---|---|---|
| **relative step error** | measured plane separation − instrument reference | needs the instrument |
| **plane local noise** | RMS of points about the fitted plane | D435 only, no reference |
| **absolute distance bias** | measured distance to a plane − independent length | only S00, only with a length standard |

**Never combine these into one "accuracy" number.** They are different questions with different references.

## 6. If something goes wrong

| situation | action |
|---|---|
| a frame looks wrong (black, half-missing) | let the capture finish, then re-capture the placement; do not delete the old one |
| valid ratio is low (below ~0.9) | **keep the frames**; record it; low coverage is a result, not an error |
| the target moved during capture | re-capture; mark the old placement `MOTION` in the manifest |
| the instrument gives readings differing by > 3× its repeatability | take a fourth reading; record all of them |
| you are unsure which face is which | stop and check against the target's label; a mislabelled ROI invalidates the analysis |
| you must leave mid-session | stop cleanly; a partial session is fine, it will validate as `INCOMPLETE` and be completed later |

## 7. What never happens

```text
the robot does not move            — this session is camera-only
no ROS, no CAN, no gripper
no changing exposure/gain/emitter mid-session
no deleting frames because they look bad
no using the D435's own number as the reference
no nominal 20/40/60 written into the reference column
no ROI adjustment after seeing an error value
```

## 8. End of session

```
1. run:  python3 validate_capture.py --session <dir> --require-reference
2. exit 0 → the session is complete and analysable
   exit 3 → capture is fine but a reference is missing; fill it before analysis
   exit 1 → read the reported reasons; fix and re-capture the named placements
3. record the session directory name and the date in the lab log
4. hand the directory to the analysis side together with the instrument's metadata sheet
```

## 9. What the operator must never be asked to do

* produce a reference value from memory;
* fill a reading with the nominal step height;
* decide which frames to keep based on the result;
* run the analysis or interpret the step error.

The operator records reality. Interpretation happens later, with the validator's output and the instrument
metadata in hand.
