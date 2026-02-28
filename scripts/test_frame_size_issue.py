#!/usr/bin/env python3
"""Test: Does Qwen VL 3B fail on large portrait frames but work on resized ones?

This script extracts the SAME frame from the output video twice:
1. Raw (no resize) — likely 1080x1920
2. Resized (max 720px) — same filter used in pipeline

Then runs the VL model on both and compares results.
"""

import os
import subprocess
import sys
import tempfile

VIDEO = "outputs/ccf6e201-534a-41be-b961-b42833120450_final.mp4"
TIMESTAMP = 15.0  # Middle of chunk 1 (the garbage chunk)


def extract_frame(video_path, timestamp, output_path, resize=False):
    cmd = [
        "ffmpeg", "-y", "-ss", f"{timestamp:.2f}", "-i", video_path,
        "-frames:v", "1", "-q:v", "2",
    ]
    if resize:
        cmd += ["-vf", "scale='if(gt(iw,ih),720,-2)':'if(gt(iw,ih),-2,720)'"]
    cmd.append(output_path)
    subprocess.run(cmd, capture_output=True)
    return os.path.exists(output_path) and os.path.getsize(output_path) > 1000


def get_dimensions(image_path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", image_path],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def analyze_frame(model, processor, config, image_path):
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    prompt = (
        "Describe exactly what you see in this image in 2-3 sentences. "
        "Focus on: what objects/food/people are visible, what cooking action is happening, "
        "and the setting. Be specific and factual."
    )
    formatted_prompt = apply_chat_template(processor, config, prompt, num_images=1)
    output = generate(model, processor, formatted_prompt, [image_path], max_tokens=200, verbose=False)
    text = output.text.strip() if hasattr(output, "text") else str(output).strip()
    if "<|endoftext|>" in text:
        text = text.split("<|endoftext|>")[0].strip()
    return text


def main():
    if not os.path.exists(VIDEO):
        print(f"Error: {VIDEO} not found. Run from backend dir.")
        sys.exit(1)

    tmpdir = tempfile.mkdtemp()
    raw_path = os.path.join(tmpdir, "raw.jpg")
    resized_path = os.path.join(tmpdir, "resized.jpg")

    # === Extract frames ===
    print("=" * 60)
    print("TEST: Frame size vs VL model output")
    print("=" * 60)
    print(f"\nSource: {VIDEO}")
    print(f"Timestamp: {TIMESTAMP}s (middle of garbage chunk 1)\n")

    print("1. Extracting RAW frame (no resize)...")
    extract_frame(VIDEO, TIMESTAMP, raw_path, resize=False)
    raw_dims = get_dimensions(raw_path)
    raw_size = os.path.getsize(raw_path)
    print(f"   Dimensions: {raw_dims}")
    print(f"   File size: {raw_size:,} bytes")

    print("\n2. Extracting RESIZED frame (max 720px)...")
    extract_frame(VIDEO, TIMESTAMP, resized_path, resize=True)
    resized_dims = get_dimensions(resized_path)
    resized_size = os.path.getsize(resized_path)
    print(f"   Dimensions: {resized_dims}")
    print(f"   File size: {resized_size:,} bytes")

    # === Load model ===
    print("\n3. Loading Qwen 2.5 VL 3B...")
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

    from mlx_vlm import load
    from mlx_vlm.utils import load_config
    model_path = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
    model, processor = load(model_path)
    config = load_config(model_path)
    print("   Model loaded!\n")

    # === Test RAW frame ===
    print("4. Analyzing RAW frame ({})...".format(raw_dims))
    raw_output = analyze_frame(model, processor, config, raw_path)
    is_garbage_raw = len(raw_output) < 15 or raw_output.count("!") > len(raw_output) * 0.3
    print(f"   Output: {raw_output[:200]}")
    print(f"   Garbage? {'YES ❌' if is_garbage_raw else 'NO ✅'}")

    # === Test RESIZED frame ===
    print("\n5. Analyzing RESIZED frame ({})...".format(resized_dims))
    resized_output = analyze_frame(model, processor, config, resized_path)
    is_garbage_resized = len(resized_output) < 15 or resized_output.count("!") > len(resized_output) * 0.3
    print(f"   Output: {resized_output[:200]}")
    print(f"   Garbage? {'YES ❌' if is_garbage_resized else 'NO ✅'}")

    # === Also test a frame from a WORKING chunk for comparison ===
    print("\n6. Control test: frame from chunk 0 (working chunk) at 5s...")
    control_raw = os.path.join(tmpdir, "control_raw.jpg")
    control_resized = os.path.join(tmpdir, "control_resized.jpg")
    extract_frame(VIDEO, 5.0, control_raw, resize=False)
    extract_frame(VIDEO, 5.0, control_resized, resize=True)
    print(f"   Raw dims: {get_dimensions(control_raw)}")
    print(f"   Resized dims: {get_dimensions(control_resized)}")

    print("   Analyzing raw control frame...")
    control_output = analyze_frame(model, processor, config, control_raw)
    is_garbage_control = len(control_output) < 15 or control_output.count("!") > len(control_output) * 0.3
    print(f"   Output: {control_output[:200]}")
    print(f"   Garbage? {'YES ❌' if is_garbage_control else 'NO ✅'}")

    # === Verdict ===
    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)
    if is_garbage_raw and not is_garbage_resized:
        print("✅ CONFIRMED: Large portrait frames cause garbage output.")
        print("   Resizing to 720px fixes it.")
        print("   FIX: Add resize filter to evaluate_video.py extract_frame()")
    elif is_garbage_raw and is_garbage_resized:
        print("❌ Both failed — issue is NOT frame size alone.")
        print("   The content in chunk 1 might genuinely be problematic.")
    elif not is_garbage_raw and not is_garbage_resized:
        print("🤔 Neither failed — the issue might be intermittent.")
        print("   Could be specific frame timing or model randomness.")
    else:
        print("🤔 Unexpected: raw works but resized fails?!")

    print(f"\nFrames saved in: {tmpdir}")


if __name__ == "__main__":
    main()
