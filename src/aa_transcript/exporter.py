import re

from .jobs import Segment


def export_segments(segments: list[Segment], fmt: str = "txt") -> str:
    if fmt == "md":
        return _build_md(segments, timestamps=True)
    if fmt == "md-clean":
        return _build_md(segments, timestamps=False)
    if fmt == "txt-clean":
        return _build_txt(segments, timestamps=False)
    return _build_txt(segments, timestamps=True)


def _ts(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _join_texts(segs: list[Segment]) -> str:
    text = " ".join(s.text for s in segs)
    text = re.sub(r"([.!?])\s*([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ])", r"\1 \2", text)
    return text.strip()


def _group_by_speaker(segments: list[Segment]) -> dict[str, list[Segment]]:
    groups: dict[str, list[Segment]] = {}
    for seg in segments:
        groups.setdefault(seg.speaker, []).append(seg)
    return groups


def _build_txt(segments: list[Segment], timestamps: bool) -> str:
    groups = _group_by_speaker(segments)
    lines = []

    for speaker, segs in groups.items():
        lines.append(f"=== {speaker.upper()} ===")
        if timestamps:
            for s in segs:
                lines.append(f"[{_ts(s.start)}] {s.text}")
        else:
            lines.append(_join_texts(segs))
        lines.append("")

    if not lines:
        lines.append("(nenhuma transcrição registrada)")

    return "\n".join(lines).strip()


def _build_md(segments: list[Segment], timestamps: bool) -> str:
    groups = _group_by_speaker(segments)
    lines = ["# Transcrição\n"]

    for speaker, segs in groups.items():
        lines.append(f"## {speaker}\n")
        if timestamps:
            for s in segs:
                lines.append(f"- **{_ts(s.start)}** {s.text}")
        else:
            lines.append(_join_texts(segs))
        lines.append("")

    if len(lines) == 1:
        lines.append("*(nenhuma transcrição registrada)*")

    return "\n".join(lines).strip()
