"""Phase 1 — Story, Script & Character Design.

Pipeline:
    prompt → LLM story draft → validate → LLM character roster → validate
          → (parallel) per-character portrait images → write to state

Every step logs a structured event so the web UI can show progress.
"""
from __future__ import annotations

from typing import Any

from mcp.tool_executor import ToolExecutor
from shared.schemas import Character, PipelineState, PhaseStatus, StoryState
from shared.utils import emit

from .planner import normalise_characters, normalise_story


def run_story_phase(
    state: PipelineState,
    job_id: str | None = None,
    directive: str = "",
) -> PipelineState:
    """Generate story + characters + portraits. Mutates and returns state.

    `directive` is an optional free-text instruction layered on top of the
    original prompt — used by the edit agent's `regenerate_script` path to
    pass the user's editing intent (e.g. "make Jack agree with Ava about
    the aliens") into the LLM call without overwriting state.prompt.
    """
    job_id = job_id or state.job_id
    state.phase_status["story"] = PhaseStatus.RUNNING
    emit(job_id, "story", "phase_start", {"directive": directive} if directive else None)

    ex = ToolExecutor(job_id=job_id)

    # 1. Generate story
    emit(job_id, "story", "story_gen_start")
    effective_prompt = (
        f"{state.prompt}\n\nADDITIONAL DIRECTIVE FROM USER: {directive}"
        if directive else state.prompt
    )
    story_raw = ex.execute(
        "generate_story",
        prompt=effective_prompt,
        num_scenes=state.num_scenes,
        style=state.style,
    )
    story = normalise_story(story_raw, state.prompt)

    # 2. Generate character roster
    emit(job_id, "story", "character_design_start", {"scene_count": len(story.scenes)})
    char_raw = ex.execute(
        "design_characters",
        scene_manifest={"scenes": [s.model_dump() for s in story.scenes]},
    )
    characters = normalise_characters(char_raw)

    # Ensure every scene-mentioned character has a record
    mentioned = {c for s in story.scenes for c in s.characters}
    known = {c.name for c in characters}
    for missing in mentioned - known:
        characters.append(
            Character(
                name=missing,
                role="supporting",
                personality_traits=["driven"],
                appearance=f"an individual fitting the {story.logline[:80]} setting",
                voice_style="neutral",
                reference_style=state.style,
            )
        )

    story.characters = characters
    state.story = story
    emit(
        job_id, "story", "script_drafted",
        {"scenes": len(story.scenes), "characters": len(story.characters)},
    )

    # 3. Portraits for every character
    run_character_images(state, job_id=job_id)

    state.phase_status["story"] = PhaseStatus.DONE
    emit(job_id, "story", "phase_done")
    return state


def run_character_images(state: PipelineState, job_id: str | None = None) -> PipelineState:
    """Regenerate the portrait image for every character that lacks one.

    Factored out so the edit agent can call it targeted."""
    job_id = job_id or state.job_id
    ex = ToolExecutor(job_id=job_id)
    for c in state.story.characters:
        if c.image_path:
            continue
        path = ex.execute(
            "generate_character_portrait",
            name=c.name,
            appearance=c.appearance,
            reference_style=c.reference_style,
        )
        c.image_path = path
        emit(job_id, "story", "portrait_ready", {"character": c.name, "path": path})
    return state
