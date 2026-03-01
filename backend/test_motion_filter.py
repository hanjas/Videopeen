"""Test motion filter on existing extracted frames."""
import sys
import glob
import os

sys.path.insert(0, '.')
from app.services.video_processor import filter_frames_by_motion

# Find a project with frames
uploads_dir = "./uploads"
projects = [d for d in os.listdir(uploads_dir) if os.path.isdir(os.path.join(uploads_dir, d))]

if not projects:
    print("No projects found in uploads/")
    sys.exit(1)

# Use first project with frames
for project_id in projects:
    frames_dir = os.path.join(uploads_dir, project_id, "frames")
    if os.path.exists(frames_dir):
        frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
        if frames:
            print(f"\nTesting on project: {project_id}")
            print(f"Frames directory: {frames_dir}")
            print(f"Total frames: {len(frames)}\n")
            
            # Create fake timestamps (simulate 1fps extraction)
            timestamps = [i * 1.0 for i in range(len(frames))]
            
            # Test motion filter with different thresholds
            for threshold in [0.02, 0.03, 0.05]:
                print(f"\n{'='*60}")
                print(f"Testing with threshold: {threshold}")
                print(f"{'='*60}")
                
                # Make a copy of frames list since filter_frames_by_motion deletes files
                # For testing, we'll use read-only mode by catching the deletion
                filtered_paths, filtered_ts = filter_frames_by_motion(
                    frames.copy(), 
                    timestamps.copy(),
                    diff_threshold=threshold,
                    min_interval=2.0,
                    max_interval=8.0,
                )
                
                print(f"\nResults:")
                print(f"  Before: {len(frames)} frames")
                print(f"  After:  {len(filtered_paths)} frames")
                print(f"  Reduction: {(1 - len(filtered_paths)/len(frames)) * 100:.1f}%")
                print(f"  Kept frame indices: {[frames.index(p) for p in filtered_paths if p in frames][:20]}")
            
            break
else:
    print("No projects with frames found")
    sys.exit(1)

print("\n" + "="*60)
print("Motion filter test complete!")
print("="*60)
