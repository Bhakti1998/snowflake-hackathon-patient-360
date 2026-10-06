import re
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_portable_skill_alias_and_frontmatter():
    canonical = ROOT / ".cortex/skills"
    alias = ROOT / ".snowflake/cortex/skills"
    assert alias.resolve() == canonical.resolve()
    skills = list(canonical.glob("*/SKILL.md"))
    assert len(skills) == 12
    for path in skills:
        frontmatter = yaml.safe_load(path.read_text().split("---", 2)[1])
        assert frontmatter["name"] == path.parent.name
        assert frontmatter["description"]
        assert (alias / path.parent.name / "SKILL.md").read_bytes() == path.read_bytes()


def test_project_kit_local_links_and_anchors():
    paths = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT.parent / "AGENTS.md"]
    paths += list((ROOT / "docs").glob("*.md")) + list((ROOT / ".cortex").rglob("*.md"))
    for path in paths:
        for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", path.read_text()):
            target = target.strip("<>")
            if target.startswith(("http:", "https:", "mailto:")):
                continue
            name, _, anchor = unquote(target).partition("#")
            resolved = (path.parent / name).resolve() if name else path
            assert resolved.exists(), f"Broken link {target} in {path}"
            if anchor and resolved.is_file():
                headings = re.findall(r"^#{1,6}\s+(.+)$", resolved.read_text(), re.MULTILINE)
                slugs = [re.sub(r"[^\w -]", "", h.replace("`", "").lower()).replace(" ", "-") for h in headings]
                assert anchor in slugs, f"Broken anchor {target} in {path}"
