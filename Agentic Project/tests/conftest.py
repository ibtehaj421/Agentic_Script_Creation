"""Shared pytest fixtures + path bootstrap."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

# Trigger tool self-registration exactly once for the test session
import mcp.tools  # noqa: F401


@pytest.fixture
def fake_story_state():
    from shared.schemas import Character, DialogueTurn, PipelineState, Scene, StoryState
    state = PipelineState(job_id="job_test", prompt="Two spies meet on a rooftop", num_scenes=2)
    state.story = StoryState(
        title="Rooftop",
        logline="Two spies meet on a rooftop",
        prompt="Two spies meet on a rooftop",
        scenes=[
            Scene(
                scene_id=1,
                location="Rainy rooftop",
                action="Alpha and Beta meet",
                mood="tense",
                characters=["Alpha", "Beta"],
                dialogue=[
                    DialogueTurn(speaker="Alpha", line="You're late.", emotion="tense"),
                    DialogueTurn(speaker="Beta", line="I was followed.", emotion="tense"),
                ],
            ),
            Scene(
                scene_id=2,
                location="Alleyway",
                action="Alpha and Beta escape",
                mood="urgent",
                characters=["Alpha", "Beta"],
                dialogue=[
                    DialogueTurn(speaker="Alpha", line="We need to move.", emotion="urgent"),
                ],
            ),
        ],
        characters=[
            Character(name="Alpha", role="operative", appearance="tall, short hair, dark trench coat", voice_style="deep"),
            Character(name="Beta", role="informant", appearance="petite, red scarf, sharp eyes", voice_style="crisp"),
        ],
    )
    return state
