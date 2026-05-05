"""Wav2Lip wrappers and mouth-region blend compositor.

`Wav2LipClipTool` runs the third_party/Wav2Lip inference script on a
portrait + audio pair and returns a video-only MP4 sized to match our
ken_burns output (TARGET_WIDTH × TARGET_HEIGHT, top-aligned crop, h264).

`MouthBlendClipTool` is the production close-up renderer: it produces
a static high-resolution clip from the portrait, generates a wav2lip
lip-sync clip, and blends only the mouth region from wav2lip onto the
sharp portrait via a feathered elliptical alpha mask. This avoids the
whole-frame softness wav2lip's 96×96 face-patch causes when used as
the full visual — the patch only ever touches the small mouth area,
the rest of the frame stays at native portrait resolution.

`LipsyncOverlayTool` is an alternative compositor that puts the wav2lip
clip in a corner inset (sign-language-window style); kept around but
no longer the default close-up path.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageFilter

from config import VIDEO_DIR
from mcp.base_tool import BaseTool, ToolSpec
from shared.constants import TARGET_FPS, TARGET_HEIGHT, TARGET_WIDTH
from shared.utils import hash_short, job_dir, video_encoder_args


# Repo-relative path to the cloned Wav2Lip source. Inference.py imports
# `audio`, `models`, `hparams` as top-level modules so the subprocess
# must run with this as cwd.
_WAV2LIP_DIR = Path(__file__).resolve().parents[3] / "third_party" / "Wav2Lip"
_WAV2LIP_CKPT = _WAV2LIP_DIR / "checkpoints" / "wav2lip_gan.pth"

# Wav2Lip's inference resizes the source frame to (out_height*aspect, out_height)
# before the lip-sync pass. If we set this below the source image height we
# burn quality on a downscale that we then have to upscale back out for the
# concat target. Default to 720 — Wav2Lip's documented best-quality setting,
# and ≥ our typical portrait height (768) so the source isn't shrunk.
_MIN_OUT_HEIGHT = 720


class Wav2LipClipTool(BaseTool):
    spec = ToolSpec(
        name="wav2lip_clip",
        description=(
            "Lip-sync a still portrait to a dialogue WAV via Wav2Lip. "
            "Returns a video-only MP4 sized to TARGET_WIDTH×TARGET_HEIGHT, "
            "ready to feed into compose_scene as if it were a ken_burns clip."
        ),
        category="video",
        schema={"image_path": "str", "audio_path": "str"},
    )

    def run(self, image_path: str, audio_path: str, job_id: str | None = None) -> str:
        if not _WAV2LIP_CKPT.exists():
            raise RuntimeError(f"wav2lip checkpoint missing at {_WAV2LIP_CKPT}")

        src = Path(image_path)
        out_dir = job_dir(VIDEO_DIR, job_id)

        # Match wav2lip's working height to the source so the source isn't
        # downscaled before the lip-sync pass; clamp to a floor so very small
        # portraits still get a usable resolution.
        try:
            with Image.open(image_path) as im:
                src_h = im.size[1]
        except Exception:
            src_h = _MIN_OUT_HEIGHT
        out_height = max(_MIN_OUT_HEIGHT, src_h)

        key = hash_short(
            f"{image_path}|{audio_path}|{TARGET_WIDTH}x{TARGET_HEIGHT}|h{out_height}|wav2lip_gan"
        )
        out = out_dir / f"w2l_{src.stem}_{key}.mp4"
        if out.exists():
            return str(out)

        raw = out_dir / f"w2l_raw_{src.stem}_{key}.mp4"

        # The inference script writes intermediate files into Wav2Lip/temp/
        # and reads its checkpoint with a relative path, so we must run it
        # with cwd=_WAV2LIP_DIR. Absolute paths for face/audio/outfile keep
        # the IO independent of cwd.
        cmd = [
            "python3",
            "inference.py",
            "--checkpoint_path", str(_WAV2LIP_CKPT.relative_to(_WAV2LIP_DIR)),
            "--face", str(Path(image_path).resolve()),
            "--audio", str(Path(audio_path).resolve()),
            "--outfile", str(raw.resolve()),
            "--pads", "0", "20", "0", "0",
            "--out_height", str(out_height),
            "--fps", str(TARGET_FPS),
        ]
        (_WAV2LIP_DIR / "temp").mkdir(exist_ok=True)
        subprocess.run(cmd, cwd=str(_WAV2LIP_DIR), check=True, capture_output=True, text=True)

        if not raw.exists():
            raise RuntimeError("wav2lip produced no output")

        # Strip audio and re-encode at TARGET_WIDTH×TARGET_HEIGHT with the
        # same top-aligned crop ken_burns uses, so this clip can be concat'd
        # alongside ken_burns clips without filter_complex stitching.
        # Lanczos preserves face detail better than bilinear on the upscale
        # to TARGET_WIDTH; the wav2lip face patch is the resolution
        # bottleneck so any softness here compounds visibly.
        vf = (
            f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={TARGET_WIDTH}:{TARGET_HEIGHT}:(iw-{TARGET_WIDTH})/2:0,"
            f"fps={TARGET_FPS}"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(raw),
                "-an",
                "-vf", vf,
                *video_encoder_args(bitrate="10M"),
                str(out),
            ],
            check=True,
        )

        # Best-effort cleanup of the intermediate; harmless if it already vanished.
        try:
            raw.unlink()
        except OSError:
            pass

        return str(out)


# Mouth-blend ellipse sizing as fractions of frame dims. Chosen empirically
# so the ellipse covers a typical talking mouth + chin area with feathered
# edges that hide the wav2lip↔portrait seam. Tuneable per portrait if
# specific characters need a tighter/looser region.
_MOUTH_ELLIPSE_W_FRAC = 0.18    # ellipse width  ≈ 184 px on 1024-wide frame
_MOUTH_ELLIPSE_H_FRAC = 0.18    # ellipse height ≈ 104 px on 576-tall frame
_MOUTH_FEATHER_FRAC   = 0.04    # gaussian-blur radius for the alpha edge

# Quality-recovery chain on the wav2lip stream before alpha-blending. The
# 96×96 internal face patch upscales to ~250 px in our 1024-wide frame and
# is perceptibly softer than the rest of the portrait — but only the mouth
# ellipse pulls from this stream, so we can be aggressive without
# affecting the rest of the frame.
#
# Stages:
#   1. 2× lanczos upscale → re-resolves the soft pixels at higher density
#      so downstream sharpening operates on more detail.
#   2. Two-radius unsharp → hits both fine (3 px) and mid (7 px) detail
#      bands; chained passes produce more visible improvement than one
#      large-radius pass without the halo cost.
#   3. cas (AMD contrast-adaptive sharpening) → halo-free crispening
#      designed exactly for upscaled content; finishes the job.
#   4. Lanczos downscale back to TARGET so the layer matches the base.
_W2L_UPSCALE_CHAIN = (
    f"scale=iw*2:ih*2:flags=lanczos,"
    f"unsharp=lx=3:ly=3:la=1.2:cx=3:cy=3:ca=0.6,"
    f"unsharp=lx=7:ly=7:la=0.8:cx=7:cy=7:ca=0.4,"
    f"cas=strength=0.7,"
    f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:flags=lanczos"
)


def _detect_mouth_xy(image_path: str) -> tuple[float, float] | None:
    """Return (mx, my) in source-image pixel coords, or None if no face.
    Lazy-imports batch_face so the tool module loads cheaply when wav2lip
    isn't actually used."""
    from batch_face import RetinaFace
    img = cv2.imread(str(image_path))
    if img is None:
        return None
    det = RetinaFace(model_path=None, network="mobilenet")
    results = det([img])
    if not results or not results[0]:
        return None
    box, lm, score = results[0][0]
    # batch_face landmark order: [le, re, nose, mouth_l, mouth_r]
    mx = (lm[3][0] + lm[4][0]) / 2
    my = (lm[3][1] + lm[4][1]) / 2
    # Drop a hair below the lip-corner line so the ellipse covers the
    # opening jaw too — speakers' jaws drop ~10-15% of face-height when
    # they articulate, and mask alignment matters more on open vowels.
    face_h = box[3] - box[1]
    my += face_h * 0.07
    return (mx, my)


def _portrait_to_target_xy(image_path: str, src_x: float, src_y: float) -> tuple[float, float]:
    """Map a coordinate from source-portrait space to TARGET_WIDTH×TARGET_HEIGHT
    space, using the same scale + top-aligned crop our ken_burns / wav2lip
    pipelines apply (force_aspect=increase, crop top-aligned)."""
    with Image.open(image_path) as im:
        sw, sh = im.size
    scale = max(TARGET_WIDTH / sw, TARGET_HEIGHT / sh)
    scaled_w, scaled_h = sw * scale, sh * scale
    # Center horizontally, top-aligned vertically (matches ken_burns crop)
    crop_x_off = (scaled_w - TARGET_WIDTH) / 2
    crop_y_off = 0
    return (src_x * scale - crop_x_off, src_y * scale - crop_y_off)


def _build_mouth_alpha_mask(image_path: str, out_path: Path) -> Path:
    """Generate (or reuse) a TARGET_WIDTH×TARGET_HEIGHT grayscale PNG: white
    feathered ellipse over the mouth, black elsewhere. Used as alpha when
    blending wav2lip output onto the static portrait base."""
    if out_path.exists():
        return out_path
    mouth = _detect_mouth_xy(image_path)
    if mouth is None:
        # No detectable face — fall back to a fixed lower-third ellipse so
        # the blend still works on stylised illustrations RetinaFace misses.
        cx, cy = TARGET_WIDTH / 2, TARGET_HEIGHT * 0.72
    else:
        cx, cy = _portrait_to_target_xy(image_path, *mouth)
    ew = max(80, int(TARGET_WIDTH * _MOUTH_ELLIPSE_W_FRAC))
    eh = max(60, int(TARGET_HEIGHT * _MOUTH_ELLIPSE_H_FRAC))
    feather = max(6, int(TARGET_HEIGHT * _MOUTH_FEATHER_FRAC))

    mask = Image.new("L", (TARGET_WIDTH, TARGET_HEIGHT), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(
        (cx - ew / 2, cy - eh / 2, cx + ew / 2, cy + eh / 2),
        fill=255,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(radius=feather))
    mask.save(out_path)
    return out_path


class MouthBlendClipTool(BaseTool):
    spec = ToolSpec(
        name="mouth_blend_clip",
        description=(
            "Produce a dialogue close-up where only the mouth region is from "
            "wav2lip lip-sync; the rest of the frame is the native-resolution "
            "portrait, eliminating the whole-frame softness of bare wav2lip."
        ),
        category="video",
        schema={"image_path": "str", "audio_path": "str", "duration_s": "float"},
    )

    def run(
        self,
        image_path: str,
        audio_path: str,
        duration_s: float | None = None,
        job_id: str | None = None,
    ) -> str:
        out_dir = job_dir(VIDEO_DIR, job_id)
        src = Path(image_path)
        key = hash_short(
            f"{image_path}|{audio_path}|{duration_s}|"
            f"e{_MOUTH_ELLIPSE_W_FRAC}x{_MOUTH_ELLIPSE_H_FRAC}|"
            f"upscale_cas|mouthblend_v3"
        )
        out = out_dir / f"mb_{src.stem}_{key}.mp4"
        if out.exists():
            return str(out)

        # Lip-sync clip — full-frame wav2lip output, slightly soft.
        w2l_clip = Wav2LipClipTool().run(
            image_path=image_path, audio_path=audio_path, job_id=job_id,
        )

        # Mouth-region alpha mask, cached per portrait so multiple lines from
        # the same speaker reuse it. Filename embeds the ellipse fractions so
        # tweaking them invalidates the cache automatically.
        mask_dir = out_dir / "_masks"
        mask_dir.mkdir(parents=True, exist_ok=True)
        mask_key = hash_short(
            f"{image_path}|{_MOUTH_ELLIPSE_W_FRAC}|{_MOUTH_ELLIPSE_H_FRAC}|{_MOUTH_FEATHER_FRAC}",
            8,
        )
        mask_path = _build_mouth_alpha_mask(
            image_path, mask_dir / f"mouthmask_{src.stem}_{mask_key}.png"
        )

        # Drive everything off the wav2lip clip's exact duration so the still
        # image inputs (portrait + mask) stop with it. `-loop 1 -t <dur>` on
        # the stills + `-shortest` would also work, but anchoring via probe
        # keeps the maths in one place and avoids a redundant -t guess.
        from shared.utils import probe_duration as _probe
        w2l_dur = _probe(w2l_clip)

        # The blend: wav2lip ⊗ mask (alpha) → overlaid on the static portrait
        # base. setpts=PTS-STARTPTS on the looped stills + eof_action=endall
        # on the overlay terminates the output the moment the wav2lip stream
        # ends, even though the still inputs are conceptually infinite.
        fc = (
            f"[0:v]"
            f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={TARGET_WIDTH}:{TARGET_HEIGHT}:(iw-{TARGET_WIDTH})/2:0,"
            f"fps={TARGET_FPS},setsar=1,setpts=PTS-STARTPTS[base];"
            f"[2:v]format=gray,setpts=PTS-STARTPTS[mask];"
            f"[1:v]setpts=PTS-STARTPTS,{_W2L_UPSCALE_CHAIN}[lipv];"
            f"[lipv][mask]alphamerge[lipa];"
            f"[base][lipa]overlay=0:0:format=auto:eof_action=endall:shortest=1"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-loop", "1", "-t", f"{w2l_dur:.3f}", "-i", str(image_path),  # 0: portrait still
                "-i", str(w2l_clip),                                             # 1: wav2lip clip
                "-loop", "1", "-t", f"{w2l_dur:.3f}", "-i", str(mask_path),    # 2: alpha mask
                "-filter_complex", fc,
                "-an",
                *video_encoder_args(bitrate="10M"),
                str(out),
            ],
            check=True,
            timeout=120,
        )
        return str(out)


# Lip-sync inset size as a fraction of frame height — keeps the inset
# proportional across resolutions and small enough that wav2lip's 96×96
# face-patch softness isn't dominant in the final frame.
_INSET_HEIGHT_FRAC = 0.32
_INSET_MARGIN_FRAC = 0.04


class LipsyncOverlayTool(BaseTool):
    spec = ToolSpec(
        name="lipsync_overlay",
        description=(
            "Composite a lip-sync clip as a small circular inset onto a "
            "full-resolution base clip. Output matches base resolution + fps."
        ),
        category="video",
        schema={"base_video": "str", "lipsync_video": "str"},
    )

    def run(
        self,
        base_video: str,
        lipsync_video: str,
        position: str = "bottom_right",
        job_id: str | None = None,
    ) -> str:
        out_dir = job_dir(VIDEO_DIR, job_id)
        key = hash_short(f"{base_video}|{lipsync_video}|{position}|inset_v1")
        out = out_dir / f"w2lov_{Path(base_video).stem}_{key}.mp4"
        if out.exists():
            return str(out)

        size = max(96, int(TARGET_HEIGHT * _INSET_HEIGHT_FRAC))
        # Round to even — h264 chokes on odd width/height.
        if size % 2:
            size -= 1
        margin = max(16, int(TARGET_HEIGHT * _INSET_MARGIN_FRAC))

        if position == "bottom_left":
            xy = f"x={margin}:y=H-h-{margin}"
        elif position == "top_right":
            xy = f"x=W-w-{margin}:y={margin}"
        elif position == "top_left":
            xy = f"x={margin}:y={margin}"
        else:  # bottom_right
            xy = f"x=W-w-{margin}:y=H-h-{margin}"

        # The wav2lip clip is always TARGET_WIDTH × TARGET_HEIGHT (the wav2lip
        # wrapper enforces this), so we can hardcode the centre-square crop
        # rather than using min(iw,ih) — ffmpeg's filter parser treats the
        # parens as graph delimiters even when quoted.
        crop_x = (TARGET_WIDTH - TARGET_HEIGHT) // 2
        fc = (
            f"[1:v]crop={TARGET_HEIGHT}:{TARGET_HEIGHT}:{crop_x}:0,"
            f"scale={size}:{size}:flags=lanczos[inset];"
            f"[0:v][inset]overlay={xy}:format=auto"
        )

        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(base_video),
                "-i", str(lipsync_video),
                "-filter_complex", fc,
                "-an",
                *video_encoder_args(bitrate="10M"),
                str(out),
            ],
            check=True,
        )

        return str(out)
