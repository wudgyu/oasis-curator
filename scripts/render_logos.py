#!/usr/bin/env python3
"""
Oasis Curator · Logo SVG → PNG 转换脚本

把 brand/logo/ 下的 SVG 源文件渲染为 README 引用的多尺寸 PNG 文件。

依赖（二选一）：
  - cairosvg（推荐）：pip install cairosvg
  - Pillow + svglib（备选）：pip install Pillow svglib reportlab

输出：
  brand/logo/oasis-curator-128.png
  brand/logo/oasis-curator-256.png
  brand/logo/oasis-curator-512.png
  brand/logo/oasis-curator-1024.png
  brand/logo/oasis-curator-icon-64.png
  brand/logo/oasis-curator-icon-128.png
  brand/logo/oasis-curator-icon-256.png

使用方法：
  python scripts/render_logos.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 路径
ROOT = Path(__file__).resolve().parent.parent
LOGO_DIR = ROOT / "brand" / "logo"
OUT_DIR = LOGO_DIR

# 渲染任务清单：(svg_filename, [(size, out_filename), ...])
TASKS: list[tuple[str, list[tuple[int, str]]]] = [
    ("logo-primary.svg", [
        (128, "oasis-curator-128.png"),
        (256, "oasis-curator-256.png"),
        (512, "oasis-curator-512.png"),
        (1024, "oasis-curator-1024.png"),
    ]),
    ("logo-icon.svg", [
        (64, "oasis-curator-icon-64.png"),
        (128, "oasis-curator-icon-128.png"),
        (256, "oasis-curator-icon-256.png"),
    ]),
]


def render_with_cairosvg(svg_path: Path, size: int, out_path: Path) -> None:
    """使用 cairosvg 渲染。"""
    import cairosvg  # type: ignore
    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(out_path),
        output_width=size,
        output_height=size,
    )


def render_with_pillow(svg_path: Path, size: int, out_path: Path) -> None:
    """使用 svglib + reportlab + Pillow 渲染（备选方案）。"""
    from io import BytesIO
    from PIL import Image
    from svglib.svglib import svg2rlg  # type: ignore
    from reportlab.graphics import renderPM  # type: ignore

    drawing = svg2rlg(str(svg_path))
    if drawing is None:
        raise RuntimeError(f"无法解析 SVG: {svg_path}")

    # 按比例缩放
    scale = size / max(drawing.width, drawing.height)
    drawing.scale(scale, scale)
    drawing.width = size
    drawing.height = size

    png_bytes = BytesIO()
    renderPM.drawToFile(drawing, png_bytes, fmt="PNG")
    png_bytes.seek(0)
    img = Image.open(png_bytes)
    img.save(out_path, "PNG")


def main() -> int:
    # 选择渲染后端
    backend = None
    try:
        import cairosvg  # noqa: F401  # type: ignore
        backend = "cairosvg"
    except ImportError:
        pass

    if backend is None:
        try:
            from svglib.svglib import svg2rlg  # noqa: F401  # type: ignore
            from reportlab.graphics import renderPM  # noqa: F401  # type: ignore
            backend = "pillow"
        except ImportError:
            print("❌ 未找到可用的 SVG 渲染后端。")
            print("   请安装其一：")
            print("     pip install cairosvg")
            print("     pip install Pillow svglib reportlab")
            return 1

    print(f"🎨 使用后端：{backend}")
    print(f"📁 输出目录：{OUT_DIR}")
    print()

    success = 0
    for svg_name, sizes in TASKS:
        svg_path = LOGO_DIR / svg_name
        if not svg_path.exists():
            print(f"⚠️  跳过：{svg_name} 不存在")
            continue

        for size, out_name in sizes:
            out_path = OUT_DIR / out_name
            try:
                if backend == "cairosvg":
                    render_with_cairosvg(svg_path, size, out_path)
                else:
                    render_with_pillow(svg_path, size, out_path)
                print(f"  ✓ {out_name:40s} ({size}×{size})")
                success += 1
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {out_name:40s} 失败：{e}")

    print()
    print(f"✅ 完成：成功生成 {success} 个 PNG 文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
