#!/usr/bin/env python3
"""Evaluate a video by analyzing chunks with direct video input to Qwen VL.

Uses native video input (not frame extraction) for much better action recognition.
The VL model sees full motion sequences, catching brief actions like sugar
sprinkling or fork mashing that single frames miss.

Usage:
    python scripts/evaluate_video.py <video_path> [--chunk-size 10] [--fps 2.0]
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def probe_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def split_into_chunks(video_path: str, output_dir: str, chunk_size: int) -> list[dict]:
    """Split video into chunk files for direct video analysis."""
    duration = probe_duration(video_path)
    num_chunks = math.ceil(duration / chunk_size)
    chunks = []

    for i in range(num_chunks):
        start = i * chunk_size
        end = min(start + chunk_size, duration)
        chunk_dur = end - start

        if chunk_dur < 2:  # Skip very short final chunks
            continue

        chunk_path = os.path.join(output_dir, f"chunk_{i:03d}.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{start:.2f}", "-i", video_path,
             "-t", f"{chunk_dur:.2f}", "-c", "copy", chunk_path],
            capture_output=True, text=True
        )

        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 1000:
            chunks.append({
                "index": i,
                "start": start,
                "end": end,
                "path": chunk_path,
            })
        else:
            chunks.append({
                "index": i,
                "start": start,
                "end": end,
                "path": None,
            })

    return chunks


def analyze_video_chunk(model, processor, config, chunk_path: str,
                        context: str = "", fps: float = 2.0) -> str:
    """Analyze a video chunk by passing it directly to the VL model."""
    import mlx.core as mx
    from mlx_vlm import generate
    from mlx_vlm.video_generate import process_vision_info, is_video_model

    if context:
        prompt = (
            f"Recipe context: {context}\n\n"
            "Describe exactly what is happening in this video clip in 2-3 sentences. "
            "Focus on: what specific cooking actions are being performed, "
            "what ingredients and utensils (fork, spoon, knife, etc.) are visible, "
            "and what step of the recipe this corresponds to. "
            "Be specific about actions — e.g. 'mashing banana with a fork' not just 'preparing food'."
        )
    else:
        prompt = (
            "Describe exactly what is happening in this cooking video clip in 2-3 sentences. "
            "Focus on: what specific cooking actions are being performed, "
            "what ingredients and utensils are visible, "
            "and the current stage of cooking. Be specific and factual."
        )

    if is_video_model(model):
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "video",
                        "video": chunk_path,
                        "max_pixels": 224 * 224,
                        "fps": fps,
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs, fps_info = process_vision_info(messages, True)

        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        input_ids = mx.array(inputs["input_ids"])
        pixel_values = inputs.get("pixel_values_videos", inputs.get("pixel_values", None))
        if pixel_values is None:
            return "[FAILED - no video input processed]"
        pixel_values = mx.array(pixel_values)
        mask = mx.array(inputs["attention_mask"])

        kwargs = {"video": [chunk_path]}
        if inputs.get("video_grid_thw", None) is not None:
            kwargs["video_grid_thw"] = mx.array(inputs["video_grid_thw"])
        if inputs.get("image_grid_thw", None) is not None:
            kwargs["image_grid_thw"] = mx.array(inputs["image_grid_thw"])
        kwargs["input_ids"] = input_ids
        kwargs["pixel_values"] = pixel_values
        kwargs["mask"] = mask

        response = generate(
            model, processor, prompt=text,
            max_tokens=300, verbose=False, **kwargs,
        )

        text_out = response.text.strip() if hasattr(response, 'text') else str(response).strip()
    else:
        # Fallback to frame-based analysis
        from mlx_vlm.prompt_utils import apply_chat_template as apt
        from mlx_vlm.utils import load_config

        frame_path = chunk_path.rsplit('.', 1)[0] + '_frame.jpg'
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "5", "-i", chunk_path,
             "-vf", "scale='if(gt(iw,ih),720,-2)':'if(gt(iw,ih),-2,720)'",
             "-frames:v", "1", "-q:v", "2", frame_path],
            capture_output=True
        )
        if not os.path.exists(frame_path):
            return "[FAILED - no frame extracted]"

        formatted = apt(processor, config, prompt, num_images=1)
        output = generate(model, processor, formatted, [frame_path],
                          max_tokens=300, verbose=False)
        text_out = output.text.strip() if hasattr(output, 'text') else str(output).strip()

    if '<|endoftext|>' in text_out:
        text_out = text_out.split('<|endoftext|>')[0].strip()
    return text_out


def is_garbage(text: str) -> bool:
    """Check if VL output is garbage."""
    if not text or len(text) < 15:
        return True
    if text.count('!') > len(text) * 0.3:
        return True
    if text.startswith('[FAILED'):
        return True
    return False


def classify_content(text: str) -> str:
    """Classify what cooking phase a description represents."""
    t = text.lower()

    if any(w in t for w in ['empty', 'nothing', 'black screen']):
        return 'empty/transition'
    if any(w in t for w in ['fork', 'mash']):
        return 'mashing/prep'
    if any(w in t for w in ['nutella', 'chocolate spread', 'spreading chocolate']):
        return 'spreading nutella'
    if any(w in t for w in ['spreading', 'spread']) and 'banana' in t:
        return 'banana prep'
    if any(w in t for w in ['banana', 'slice']) and any(w in t for w in ['bread', 'cutting board']):
        return 'banana prep'
    if any(w in t for w in ['sandwich', 'assembl', 'on top', 'placing on top']):
        return 'assembling'
    if any(w in t for w in ['sugar', 'caramel', 'sprinkle sugar']):
        return 'sugar/caramelizing'
    if any(w in t for w in ['milk', 'pour milk', 'white liquid', 'foamy']):
        return 'milk pouring'
    if any(w in t for w in ['butter', 'melt']) and any(w in t for w in ['pan', 'frying']):
        return 'heating pan/butter'
    if any(w in t for w in ['golden', 'crispy', 'toasting', 'toast', 'frying', 'cooking']):
        return 'cooking/toasting'
    if any(w in t for w in ['spoon', 'pressing']):
        return 'pressing with spoon'
    if any(w in t for w in ['plate', 'serving', 'plating', 'served', 'ready']):
        return 'plating/serving'
    if any(w in t for w in ['chopping', 'cutting', 'slicing', 'dicing', 'knife']):
        return 'cutting/prep'
    if any(w in t for w in ['pan', 'pot', 'stove', 'stovetop']):
        return 'cooking setup'

    return 'other'


def main():
    parser = argparse.ArgumentParser(description="Evaluate video quality (direct video input)")
    parser.add_argument("video_path", help="Path to video file")
    parser.add_argument("--chunk-size", type=int, default=10, help="Chunk size in seconds")
    parser.add_argument("--fps", type=float, default=2.0, help="FPS for video sampling")
    parser.add_argument("--context", type=str, default="", help="Recipe context for the prompt")
    args = parser.parse_args()

    video_path = args.video_path
    if not os.path.exists(video_path):
        print(f"Error: {video_path} not found")
        sys.exit(1)

    duration = probe_duration(video_path)
    file_size = os.path.getsize(video_path) / (1024 * 1024)

    print(f"{'=' * 60}")
    print(f"VIDEO EVALUATION (Direct Video Input)")
    print(f"{'=' * 60}")
    print(f"Video: {Path(video_path).name}")
    print(f"Duration: {duration:.1f}s ({duration/60:.1f} min)")
    print(f"File size: {file_size:.1f} MB")
    print(f"Chunk size: {args.chunk_size}s | FPS: {args.fps}")
    print()

    # Patch transformers bug
    try:
        from transformers.models.auto import video_processing_auto
        _orig = video_processing_auto.video_processor_class_from_name
        def _patched(class_name):
            try:
                return _orig(class_name)
            except TypeError:
                return None
        video_processing_auto.video_processor_class_from_name = _patched
    except Exception:
        pass

    # Load model
    print("Loading Qwen 2.5 VL 3B...")
    from mlx_vlm import load
    from mlx_vlm.utils import load_config
    model_path = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
    model, processor = load(model_path)
    config = load_config(model_path)
    print("Model loaded!\n")

    # Split video into chunks
    with tempfile.TemporaryDirectory() as tmpdir:
        print("Splitting video into chunks...")
        chunks = split_into_chunks(video_path, tmpdir, args.chunk_size)
        print(f"Created {len(chunks)} chunks\n")

        results = []
        issues = []

        for chunk in chunks:
            i = chunk["index"]
            start = chunk["start"]
            end = chunk["end"]

            if chunk["path"] is None:
                desc = "[FAILED - chunk not created]"
            else:
                desc = analyze_video_chunk(
                    model, processor, config, chunk["path"],
                    context=args.context, fps=args.fps
                )

            content_type = classify_content(desc)
            is_bad = is_garbage(desc)

            result = {
                "chunk": i,
                "start": start,
                "end": end,
                "description": desc,
                "content_type": content_type,
                "is_garbage": is_bad,
            }
            results.append(result)

            status = "⚠️" if is_bad else "✅"
            print(f"  {status} Chunk {i} ({start:.0f}-{end:.0f}s) [{content_type}]")
            print(f"     {desc[:200]}")

            if is_bad:
                issues.append(f"Chunk {i} ({start:.0f}-{end:.0f}s): Model failed to analyze")
            if content_type == 'empty/transition':
                issues.append(f"Chunk {i} ({start:.0f}-{end:.0f}s): Empty/transition content")

    # === ANALYSIS ===
    print(f"\n{'=' * 60}")
    print("DETAILED ANALYSIS")
    print(f"{'=' * 60}")

    valid_results = [r for r in results if not r['is_garbage']]
    content_sequence = [r['content_type'] for r in valid_results]
    print(f"\nContent flow: {' → '.join(content_sequence)}")

    unique_types = set(r['content_type'] for r in valid_results)
    print(f"\nUnique content types: {len(unique_types)}/{len(valid_results)} chunks")
    for ct in unique_types:
        count = sum(1 for r in valid_results if r['content_type'] == ct)
        print(f"  {ct}: {count} chunks")

    # Detect repeated content
    for j in range(len(valid_results) - 1):
        if valid_results[j]['content_type'] == valid_results[j+1]['content_type']:
            d1 = valid_results[j]['description'][:80].lower()
            d2 = valid_results[j+1]['description'][:80].lower()
            common = sum(1 for w in d1.split() if w in d2.split())
            if common > len(d1.split()) * 0.6:
                issues.append(
                    f"Chunks {valid_results[j]['chunk']}-{valid_results[j+1]['chunk']}: "
                    f"Very similar content back-to-back ({valid_results[j]['content_type']})"
                )

    # Recipe step coverage check
    RECIPE_STEPS = {
        'banana prep': ['banana', 'slice', 'bread'],
        'mashing/prep': ['fork', 'mash'],
        'spreading nutella': ['nutella', 'chocolate spread', 'chocolate'],
        'assembling': ['sandwich', 'assembl', 'on top', 'place on top'],
        'heating pan/butter': ['butter', 'melt', 'pan', 'heat'],
        'cooking/toasting': ['toast', 'golden', 'crispy', 'frying', 'cooking'],
        'milk pouring': ['milk', 'pour', 'absorb', 'foamy'],
        'sugar/caramelizing': ['sugar', 'caramel', 'sprinkle'],
        'pressing with spoon': ['spoon', 'press'],
        'plating/serving': ['plate', 'serving', 'plating'],
    }

    print(f"\n{'=' * 60}")
    print("RECIPE STEP COVERAGE")
    print(f"{'=' * 60}")
    all_descs = " ".join(r['description'].lower() for r in valid_results)
    covered = 0
    total_steps = len(RECIPE_STEPS)
    for step_name, keywords in RECIPE_STEPS.items():
        found = any(kw in all_descs for kw in keywords)
        status = "✅" if found else "❌"
        if found:
            covered += 1
            # Find which chunk covers this
            for r in valid_results:
                if any(kw in r['description'].lower() for kw in keywords):
                    print(f"  {status} {step_name} — Chunk {r['chunk']} ({r['start']:.0f}-{r['end']:.0f}s)")
                    break
        else:
            print(f"  {status} {step_name} — NOT FOUND")
            issues.append(f"Missing recipe step: {step_name}")

    print(f"\nCoverage: {covered}/{total_steps} steps")

    # Narrative order check
    IDEAL_FLOW = ['banana prep', 'mashing/prep', 'spreading nutella', 'assembling',
                  'heating pan/butter', 'cooking/toasting', 'milk pouring',
                  'sugar/caramelizing', 'pressing with spoon', 'plating/serving']

    seen_phases = []
    for ct in content_sequence:
        if ct in IDEAL_FLOW:
            idx = IDEAL_FLOW.index(ct)
            seen_phases.append(idx)

    out_of_order = 0
    for k in range(len(seen_phases) - 1):
        if seen_phases[k] > seen_phases[k+1]:
            out_of_order += 1

    if out_of_order > len(seen_phases) * 0.3:
        issues.append(f"Narrative flow: {out_of_order} out-of-order transitions")

    garbage_count = sum(1 for r in results if r['is_garbage'])
    if garbage_count > 0:
        issues.append(f"{garbage_count}/{len(results)} chunks had garbage analysis")

    # === ISSUES ===
    print(f"\n{'=' * 60}")
    print("ISSUES FOUND")
    print(f"{'=' * 60}")
    if issues:
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print("  ✅ No issues found!")

    # === VERDICT ===
    print(f"\n{'=' * 60}")
    print("VERDICT")
    print(f"{'=' * 60}")

    score = 10.0
    score -= garbage_count * 0.5
    score -= out_of_order * 0.5
    score -= (total_steps - covered) * 0.5
    if len(unique_types) < 4:
        score -= 1.0
    score = max(0, min(10, score))

    print(f"  Duration: {duration:.0f}s")
    print(f"  Variety: {len(unique_types)} content types {'✅' if len(unique_types) >= 4 else '⚠️'}")
    print(f"  Narrative: {'✅ good flow' if out_of_order <= 1 else '⚠️ jumpy narrative'}")
    print(f"  Quality: {len(valid_results)}/{len(results)} chunks readable {'✅' if garbage_count == 0 else '⚠️'}")
    print(f"  Recipe coverage: {covered}/{total_steps} steps {'✅' if covered >= total_steps - 2 else '⚠️'}")
    print(f"  Overall score: {score:.1f}/10")

    # Save results
    output_json = video_path.rsplit('.', 1)[0] + '_evaluation.json'
    with open(output_json, 'w') as f:
        json.dump({
            "video": video_path,
            "duration": duration,
            "file_size_mb": file_size,
            "chunk_size": args.chunk_size,
            "fps": args.fps,
            "method": "direct_video_input",
            "chunks": results,
            "issues": issues,
            "content_flow": content_sequence,
            "unique_types": list(unique_types),
            "recipe_coverage": f"{covered}/{total_steps}",
            "score": score,
            "garbage_count": garbage_count,
            "out_of_order": out_of_order,
        }, f, indent=2)
    print(f"\nFull results saved to: {output_json}")


if __name__ == "__main__":
    main()
