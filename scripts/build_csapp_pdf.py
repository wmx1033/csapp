#!/usr/bin/env python3
"""Build a single PDF from the markdown files listed in SUMMARY.md."""
from __future__ import annotations

import argparse
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "SUMMARY.md"
DEFAULT_PDF_PATH = ROOT / "csapp.pdf"
DEFAULT_MD_PATH = ROOT / "csapp.md"


def extract_summary_entries(summary_text: str) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    for line in summary_text.splitlines():
        match = re.search(r"\[([^\]]+)\]\(([^)]+\.md)\)", line)
        if not match:
            continue
        title, rel_path = match.groups()
        entries.append((title.strip(), ROOT / rel_path))
    return entries


def normalize_markdown(markdown: str) -> list[str]:
    lines: list[str] = []
    in_code_block = False
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if line.strip().startswith("{%"):
            continue
        if in_code_block:
            lines.append(f"    {line}")
            continue
        image_match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
        if image_match:
            alt_text = image_match.group(1).strip() or "Image"
            lines.append(f"[Image: {alt_text}]")
            continue
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        line = re.sub(r"__([^_]+)__", r"\1", line)
        line = re.sub(r"_([^_]+)_", r"\1", line)
        line = re.sub(r"<[^>]+>", "", line)
        heading_match = re.match(r"^(#+)\s*(.*)", line)
        if heading_match:
            heading_text = heading_match.group(2).strip()
            if heading_text:
                lines.append(heading_text)
                lines.append("")
            continue
        lines.append(line)
    return lines


def wrap_lines(lines: list[str], width: int = 90) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if not line.strip():
            wrapped.append("")
            continue
        indent = re.match(r"^(\s*)", line).group(1)
        content = line.strip()
        wrapped_lines = textwrap.wrap(
            content,
            width=width,
            initial_indent=indent,
            subsequent_indent=indent,
            replace_whitespace=False,
        )
        wrapped.extend(wrapped_lines or [indent])
    return wrapped


def build_pdf(lines: list[str], output_path: Path) -> None:
    lines_per_page = 46
    page_width = 612
    page_height = 792
    margin_left = 72
    start_y = 720
    leading = 14

    def escape_pdf_text(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content_streams = []
    for page_start in range(0, len(lines), lines_per_page):
        page_lines = lines[page_start : page_start + lines_per_page]
        content_lines = [
            "BT",
            "/F1 12 Tf",
            f"{leading} TL",
            f"{margin_left} {start_y} Td",
        ]
        for line in page_lines:
            content_lines.append(f"({escape_pdf_text(line)}) Tj")
            content_lines.append("T*")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("utf-8")
        content_streams.append(stream)

    objects: list[bytes] = []

    def add_obj(content: bytes) -> None:
        objects.append(content)

    add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")

    pages_kids = []
    page_objects_start = 3
    content_objects_start = page_objects_start + len(content_streams)

    for idx in range(len(content_streams)):
        page_obj_num = page_objects_start + idx
        pages_kids.append(f"{page_obj_num} 0 R")

    pages_obj = f"<< /Type /Pages /Kids [{' '.join(pages_kids)}] /Count {len(content_streams)} >>"
    add_obj(pages_obj.encode("utf-8"))

    for idx, stream in enumerate(content_streams):
        content_obj_num = content_objects_start + idx
        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Contents {content_obj_num} 0 R /Resources << /Font << /F1 {content_objects_start + len(content_streams)} 0 R >> >> >>"
        )
        add_obj(page_obj.encode("utf-8"))

    for stream in content_streams:
        stream_obj = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        add_obj(stream_obj)

    add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf_header = b"%PDF-1.4\n"
    offsets = [0]
    current_offset = len(pdf_header)
    body_parts = []

    for index, content in enumerate(objects, start=1):
        obj_bytes = f"{index} 0 obj\n".encode("utf-8") + content + b"\nendobj\n"
        offsets.append(current_offset)
        body_parts.append(obj_bytes)
        current_offset += len(obj_bytes)

    xref_start = current_offset
    xref_lines = [f"xref\n0 {len(objects) + 1}"]
    xref_lines.append("0000000000 65535 f ")
    for offset in offsets[1:]:
        xref_lines.append(f"{offset:010d} 00000 n ")
    xref = "\n".join(xref_lines).encode("utf-8")

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n"
    ).encode("utf-8")

    output_path.write_bytes(pdf_header + b"".join(body_parts) + xref + b"\n" + trailer)


def build_combined_markdown(entries: list[tuple[str, Path]]) -> list[str]:
    combined_lines: list[str] = []
    for title, path in entries:
        combined_lines.append(f"# {title}")
        combined_lines.append("")
        if not path.exists():
            combined_lines.append(f"[Missing file: {path.relative_to(ROOT)}]")
            combined_lines.append("")
            continue
        markdown = path.read_text(encoding="utf-8")
        combined_lines.append(markdown.rstrip())
        combined_lines.append("")
    return combined_lines


def write_combined_markdown(lines: list[str], output_path: Path) -> None:
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a consolidated CSAPP PDF.")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=DEFAULT_PDF_PATH,
        help="Output PDF path (default: csapp.pdf).",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=DEFAULT_MD_PATH,
        help="Output combined markdown path (default: csapp.md).",
    )
    parser.add_argument(
        "--skip-markdown",
        action="store_true",
        help="Skip writing the combined markdown output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary_text = SUMMARY_PATH.read_text(encoding="utf-8")
    entries = extract_summary_entries(summary_text)
    combined_markdown = build_combined_markdown(entries)
    if not args.skip_markdown:
        write_combined_markdown(combined_markdown, args.markdown)
        print(f"Wrote {args.markdown}")

    combined_lines: list[str] = []
    for title, path in entries:
        combined_lines.append("=" * 80)
        combined_lines.append(title)
        combined_lines.append("=" * 80)
        combined_lines.append("")
        if not path.exists():
            combined_lines.append(f"[Missing file: {path.relative_to(ROOT)}]")
            combined_lines.append("")
            continue
        markdown = path.read_text(encoding="utf-8")
        combined_lines.extend(normalize_markdown(markdown))
        combined_lines.append("")

    wrapped_lines = wrap_lines(combined_lines)
    build_pdf(wrapped_lines, args.pdf)
    print(f"Wrote {args.pdf}")


if __name__ == "__main__":
    main()
