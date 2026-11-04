from portfolio_agent import publication_check as pc


def test_terms_split_on_new_lines_and_commas_and_drop_blanks():
    assert pc.parse_terms(" Acme Corp ,Zeta\n\n  ביטוח ישיר\n,") == [
        "Acme Corp", "Zeta", "ביטוח ישיר"]


def test_find_ignores_case_final_letters_niqqud_and_hebrew_prefixes(tmp_path):
    a = tmp_path / "a.md"
    a.write_text("line one\nWe built it for ACME corp.\n", encoding="utf-8")
    b = tmp_path / "b.md"
    b.write_text("עבדנו בשָׁלוֹם בע\"מ\n", encoding="utf-8")  # prefix ב, niqqud, final ם
    clean = tmp_path / "c.md"
    clean.write_text("nothing here\n", encoding="utf-8")
    binary = tmp_path / "d.ico"
    binary.write_bytes(b"\xff\xfe\x00acme")
    errors = pc.find(["Acme Corp", "שלומ"], [a, b, clean, binary], root=tmp_path)
    assert errors == ["a.md:2: forbidden term #1", "b.md:1: forbidden term #2"]


def test_errors_never_print_the_term(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("SecretClient\n", encoding="utf-8")
    assert all("secret" not in e.lower() for e in pc.find(["SecretClient"], [f], root=tmp_path))


def test_main_skips_without_a_list_unless_required(monkeypatch, tmp_path):
    monkeypatch.setattr(pc, "ROOT", tmp_path)
    monkeypatch.delenv(pc.ENV_VAR, raising=False)
    assert pc.main([]) == 0
    assert pc.main(["--require"]) == 1


def test_main_fails_on_a_hit_and_reads_the_list_from_env(monkeypatch, tmp_path, capsys):
    f = tmp_path / "r.md"
    f.write_text("Zeta Holdings\n", encoding="utf-8")
    monkeypatch.setenv(pc.ENV_VAR, "zeta")
    monkeypatch.setattr(pc, "tracked_files", lambda: [f])
    monkeypatch.setattr(pc, "ROOT", tmp_path)
    assert pc.main(["--require"]) == 1
    assert capsys.readouterr().out.strip() == "r.md:1: forbidden term #1"


def test_load_terms_falls_back_to_the_local_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv(pc.ENV_VAR, raising=False)
    (tmp_path / ".env").write_text('OTHER=1\nPUBLICATION_TERMS="a, b"\n', encoding="utf-8")
    monkeypatch.setattr(pc, "ROOT", tmp_path)
    assert pc.load_terms() == ["a", "b"]
