"""Tests for the ``fetcher`` CLI — focused on ``--query-file`` handling."""
from __future__ import annotations

import pytest

from src import fetcher


def _parse(argv: list[str]) -> tuple:
    parser = fetcher._build_cli()
    return parser, parser.parse_args(argv)


def test_query_file_reads_and_strips_contents(tmp_path):
    qfile = tmp_path / "query.txt"
    qfile.write_text("  Ganoderma lucidum [MeSH]  \n", encoding="utf-8")

    parser, args = _parse([
        "--query-file", str(qfile),
        "--output", str(tmp_path / "out.json"),
    ])
    assert fetcher._resolve_query(parser, args) == "Ganoderma lucidum [MeSH]"


def test_query_file_empty_errors_cleanly(tmp_path, capsys):
    qfile = tmp_path / "empty.txt"
    qfile.write_text("   \n\n", encoding="utf-8")

    parser, args = _parse([
        "--query-file", str(qfile),
        "--output", str(tmp_path / "out.json"),
    ])
    with pytest.raises(SystemExit):
        fetcher._resolve_query(parser, args)
    assert "empty" in capsys.readouterr().err.lower()


def test_query_file_missing_errors_cleanly(tmp_path, capsys):
    missing = tmp_path / "does_not_exist.txt"

    parser, args = _parse([
        "--query-file", str(missing),
        "--output", str(tmp_path / "out.json"),
    ])
    with pytest.raises(SystemExit):
        fetcher._resolve_query(parser, args)
    assert "not found" in capsys.readouterr().err.lower()
