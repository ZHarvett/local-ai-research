"""Bootstrap and sync on a temp repo carrying a copy of the umbrella CLAUDE.md
(the non-destructive merge case)."""

import json
import shutil
from pathlib import Path

from conftest import KIT

BOOTSTRAP = KIT / "bootstrap.sh"
SYNC = KIT / "sync.sh"
UMBRELLA_CLAUDE = KIT.parent / "CLAUDE.md"


def make_target(tmp_path, with_claude=True, name="target") -> Path:
    target = tmp_path / name
    target.mkdir()
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    if with_claude:
        shutil.copyfile(UMBRELLA_CLAUDE, target / "CLAUDE.md")
    return target


def run(script, *args):
    import subprocess

    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True)


def test_bootstrap_dry_run_writes_nothing(tmp_path):
    target = make_target(tmp_path)
    out = run(BOOTSTRAP, str(target), "--dry-run")
    assert out.returncode == 0
    assert "DRY RUN" in out.stdout
    assert not (target / "scripts").exists()
    assert not (target / ".workflow").exists()
    assert not (target / ".workflow-kit-version").exists()
    # the existing CLAUDE.md is untouched
    assert (target / "CLAUDE.md").read_text() == UMBRELLA_CLAUDE.read_text()


def test_bootstrap_dry_run_reports_claude_conflicts(tmp_path):
    target = make_target(tmp_path)
    out = run(BOOTSTRAP, str(target), "--dry-run")
    assert "CLAUDE.md conflicts" in out.stdout
    assert "session start protocol" in out.stdout
    assert "progress logging" in out.stdout
    assert "report format" in out.stdout


def test_bootstrap_appends_marker_block_to_existing_claude(tmp_path):
    target = make_target(tmp_path)
    out = run(BOOTSTRAP, str(target))
    assert out.returncode == 0
    text = (target / "CLAUDE.md").read_text()
    assert text.startswith("# CLAUDE.md — Local AI on a Small PC")  # original intact
    assert "<!-- workflow-kit:begin -->" in text
    assert "<!-- workflow-kit:end -->" in text
    assert "docs/WORKFLOW.md" in text


def test_bootstrap_installs_all_kit_files(tmp_path):
    target = make_target(tmp_path)
    run(BOOTSTRAP, str(target))
    expected = [
        "scripts/_wf.py",
        "scripts/wf.sh",
        "scripts/wf-card.sh",
        "scripts/wf-guard.sh",
        "scripts/wf-progress.sh",
        "scripts/wf-plan-import.sh",
        "scripts/wf-escalate.sh",
        "scripts/wf-decision.sh",
        "scripts/wf-merge-lanes.sh",
        "docs/WORKFLOW.md",
        ".workflow/config.toml",
        ".workflow/templates/escalation-brief.md",
        ".workflow/templates/review-report.md",
        ".claude/settings.json",
        ".workflow-kit-version",
        ".workflow-kit-manifest.json",
        ".gitignore",
    ]
    for rel in expected:
        assert (target / rel).is_file(), rel
    for name in (
        "continue.md",
        "lane.md",
        "review.md",
        "address-review.md",
        "escalate.md",
        "status.md",
        "calibrate-reviewer.md",
    ):
        assert (target / ".claude" / "commands" / name).is_file(), name
    assert (target / "scripts" / "wf.sh").stat().st_mode & 0o111


def test_bootstrap_reports_conflict_without_force(tmp_path):
    target = make_target(tmp_path)
    run(BOOTSTRAP, str(target))
    # locally modify a kit file
    (target / "docs" / "WORKFLOW.md").write_text("rewritten\n")
    out = run(BOOTSTRAP, str(target))
    assert "CONFLICT" in out.stdout
    assert (target / "docs" / "WORKFLOW.md").read_text() == "rewritten\n"
    out = run(BOOTSTRAP, str(target), "--force")
    assert (target / "docs" / "WORKFLOW.md").read_text() != "rewritten\n"


def test_bootstrap_never_overwrites_settings(tmp_path):
    target = make_target(tmp_path)
    run(BOOTSTRAP, str(target))
    settings = target / ".claude" / "settings.json"
    settings.write_text('{"permissions": {"allow": ["Bash(ls)"]}}')
    out = run(BOOTSTRAP, str(target), "--force")
    assert settings.read_text() == '{"permissions": {"allow": ["Bash(ls)"]}}'
    assert "suggested" in out.stdout  # the diff is printed, not applied


def test_bootstrap_gitignore_entry(tmp_path):
    target = make_target(tmp_path)
    (target / ".gitignore").write_text("build/\n")
    run(BOOTSTRAP, str(target))
    gi = (target / ".gitignore").read_text()
    assert ".workflow/worktrees/" in gi and "build/" in gi


def test_bootstrap_with_hook(tmp_path):
    target = make_target(tmp_path)
    run(BOOTSTRAP, str(target), "--with-hook")
    hook = target / ".git" / "hooks" / "pre-commit"
    assert hook.is_file()
    assert "wf-guard" in hook.read_text()
    assert hook.stat().st_mode & 0o111


def test_sync_updates_only_unchanged_kit_files(tmp_path):
    target = make_target(tmp_path)
    run(BOOTSTRAP, str(target))
    # change a kit file in the KIT itself is not possible here; instead modify
    # the installed copy and check refusal, then --force
    work = target / "docs" / "WORKFLOW.md"
    work.write_text(work.read_text() + "\n# local addition\n")
    out = run(SYNC, str(target))
    assert out.returncode == 1
    assert "REFUSED (locally modified): docs/WORKFLOW.md" in out.stdout
    assert "# local addition" in work.read_text()  # not discarded
    out = run(SYNC, str(target), "--force")
    assert out.returncode == 0
    assert "# local addition" not in work.read_text()


def test_sync_refusal_persists_across_runs(tmp_path):
    target = make_target(tmp_path)
    run(BOOTSTRAP, str(target))
    work = target / "docs" / "WORKFLOW.md"
    work.write_text(work.read_text() + "\n# local addition\n")
    run(SYNC, str(target))
    run(SYNC, str(target))  # second run must still refuse (manifest kept)
    assert "# local addition" in work.read_text()


def test_sync_restores_missing_kit_file(tmp_path):
    target = make_target(tmp_path)
    run(BOOTSTRAP, str(target))
    (target / "scripts" / "wf-card.sh").unlink()
    out = run(SYNC, str(target))
    assert out.returncode == 0
    assert (target / "scripts" / "wf-card.sh").is_file()
    assert (target / "scripts" / "wf-card.sh").stat().st_mode & 0o111


def test_sync_never_touches_settings_or_unmarked_claude(tmp_path):
    target = make_target(tmp_path)
    run(BOOTSTRAP, str(target))
    settings = target / ".claude" / "settings.json"
    settings.write_text('{"mine": true}')
    claude = target / "CLAUDE.md"
    claude.write_text("# only mine\nno markers\n")
    out = run(SYNC, str(target), "--force")
    assert settings.read_text() == '{"mine": true}'
    assert claude.read_text() == "# only mine\nno markers\n"
    assert "settings.json" in out.stdout  # reported, not touched


def test_manifest_records_kit_hashes(tmp_path):
    target = make_target(tmp_path)
    run(BOOTSTRAP, str(target))
    manifest = json.loads((target / ".workflow-kit-manifest.json").read_text())
    assert manifest["version"] == "0.1.0"
    assert "scripts/_wf.py" in manifest["files"]
    assert manifest["files"]["docs/WORKFLOW.md"] == _sha(KIT / "templates" / "WORKFLOW.md.template")


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
