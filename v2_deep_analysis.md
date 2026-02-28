# V2 Output Deep Analysis — Every 5 Seconds

## Video: fdb57dff (75 seconds)

| Time | Frame | What's Shown | Issue |
|------|-------|-------------|-------|
| 0:00 | 1 | Setup shot: bread + bourbon biscuits on cutting board | OK intro |
| 0:05 | 2 | **Same setup**: bread + bourbon biscuits, nearly identical | ❌ DUPLICATE of frame 1 |
| 0:10 | 3 | Mashing banana on bread with fork | Good - action started |
| 0:15 | 4 | Still mashing banana, same angle, same action | ❌ DUPLICATE of frame 3 |
| 0:20 | 5 | Banana on bread, biscuits beside, slightly different stage | ❌ NEAR-DUPLICATE (3rd banana frame) |
| 0:25 | 6 | Butter melting in pan | ✅ NEW step - cooking starts |
| 0:30 | 7 | Pressing bread into buttered pan | ✅ Good progression |
| 0:35 | 8 | French toast cooking in milk/egg in pan | ✅ Good |
| 0:40 | 9 | Same toast in pan, spatula lifting | ⚠️ Similar to frame 8 |
| 0:45 | 10 | Golden toast in pan + adding more butter | ✅ Good - new action |
| 0:50 | 11 | Pouring milk/batter onto bread in pan | ✅ Good - new action |
| 0:55 | 12 | Toast soaking in milk, bubbling | ⚠️ Similar to 11, continuation |
| 1:00 | 13 | Plated toast on white plate + bourbon biscuits | ✅ Good - final presentation |
| 1:05 | 14 | Same plate, same toast, same biscuits | ❌ DUPLICATE of frame 13 |
| 1:10 | 15 | Same plate, same toast, same angle | ❌ DUPLICATE of frames 13-14 |

## Video: 56da3c3f (120 seconds) — Sampled at 0:00, 0:25, 0:55, 1:25, 1:45, 1:55

| Time | What's Shown | Issue |
|------|-------------|-------|
| 0:00 | Banana + bread + biscuit assembly | Similar to fdb57dff |
| 0:25 | Same banana + bread assembly | ❌ Still assembling after 25 seconds |
| 0:55 | Still mashing banana on bread | ❌ SAME ACTION for a full minute! |
| 1:25 | Spreading chocolate on bread | Finally new action, but took 85s to get here |
| 1:45 | Still spreading chocolate | Repetitive |
| 1:55 | Bread + biscuits on board, different angle | ❌ Back to ingredient shot??  |

## Root Cause Analysis

### Problem 1: DUPLICATE CLIPS (biggest issue)
The pipeline picks 2-3 clips from the SAME scene or visually identical scenes.
- Setup shot appears 2x (10 seconds wasted)
- Banana mashing appears 3x (15 seconds wasted)  
- Plating appears 3x (15 seconds wasted)
- **40 seconds of a 75s video is duplicated content** = 53% waste

### Problem 2: MISSING KEY STEPS
From the source videos, these steps clearly happen but are NOT in the output:
- Crushing/placing bourbon biscuits on bread
- Spreading chocolate spread
- Dipping assembled sandwich in egg/milk mixture
- Closing/assembling the sandwich
- The final cut/cross-section reveal

### Problem 3: PACING
A human editor would:
- Show setup: 2-3 sec MAX (we show 10 sec)
- Show banana mashing: 3-4 sec (we show 15 sec)  
- Show plating: 3-5 sec (we show 15 sec)
- Use the saved time for MISSING steps

### Problem 4: The pipeline thinks in CLIPS, not in STORY
A human editor thinks: "What's the story arc? Setup → ingredients → assembly → cook → plate"
Our pipeline thinks: "Which clips scored highest? Pick those."

## What a Human Editor Actually Does

1. **Watches all footage** and mentally maps the full recipe
2. **Identifies the story beats**: every distinct step/action
3. **Picks ONE best moment** per beat (not 3 from the same beat)
4. **Allocates screen time** by interest level:
   - Boring (setup, static shots): 2-3 sec
   - Standard (mixing, spreading): 4-6 sec  
   - Hero moments (sizzle, pour, plate, reveal): 6-10 sec
5. **Never repeats** the same visual twice
6. **Fills gaps**: if a step has no good footage, skip it or use a brief transition

## Required Fixes (in priority order)

1. **Recipe-step dedup**: Each unique recipe step gets exactly ONE clip. Period.
2. **Story-arc structure**: Pipeline should output a SEQUENCE of story beats, not a bag of clips
3. **Time budgeting**: Allocate duration per clip based on action type, not fixed lengths
4. **Missing step detection**: If a recipe step has 0 clips, flag it (don't fill with duplicates)
5. **Hard cap on visual similarity**: No two clips in final output with >0.70 histogram similarity
