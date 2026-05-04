"""Phase 1 normaliser smoke test (no LLM call)."""
from agents.story_agent.planner import normalise_characters, normalise_story


def test_normalise_story_fills_defaults():
    raw = {
        "title": "Skies",
        "logline": "A jet crash",
        "scenes": [
            {"scene_id": 1, "location": "Cockpit", "action": "alarms blare",
             "mood": "URGENT", "characters": ["Pilot"],
             "dialogue": [{"speaker": "Pilot", "line": "Mayday!", "visual_cue": "flames", "emotion": "Panicked"}]}
        ],
    }
    story = normalise_story(raw, prompt="p")
    assert story.title == "Skies"
    assert story.scenes[0].mood == "urgent"
    assert story.scenes[0].dialogue[0].emotion == "panicked"


def test_normalise_characters_handles_list_appearance():
    raw = {"characters": [
        {"name": "Z", "appearance": ["tall", "red hair"], "personality_traits": ["brave"]}
    ]}
    chars = normalise_characters(raw)
    assert chars[0].appearance == "tall, red hair"
    assert chars[0].name == "Z"
