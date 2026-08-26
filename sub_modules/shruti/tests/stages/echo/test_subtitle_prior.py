from shruti.stages.echo.subtitle_prior import parse_subtitle_file, align_subtitle_prior
from shruti.contracts.speech import Utterance


def test_parse_subtitle_file_reads_basic_vtt(tmp_path):
    vtt = tmp_path / "captions.vtt"
    vtt.write_text(
        "WEBVTT\n\n"
        "1\n00:00:01.000 --> 00:00:03.500\nHello there\n\n"
        "2\n00:00:04.000 --> 00:00:06.000\nSecond line\n"
    )
    segments = parse_subtitle_file(str(vtt))
    assert segments[0] == {"start_s": 1.0, "end_s": 3.5, "text": "Hello there"}
    assert segments[1]["start_s"] == 4.0


def test_align_subtitle_prior_prefers_subtitle_timing_keeps_model_text():
    utterances = [Utterance(id="u1", recording_id="r1", start_s=0.8, end_s=3.6,
                             text="Hello there (model transcription)", speaker="TEACHER")]
    segments = [{"start_s": 1.0, "end_s": 3.5, "text": "Hello there"}]
    aligned = align_subtitle_prior(utterances, segments)
    assert aligned[0].start_s == 1.0
    assert aligned[0].end_s == 3.5
    assert aligned[0].text == "Hello there (model transcription)"
