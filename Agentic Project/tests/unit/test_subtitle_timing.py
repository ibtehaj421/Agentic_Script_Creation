"""Phase 3 helper: SRT generation from audio segments."""
from mcp.tools.video_tools.subtitle_tool import write_srt, _fmt_ts


def test_fmt_ts_format():
    assert _fmt_ts(0) == "00:00:00,000"
    assert _fmt_ts(65.5) == "00:01:05,500"


def test_write_srt(tmp_path):
    out = tmp_path / "x.srt"
    write_srt(
        [
            {"start_s": 0.0, "end_s": 2.0, "text": "Hello"},
            {"start_s": 2.0, "end_s": 4.5, "text": "World"},
        ],
        out,
    )
    content = out.read_text()
    assert "1\n00:00:00,000 --> 00:00:02,000\nHello" in content
    assert "2\n00:00:02,000 --> 00:00:04,500\nWorld" in content
