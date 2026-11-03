from mubu_exporter.cli import main


def test_cli_real_export(cache, tmp_path, capsys):
    out = tmp_path / "output"
    assert main(["export", "--cache", str(cache), "--out", str(out), "--images", "skip"]) == 0
    assert '"documents": 1' in capsys.readouterr().out
    assert (out / "index.md").exists()


def test_cli_failure_returns_nonzero_and_redacts_local_path(tmp_path, capsys):
    assert main(["inspect", "--cache", str(tmp_path / "private-name")]) == 2
    result = capsys.readouterr()
    assert "private-name" not in result.err and "error:" in result.err


def test_cli_does_not_log_note_titles_or_ids(cache, capsys):
    assert main(["inspect", "--cache", str(cache)]) == 0
    output = capsys.readouterr().out
    assert "sample_doc" not in output and "示例文档" not in output


def test_fetch_requires_explicit_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MUBU_TOKEN", raising=False)
    assert main(["fetch", "--cache", str(tmp_path / "backup")]) == 2
    assert "MUBU_TOKEN is required" in capsys.readouterr().err
