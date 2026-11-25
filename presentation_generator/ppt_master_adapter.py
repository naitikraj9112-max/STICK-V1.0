"""Thin adapter for PPT Master's SVG quality and native-PPTX export scripts."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from config import PPT_MASTER_WORKSPACE
from presentation_generator.svg_templates import _slide_filename


def prepare_session_workspace(session_workspace: Path, template_workspace: str | Path | None = None) -> Path:
    """Initialize an isolated session workspace from the configured template project."""
    session_workspace.mkdir(parents=True, exist_ok=True)
    marker = session_workspace / ".stick_initialized"
    if marker.exists():
        return session_workspace
    template = Path(template_workspace or PPT_MASTER_WORKSPACE)
    if template.is_dir():
        for item in template.iterdir():
            if item.name in {"svg_output", "exports", ".git", "__pycache__", "validation", "backup"}:
                continue
            target = session_workspace / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            elif not target.exists():
                shutil.copy2(item, target)
    for folder in ("svg_output", "exports", "validation"):
        (session_workspace / folder).mkdir(parents=True, exist_ok=True)
    marker.write_text("initialized")
    return session_workspace


class PptMasterAdapter:
    """Uses an installed PPT Master checkout without importing its agent architecture."""

    def __init__(self, root: str | Path, workspace: str | Path = ""):
        self.root = Path(root)
        self.workspace = Path(workspace) if workspace else None
        self.scripts = self.root / "skills" / "ppt-master" / "scripts"
        self.last_report: dict = {}

    @property
    def available(self) -> bool:
        return (
            self.workspace is not None
            and (self.scripts / "svg_quality_checker.py").is_file()
            and (self.scripts / "svg_to_pptx.py").is_file()
        )

    def write_scene_svg(
        self,
        scene: dict,
        workspace: Path,
        filename: str | None = None,
        scene_images: dict[str, str] | None = None,
    ) -> Path:
        """Translate approved scene intent into a quick-generate flat SVG page."""
        from presentation_generator.svg_templates import build_scene_svg

        output = workspace / "svg_output"
        output.mkdir(parents=True, exist_ok=True)
        index = scene.get("slide_index", 1)
        path = output / (filename or _slide_filename(index, scene))
        background = (scene_images or {}).get(scene.get("id", ""))
        path.write_text(build_scene_svg(scene, background_image=background), encoding="utf-8")
        return path

    def write_all_scenes(self, scenes: list[dict], workspace: Path, scene_images: dict[str, str] | None = None) -> None:
        """Write every slide in presentation order for multi-page quick-generate export."""
        output = workspace / "svg_output"
        output.mkdir(parents=True, exist_ok=True)
        for path in output.glob("*.svg"):
            path.unlink()
        for index, scene in enumerate(scenes, start=1):
            enriched = {**scene, "slide_index": index, "slide_total": len(scenes)}
            self.write_scene_svg(enriched, workspace, filename=_slide_filename(index, enriched), scene_images=scene_images)

    def validate(self, workspace: Path) -> list[str]:
        """Run the lockless quick-generate final SVG quality gate."""
        result = self._run(
            "svg_quality_checker.py",
            workspace,
            "--quick-generate",
            "--stage",
            "final",
            "--json",
        )
        report_path = workspace / "validation" / "svg_quality_report.json"
        self.last_report = {}
        if report_path.is_file():
            try:
                self.last_report = json.loads(report_path.read_text())
            except json.JSONDecodeError:
                self.last_report = {}
        if result.returncode == 0:
            return []
        issues = []
        blocking = self.last_report.get("categories", {}).get("blocking", {}).get("issues", [])
        if not blocking:
            blocking = self.last_report.get("issues", {}).get("blocking", {}).get("issues", [])
        for item in blocking[:6]:
            message = item.get("message") or item.get("code") or "SVG quality issue"
            file_name = item.get("file") or item.get("svg") or ""
            issues.append(f"{file_name}: {message}".strip(": "))
        if not issues:
            stderr = (result.stderr or "").strip()
            issues.append(stderr.splitlines()[-1] if stderr else "PPT Master SVG quality check failed")
        return issues

    def export(self, workspace: Path) -> Path:
        result = self._run("svg_to_pptx.py", workspace, "--quick-generate")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            raise RuntimeError(detail[-1] if detail else "PPT Master native PPTX export failed")
        exports = sorted((workspace / "exports").glob("*.pptx"), key=lambda path: path.stat().st_mtime)
        if not exports:
            raise RuntimeError("PPT Master export produced no PPTX artifact")
        return exports[-1]

    def _run(self, script: str, workspace: Path, *arguments: str):
        return subprocess.run(
            [sys.executable, str(self.scripts / script), str(workspace), *arguments],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
