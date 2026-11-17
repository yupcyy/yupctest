"""Combine safe, versioned prompt resources without reading arbitrary paths."""
from pathlib import Path


class PromptManager:
    def __init__(self, root: str | Path | None = None, *, allowed_personas: tuple[str, ...] = ("dafeiyu",)):
        if root is not None:
            self.root = Path(root)
        else:
            # Support both the canonical project-level prompts/ directory and
            # existing deployments that placed prompts inside src/qq_deepseek/.
            project_root = Path(__file__).resolve().parents[3]
            project_prompts = project_root / "prompts"
            package_prompts = Path(__file__).resolve().parents[1] / "prompts"
            self.root = project_prompts if project_prompts.is_dir() else package_prompts
        self.allowed_personas = frozenset(allowed_personas)

    def _read(self, relative: str) -> str:
        path = self.root / relative
        try:
            content = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Missing prompt resource: {path}") from exc
        if not content:
            raise ValueError(f"Empty prompt resource: {path}")
        return content

    def build(self, persona: str = "dafeiyu", *, tools_enabled: bool = False) -> str:
        if persona not in self.allowed_personas:
            raise ValueError(f"Unsupported persona: {persona!r}")
        parts = [self._read("system.md"), self._read(f"personas/{persona}.md")]
        if tools_enabled:
            parts.append(self._read("tools.md"))
        return "\n\n---\n\n".join(parts)
