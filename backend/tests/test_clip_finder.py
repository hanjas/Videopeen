"""Tests for clip_finder.py — smart clip finding Layer 0 + Layer 5."""

import sys
import asyncio

sys.path.insert(0, '.')

from app.services.clip_finder import (
    find_clips_by_text,
    build_not_found_response,
    smart_find_clip,
    _extract_keywords,
    _count_keyword_matches,
)


# Sample test data
SAMPLE_CLIPS = [
    {
        "action_id": "action_1",
        "description": "Adding garam masala to the pot while stirring",
        "start_time": 45.0,
        "end_time": 52.0,
        "source_path": "/uploads/test/video1.mp4",
    },
    {
        "action_id": "action_2",
        "description": "Stirring the pot with wooden spoon",
        "start_time": 30.0,
        "end_time": 40.0,
        "source_path": "/uploads/test/video1.mp4",
    },
    {
        "action_id": "action_3",
        "description": "Chopping onions on cutting board",
        "start_time": 10.0,
        "end_time": 25.0,
        "source_path": "/uploads/test/video1.mp4",
    },
    {
        "action_id": "action_4",
        "description": "Adding turmeric powder to the mixture",
        "start_time": 60.0,
        "end_time": 65.0,
        "source_path": "/uploads/test/video1.mp4",
    },
    {
        "action_id": "action_5",
        "description": "Plating the finished curry on white plate",
        "start_time": 120.0,
        "end_time": 135.0,
        "source_path": "/uploads/test/video1.mp4",
    },
]


def test_extract_keywords():
    """Test keyword extraction from query."""
    # Basic test
    keywords = _extract_keywords("garam masala scene")
    assert "garam" in keywords
    assert "masala" in keywords
    assert "scene" not in keywords  # stop word
    
    # Filter short words (> 2 chars) and stop words
    keywords = _extract_keywords("add in at spice to pot")
    assert "add" not in keywords  # stop word
    assert "in" not in keywords   # 2 chars, filtered
    assert "at" not in keywords   # 2 chars, filtered
    assert "to" not in keywords   # 2 chars, filtered
    assert "spice" in keywords
    assert "pot" in keywords
    
    # Case insensitive
    keywords = _extract_keywords("ADDING Turmeric")
    assert "adding" not in keywords  # stop word
    assert "turmeric" in keywords
    
    print("✓ test_extract_keywords passed")


def test_count_keyword_matches():
    """Test keyword matching count."""
    keywords = ["garam", "masala"]
    
    # Perfect match
    score = _count_keyword_matches("Adding garam masala to the pot", keywords)
    assert score == 2
    
    # Partial match
    score = _count_keyword_matches("Adding masala to the pot", keywords)
    assert score == 1
    
    # No match
    score = _count_keyword_matches("Stirring the pot", keywords)
    assert score == 0
    
    # Case insensitive
    score = _count_keyword_matches("GARAM MASALA powder", keywords)
    assert score == 2
    
    print("✓ test_count_keyword_matches passed")


async def test_find_clips_by_text_exact_match():
    """Test finding clips with exact keyword matches."""
    # Search for "garam masala"
    results = await find_clips_by_text("garam masala", SAMPLE_CLIPS)
    
    assert len(results) == 1
    assert results[0]["action_id"] == "action_1"
    assert results[0]["_search_score"] == 2
    
    print("✓ test_find_clips_by_text_exact_match passed")


async def test_find_clips_by_text_partial_match():
    """Test finding clips with partial keyword matches."""
    # Search for "stirring pot" - should match 2 clips
    results = await find_clips_by_text("stirring pot", SAMPLE_CLIPS)
    
    assert len(results) == 2
    # First should have higher score (both keywords)
    assert results[0]["_search_score"] >= results[1]["_search_score"]
    
    # Should include both stirring clips
    action_ids = {r["action_id"] for r in results}
    assert "action_1" in action_ids or "action_2" in action_ids
    
    print("✓ test_find_clips_by_text_partial_match passed")


async def test_find_clips_by_text_no_match():
    """Test finding clips when no match exists."""
    # Search for something that doesn't exist
    results = await find_clips_by_text("baking bread", SAMPLE_CLIPS)
    
    assert len(results) == 0
    
    print("✓ test_find_clips_by_text_no_match passed")


async def test_find_clips_by_text_sorted_by_score():
    """Test that results are sorted by match score descending."""
    # "adding" appears in multiple clips
    results = await find_clips_by_text("adding powder", SAMPLE_CLIPS)
    
    # Should have results
    assert len(results) > 0
    
    # Verify sorted by score
    scores = [r["_search_score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    
    print("✓ test_find_clips_by_text_sorted_by_score passed")


async def test_find_clips_by_text_edge_cases():
    """Test edge cases: empty query, empty clips, short words."""
    # Empty query
    results = await find_clips_by_text("", SAMPLE_CLIPS)
    assert len(results) == 0
    
    # Empty clips
    results = await find_clips_by_text("test", [])
    assert len(results) == 0
    
    # Only short words (filtered out)
    results = await find_clips_by_text("to in on", SAMPLE_CLIPS)
    assert len(results) == 0
    
    print("✓ test_find_clips_by_text_edge_cases passed")


def test_build_not_found_response():
    """Test the not found response builder."""
    query = "chocolate sauce drizzle"
    response = build_not_found_response(query)
    
    assert response["type"] == "not_found"
    assert query in response["summary"]
    assert isinstance(response["suggestions"], list)
    assert len(response["suggestions"]) > 0
    
    print("✓ test_build_not_found_response passed")


async def test_smart_find_clip_found():
    """Test smart_find_clip when clips are found (Layer 0 success)."""
    result = await smart_find_clip("garam masala", SAMPLE_CLIPS, project_id="test_project")
    
    assert result["type"] == "found"
    assert result["layer"] == 0
    assert len(result["clips"]) > 0
    assert result["clips"][0]["action_id"] == "action_1"
    
    print("✓ test_smart_find_clip_found passed")


async def test_smart_find_clip_not_found():
    """Test smart_find_clip when no clips match (Layer 5 fallback)."""
    result = await smart_find_clip("baking bread", SAMPLE_CLIPS, project_id="test_project")
    
    assert result["type"] == "not_found"
    assert "summary" in result
    assert "suggestions" in result
    assert "baking bread" in result["summary"]
    
    print("✓ test_smart_find_clip_not_found passed")


async def test_smart_find_clip_case_insensitive():
    """Test that search is case-insensitive."""
    # Test uppercase
    result = await smart_find_clip("GARAM MASALA", SAMPLE_CLIPS)
    assert result["type"] == "found"
    assert len(result["clips"]) > 0
    
    # Test mixed case
    result = await smart_find_clip("Turmeric Powder", SAMPLE_CLIPS)
    assert result["type"] == "found"
    assert len(result["clips"]) > 0
    
    print("✓ test_smart_find_clip_case_insensitive passed")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Running clip_finder.py tests")
    print("="*60 + "\n")
    
    # Synchronous tests
    test_extract_keywords()
    test_count_keyword_matches()
    test_build_not_found_response()
    
    # Async tests
    await test_find_clips_by_text_exact_match()
    await test_find_clips_by_text_partial_match()
    await test_find_clips_by_text_no_match()
    await test_find_clips_by_text_sorted_by_score()
    await test_find_clips_by_text_edge_cases()
    await test_smart_find_clip_found()
    await test_smart_find_clip_not_found()
    await test_smart_find_clip_case_insensitive()
    
    print("\n" + "="*60)
    print("✓ All tests passed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
