"""受控的 SVG/PNG 流程图渲染器。

渲染输入来自已经通过 ``DiagramDocument`` 校验的 JSON，而不是客户端提供的
HTML 或脚本。Worker 使用本地固定版本的 Mermaid.js 在 Chromium 中生成 SVG，
再从同一个 SVG 截取 PNG；这样预览和导出的布局算法保持一致，也不会访问外部网络。
"""

from __future__ import annotations

import asyncio
import html
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4
from xml.etree import ElementTree

from app.core.config import get_settings
from app.schemas.diagram import DiagramDocument, DiagramNode, DiagramNodeType
from app.schemas.export import ExportBackground, ExportFormat
from app.services.diagram_service import compile_mermaid, validate_diagram_document


RENDER_TIMEOUT_MS = 30_000
MAX_RENDER_DIMENSION = 4_096
_NODE_WIDTH = 180
_NODE_HEIGHT = 68
_NODE_GAP_X = 88
_NODE_GAP_Y = 72
_PADDING = 36
_FONT_FAMILY = "Inter, 'Source Han Sans SC', sans-serif"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MERMAID_BUNDLE_ENV = "FLOWCHART_MERMAID_BUNDLE_PATH"
_MERMAID_BUNDLE_DEFAULT = "/app/assets/mermaid.min.js"
_MERMAID_THEME_VARIABLES: dict[str, dict[str, str]] = {
    "blue": {
        "primaryColor": "#EEF5FF",
        "primaryBorderColor": "#8EB8FF",
        "primaryTextColor": "#24549E",
        "lineColor": "#7A8CA8",
        "secondaryColor": "#EEF7FB",
        "tertiaryColor": "#F3F0FF",
    },
    "purple": {
        "primaryColor": "#F5F1FF",
        "primaryBorderColor": "#B7A8F0",
        "primaryTextColor": "#5B4A9B",
        "lineColor": "#8175A8",
        "secondaryColor": "#F1F4FF",
        "tertiaryColor": "#F7EFFF",
    },
    "green": {
        "primaryColor": "#EDFBF5",
        "primaryBorderColor": "#8ED3B6",
        "primaryTextColor": "#27765D",
        "lineColor": "#6D9C8A",
        "secondaryColor": "#EEFAF8",
        "tertiaryColor": "#F0F8F4",
    },
}
_SAFE_STYLE_FORBIDDEN_RE = re.compile(
    r"(?:@import|expression\s*\(|(?:java|vb)script\s*:|data\s*:|<|>|`)",
    re.IGNORECASE,
)
_ACTIVE_SVG_TAGS = {
    "a",
    "audio",
    "animate",
    "animatemotion",
    "animatetransform",
    "animatecolor",
    "cursor",
    "discard",
    "embed",
    "feimage",
    "foreignobject",
    "iframe",
    "image",
    "mpath",
    "object",
    "set",
    "script",
    "style",
    "switch",
    "use",
    "video",
    "view",
}


def _mermaid_bundle_path() -> Path | None:
    configured = os.getenv(_MERMAID_BUNDLE_ENV, "").strip()
    repository_bundle = (
        Path(__file__).resolve().parents[4]
        / "frontend"
        / "node_modules"
        / "mermaid"
        / "dist"
        / "mermaid.min.js"
    )
    candidates = [Path(configured)] if configured else []
    candidates.extend([Path(_MERMAID_BUNDLE_DEFAULT), repository_bundle])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _mermaid_source_from_snapshot(
    snapshot: Mapping[str, Any], document: DiagramDocument
) -> str:
    """Use the persisted source only when it is exactly the current graph source."""

    canonical_source = compile_mermaid(document)
    persisted_source = snapshot.get("mermaidSource") or snapshot.get("mermaid_source")
    if isinstance(persisted_source, str) and persisted_source.strip() == canonical_source:
        return persisted_source.strip()
    return canonical_source


def _mermaid_theme_variables(document: DiagramDocument) -> dict[str, str]:
    theme = str(document.metadata.theme or "blue").lower()
    return dict(_MERMAID_THEME_VARIABLES.get(theme, _MERMAID_THEME_VARIABLES["blue"]))


class ExportRenderError(RuntimeError):
    """所有浏览器、字体和截图失败的统一内部异常。"""

    error_code = "EXPORT_RENDER_FAILED"


class ExportRenderer(Protocol):
    async def render(
        self,
        snapshot: Mapping[str, Any],
        export_format: ExportFormat,
        background: ExportBackground,
    ) -> bytes: ...


def _document_from_snapshot(snapshot: Mapping[str, Any]) -> DiagramDocument:
    payload = snapshot.get("diagramData") or snapshot.get("diagram_data") or snapshot
    return validate_diagram_document(payload)


def _layout_nodes(document: DiagramDocument) -> dict[str, tuple[float, float]]:
    nodes = document.nodes
    if not nodes:
        return {}

    supplied = {
        node.id: (float(node.position.x), float(node.position.y)) for node in nodes
    }
    # 新生成的节点通常都从 (0, 0) 开始；在这种情况下提供稳定的可读布局。
    if len(set(supplied.values())) == 1:
        return {
            node.id: (
                0 if document.direction.value == "TB" else index * (_NODE_WIDTH + _NODE_GAP_X),
                index * (_NODE_HEIGHT + _NODE_GAP_Y) if document.direction.value == "TB" else 0,
            )
            for index, node in enumerate(nodes)
        }
    return supplied


def _wrap_label(label: str, limit: int = 14) -> list[str]:
    normalized = " ".join(label.split())
    return [normalized[index : index + limit] for index in range(0, len(normalized), limit)] or [""]


def _node_style(node: DiagramNode) -> tuple[str, str]:
    if node.style is not None:
        return node.style.fill or "#F8FAFC", node.style.stroke or "#334155"
    defaults = {
        DiagramNodeType.START: ("#DCFCE7", "#15803D"),
        DiagramNodeType.END: ("#FEE2E2", "#B91C1C"),
        DiagramNodeType.PROCESS: ("#E0F2FE", "#0369A1"),
        DiagramNodeType.DECISION: ("#FEF3C7", "#B45309"),
        DiagramNodeType.INPUT_OUTPUT: ("#EDE9FE", "#6D28D9"),
        DiagramNodeType.SUBPROCESS: ("#F1F5F9", "#475569"),
    }
    return defaults[node.type]


def _text_svg(label: str, *, x: float, y: float) -> str:
    lines = _wrap_label(label)
    start = y - (len(lines) - 1) * 9
    tspans = "".join(
        f'<tspan x="{x:.1f}" dy="{0 if index == 0 else 18:.1f}">{html.escape(line)}</tspan>'
        for index, line in enumerate(lines[:4])
    )
    return (
        f'<text x="{x:.1f}" y="{start:.1f}" text-anchor="middle" '
        f'font-family="{html.escape(_FONT_FAMILY, quote=True)}" font-size="16" '
        f'fill="#0F172A">{tspans}</text>'
    )


def _shape_svg(node: DiagramNode, x: float, y: float) -> str:
    fill, stroke = _node_style(node)
    cx = x + _NODE_WIDTH / 2
    cy = y + _NODE_HEIGHT / 2
    common = f'fill="{fill}" stroke="{stroke}" stroke-width="2"'
    if node.type in {DiagramNodeType.START, DiagramNodeType.END}:
        shape = f'<rect x="{x}" y="{y}" width="{_NODE_WIDTH}" height="{_NODE_HEIGHT}" rx="34" {common}/>'
    elif node.type is DiagramNodeType.DECISION:
        points = f"{cx},{y} {x + _NODE_WIDTH},{cy} {cx},{y + _NODE_HEIGHT} {x},{cy}"
        shape = f'<polygon points="{points}" {common}/>'
    elif node.type is DiagramNodeType.INPUT_OUTPUT:
        points = f"{x + 24},{y} {x + _NODE_WIDTH},{y} {x + _NODE_WIDTH - 24},{y + _NODE_HEIGHT} {x},{y + _NODE_HEIGHT}"
        shape = f'<polygon points="{points}" {common}/>'
    else:
        radius = 4 if node.type is DiagramNodeType.PROCESS else 8
        shape = f'<rect x="{x}" y="{y}" width="{_NODE_WIDTH}" height="{_NODE_HEIGHT}" rx="{radius}" {common}/>'
        if node.type is DiagramNodeType.SUBPROCESS:
            shape += f'<rect x="{x + 7}" y="{y + 7}" width="{_NODE_WIDTH - 14}" height="{_NODE_HEIGHT - 14}" rx="5" fill="none" stroke="{stroke}" stroke-width="1"/>'
    return shape + _text_svg(node.label, x=cx, y=cy + 5)


def build_diagram_svg(payload: DiagramDocument | Mapping[str, Any]) -> str:
    """根据权威 DiagramDocument 生成无脚本的、可嵌入的 SVG。"""

    document = validate_diagram_document(payload)
    positions = _layout_nodes(document)
    if not positions:
        width = height = 240
    else:
        min_x = min(value[0] for value in positions.values())
        min_y = min(value[1] for value in positions.values())
        positions = {
            key: (value[0] - min_x + _PADDING, value[1] - min_y + _PADDING)
            for key, value in positions.items()
        }
        max_x = max(value[0] for value in positions.values()) + _NODE_WIDTH + _PADDING
        max_y = max(value[1] for value in positions.values()) + _NODE_HEIGHT + _PADDING
        width = min(MAX_RENDER_DIMENSION, max(240, int(max_x)))
        height = min(MAX_RENDER_DIMENSION, max(180, int(max_y)))

    aliases = {node.id: f"node-{index}" for index, node in enumerate(document.nodes)}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(document.title, quote=True)}">',
        f"<title>{html.escape(document.title)}</title>",
        "<defs><marker id=\"flowchart-arrow\" markerWidth=\"10\" markerHeight=\"10\" refX=\"8\" refY=\"3\" orient=\"auto\"><path d=\"M0,0 L0,6 L9,3 z\" fill=\"#64748B\"/></marker></defs>",
    ]
    for edge in document.edges:
        source = positions.get(edge.source)
        target = positions.get(edge.target)
        if source is None or target is None:
            continue
        sx, sy = source[0] + _NODE_WIDTH / 2, source[1] + _NODE_HEIGHT / 2
        tx, ty = target[0] + _NODE_WIDTH / 2, target[1] + _NODE_HEIGHT / 2
        parts.append(
            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" '
            'stroke="#64748B" stroke-width="2" marker-end="url(#flowchart-arrow)"/>'
        )
        edge_label = edge.condition or edge.label
        if edge_label:
            parts.append(
                f'<text x="{(sx + tx) / 2:.1f}" y="{(sy + ty) / 2 - 6:.1f}" '
                f'text-anchor="middle" font-family="{html.escape(_FONT_FAMILY, quote=True)}" '
                f'font-size="13" fill="#475569">{html.escape(edge_label)}</text>'
            )
    for node in document.nodes:
        x, y = positions[node.id]
        parts.append(f'<g id="{aliases[node.id]}">{_shape_svg(node, x, y)}</g>')
    parts.append("</svg>")
    return "".join(parts)


def _html_for_svg(svg: str, background: ExportBackground) -> str:
    background_css = "transparent" if background is ExportBackground.TRANSPARENT else "#FFFFFF"
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><style>"
        f"html,body{{margin:0;padding:0;background:{background_css};}}"
        f"svg{{display:block;font-family:{_FONT_FAMILY};}}"
        "</style></head><body>"
        f"{svg}</body></html>"
    )


def _html_for_mermaid(background: ExportBackground) -> str:
    background_css = "transparent" if background is ExportBackground.TRANSPARENT else "#FFFFFF"
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><style>"
        f"html,body{{margin:0;padding:0;background:{background_css};}}"
        "#flowchart-mermaid-mount{display:block;width:100%;}"
        "svg{display:block;}"
        "</style></head><body><div id=\"flowchart-mermaid-mount\"></div></body></html>"
    )


_MERMAID_RENDER_SCRIPT = """
async ({source, renderId, themeVariables}) => {
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    themeVariables,
    flowchart: {
      htmlLabels: false,
      useMaxWidth: true,
      curve: 'basis',
    },
  });
  const { svg } = await mermaid.render(renderId, source);
  const mount = document.getElementById('flowchart-mermaid-mount');
  if (!mount) {
    return false;
  }
  mount.innerHTML = svg;
  return Boolean(mount.querySelector('svg'));
}
"""


def _svg_dimensions(svg: str) -> tuple[int, int]:
    width_match = re.search(r'\bwidth="(\d+)"', svg)
    height_match = re.search(r'\bheight="(\d+)"', svg)
    return (
        min(MAX_RENDER_DIMENSION, max(240, int(width_match.group(1)) if width_match else 800)),
        min(MAX_RENDER_DIMENSION, max(180, int(height_match.group(1)) if height_match else 600)),
    )


def _chromium_path(configured: str) -> str | None:
    candidates = [configured, os.getenv("FLOWCHART_CHROMIUM_PATH", "")]
    if os.name == "nt":
        candidates.extend(
            [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]
        )
    else:
        candidates.extend(["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"])
    for candidate in candidates:
        if candidate and (Path(candidate).is_file() or shutil.which(candidate)):
            return candidate
    return None


async def _close_quietly(resource: Any, method: str = "close") -> None:
    if resource is None:
        return
    try:
        await asyncio.wait_for(getattr(resource, method)(), timeout=2)
    except Exception:
        # 清理阶段不覆盖渲染异常；Chromium close 会终止其子进程。
        return


class ChromiumExportRenderer:
    """使用单次 Playwright context 完成 SVG/PNG 渲染并强制回收资源。"""

    async def render(
        self,
        snapshot: Mapping[str, Any],
        export_format: ExportFormat,
        background: ExportBackground,
    ) -> bytes:
        if export_format not in {ExportFormat.SVG, ExportFormat.PNG}:
            raise ValueError("Chromium 仅支持 SVG 和 PNG")
        document = _document_from_snapshot(snapshot)
        mermaid_source = _mermaid_source_from_snapshot(snapshot, document)
        theme_variables = _mermaid_theme_variables(document)
        settings = get_settings().export
        # D14 契约是硬性的 30 秒上限；配置只能缩短，不能放宽该上限。
        timeout_ms = min(settings.render_timeout_ms or RENDER_TIMEOUT_MS, RENDER_TIMEOUT_MS)
        try:
            return await asyncio.wait_for(
                self._render_with_browser(
                    mermaid_source,
                    export_format,
                    background,
                    settings,
                    timeout_ms,
                    theme_variables=theme_variables,
                ),
                timeout=timeout_ms / 1000,
            )
        except asyncio.TimeoutError as exc:
            raise ExportRenderError("Chromium 渲染超时") from exc
        except ExportRenderError:
            raise
        except Exception as exc:
            raise ExportRenderError("Chromium 渲染失败") from exc

    async def _render_with_browser(
        self,
        mermaid_source: str,
        export_format: ExportFormat,
        background: ExportBackground,
        settings: Any,
        timeout_ms: int,
        *,
        theme_variables: Mapping[str, str] | None = None,
    ) -> bytes:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ExportRenderError("导出 Worker 未安装 Chromium 运行时") from exc

        temp_root = settings.temp_dir.strip() if isinstance(settings.temp_dir, str) else ""
        if temp_root:
            Path(temp_root).mkdir(parents=True, exist_ok=True)
        temp_dir = tempfile.mkdtemp(prefix="flowchart-export-", dir=temp_root or None)
        playwright = browser = context = page = None
        try:
            html_path = Path(temp_dir) / "diagram.html"
            bundle_path = _mermaid_bundle_path()
            if bundle_path is None:
                raise ExportRenderError("导出 Worker 未安装 Mermaid 渲染资源")
            html_path.write_text(_html_for_mermaid(background), encoding="utf-8")
            playwright = await async_playwright().start()
            launch_kwargs: dict[str, Any] = {"headless": True}
            executable = _chromium_path(settings.chromium_path)
            if executable:
                launch_kwargs["executable_path"] = executable
            if os.name != "nt":
                launch_kwargs["args"] = ["--no-sandbox", "--disable-dev-shm-usage"]
            browser = await playwright.chromium.launch(**launch_kwargs)
            context = await browser.new_context(
                # Mermaid 的 SVG 使用 viewBox 和 max-width；给它一个足够大的
                # 画布，截图时由 locator 取 SVG 的完整边界，避免分支被裁剪。
                viewport={"width": MAX_RENDER_DIMENSION, "height": MAX_RENDER_DIMENSION},
                device_scale_factor=1,
            )
            page = await context.new_page()
            await page.goto(
                html_path.resolve().as_uri(),
                wait_until="load",
                timeout=timeout_ms,
            )
            await page.add_script_tag(path=str(bundle_path))
            rendered = await page.evaluate(
                _MERMAID_RENDER_SCRIPT,
                {
                    "source": mermaid_source,
                    "renderId": f"flowchart-export-{uuid4().hex}",
                    "themeVariables": dict(theme_variables or _MERMAID_THEME_VARIABLES["blue"]),
                },
            )
            if not rendered:
                raise ExportRenderError("Mermaid 未生成 SVG")
            await page.evaluate("document.fonts ? document.fonts.ready : Promise.resolve()")
            svg_locator = page.locator("svg").first
            if export_format is ExportFormat.SVG:
                rendered = await svg_locator.evaluate(
                    """
                    element => {
                      const values = (element.getAttribute('viewBox') || '')
                        .trim()
                        .split(/\\s+/)
                        .map(Number);
                      if (values.length === 4 && values[2] > 0 && values[3] > 0) {
                        element.setAttribute('width', String(values[2]));
                        element.setAttribute('height', String(values[3]));
                      }
                      return element.outerHTML;
                    }
                    """
                )
                return str(rendered).encode("utf-8")
            return await svg_locator.screenshot(
                type="png",
                omit_background=background is ExportBackground.TRANSPARENT,
                timeout=timeout_ms,
            )
        except ExportRenderError:
            raise
        except Exception as exc:
            raise ExportRenderError("Chromium 页面渲染失败") from exc
        finally:
            # wait_for 取消当前协程时，直接 await gather 会把 gather 内的
            # close 协程一并取消，导致 Chromium 子进程残留。将清理任务
            # 与当前取消隔离，并在必要时等待它完成后再重新抛出取消。
            cleanup = asyncio.gather(
                _close_quietly(page),
                _close_quietly(context),
                _close_quietly(browser),
                _close_quietly(playwright, "stop"),
            )
            try:
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await asyncio.shield(cleanup)
                    raise
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)


@lru_cache(maxsize=1)
def get_export_renderer() -> ChromiumExportRenderer:
    return ChromiumExportRenderer()


def is_valid_rendered_content(export_format: ExportFormat, content: bytes) -> bool:
    if not content:
        return False
    if export_format is ExportFormat.SVG:
        try:
            source = content.decode("utf-8")
            lowered_source = source.lower()
            if (
                "<!doctype" in lowered_source
                or "<!entity" in lowered_source
                or "<?xml-stylesheet" in lowered_source
            ):
                return False
            root = ElementTree.fromstring(source)
        except (UnicodeDecodeError, ElementTree.ParseError):
            return False
        if root.tag.rsplit("}", 1)[-1].lower() != "svg":
            return False
        parents = {
            child: parent
            for parent in root.iter()
            for child in parent
        }
        for element in root.iter():
            local_name = element.tag.rsplit("}", 1)[-1].lower()
            if local_name == "foreignobject":
                if not _is_safe_mermaid_foreign_object(element):
                    return False
            elif local_name in {"div", "span", "p"}:
                if not _inside_foreign_object(element, parents):
                    return False
                if not element.tag.startswith("{http://www.w3.org/1999/xhtml}"):
                    return False
                if any(
                    attribute.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()
                    not in {"class", "style"}
                    for attribute in element.attrib
                ):
                    return False
            elif local_name == "style":
                if not _is_safe_style_value(element.text or ""):
                    return False
            elif local_name in _ACTIVE_SVG_TAGS:
                return False
            for attribute, value in element.attrib.items():
                attribute_name = attribute.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()
                if attribute_name.startswith("on"):
                    return False
                if attribute_name == "style":
                    if not _is_safe_style_value(value):
                        return False
                normalized_value = value.strip()
                lowered_value = normalized_value.lower()
                if (
                    lowered_value.startswith(("javascript:", "vbscript:", "data:", "http:", "https:", "file:"))
                    or any(
                        reference.strip() and not reference.strip().startswith("#")
                        for reference in re.findall(r"url\(([^)]*)\)", normalized_value, flags=re.IGNORECASE)
                    )
                ):
                    return False
                if attribute_name in {"href", "src"} and normalized_value and not normalized_value.startswith("#"):
                    return False
        return True
    if export_format is ExportFormat.PNG:
        return content.startswith(_PNG_SIGNATURE)
    return False


def _is_safe_style_value(value: str) -> bool:
    if "\x00" in value or _SAFE_STYLE_FORBIDDEN_RE.search(value):
        return False
    return all(
        not reference.strip() or reference.strip().startswith("#")
        for reference in re.findall(r"url\(([^)]*)\)", value, flags=re.IGNORECASE)
    )


def _inside_foreign_object(
    element: ElementTree.Element,
    parents: Mapping[ElementTree.Element, ElementTree.Element],
) -> bool:
    parent = parents.get(element)
    while parent is not None:
        if parent.tag.rsplit("}", 1)[-1].lower() == "foreignobject":
            return True
        parent = parents.get(parent)
    return False


def _is_safe_mermaid_foreign_object(element: ElementTree.Element) -> bool:
    allowed_tags = {"div", "span", "p"}
    for child in element.iter():
        if child is element:
            continue
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name not in allowed_tags:
            return False
        if not child.tag.startswith("{http://www.w3.org/1999/xhtml}"):
            return False
        for attribute, value in child.attrib.items():
            attribute_name = attribute.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()
            if attribute_name not in {"class", "style"}:
                return False
            if attribute_name == "style" and not _is_safe_style_value(value):
                return False
    return True


__all__ = [
    "ChromiumExportRenderer",
    "ExportRenderError",
    "ExportRenderer",
    "RENDER_TIMEOUT_MS",
    "build_diagram_svg",
    "get_export_renderer",
    "is_valid_rendered_content",
]
