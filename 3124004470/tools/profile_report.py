"""用标准库 ``cProfile`` 做性能分析，并生成性能分析图。

对应作业要求的"效能分析"：记录改进思路、展示性能分析图，
并指出程序中消耗最大的函数。

用法（在项目根目录执行）::

    python tools/profile_report.py [题目个数] [范围]

输出：

* ``docs/profile_stats.txt``  完整的函数耗时排名；
* ``docs/profile_chart.svg``  横向条形图（可直接在浏览器中打开并截图）；
* ``docs/profile_data.json``  原始数据，便于用其它工具重新绘图。
"""

from __future__ import annotations

import cProfile
import io
import json
import pstats
import platform
import random
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from quiz.generator import QuestionGenerator  # noqa: E402

DEFAULT_COUNT = 10000
DEFAULT_LIMIT = 10

CHART_PATH = PROJECT_ROOT / "docs" / "profile_chart.svg"
STATS_PATH = PROJECT_ROOT / "docs" / "profile_stats.txt"
DATA_PATH = PROJECT_ROOT / "docs" / "profile_data.json"


def run_generation(count: int, limit: int, seed: int = 20240915) -> float:
    """执行一次完整生成，返回耗时（秒）。"""
    started = time.perf_counter()
    QuestionGenerator(limit, rng=random.Random(seed)).generate(count)
    return time.perf_counter() - started


def write_bar_chart(path: Path, entries: list[tuple[str, float]], total: float) -> None:
    """把"函数 → 累计耗时占比"画成 SVG 条形图（不依赖第三方库）。"""
    row_height = 26
    width = 900
    height = 76 + row_height * len(entries)
    bar_left = 340
    bar_max_width = 420

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="20" y="32" font-family="Consolas,monospace" font-size="16" '
        f'font-weight="bold">cProfile cumulative time (total {total:.3f}s)</text>',
    ]
    for index, (name, value) in enumerate(entries):
        top = 56 + index * row_height
        ratio = value / total if total else 0.0
        bar_width = max(1.0, bar_max_width * ratio)
        parts.append(
            f'<text x="20" y="{top + 14}" font-family="Consolas,monospace" '
            f'font-size="12">{name}</text>'
        )
        parts.append(
            f'<rect x="{bar_left}" y="{top}" width="{bar_width:.1f}" height="16" '
            f'fill="#3b7dd8"/>'
        )
        parts.append(
            f'<text x="{bar_left + bar_width + 8:.1f}" y="{top + 13}" '
            f'font-family="Consolas,monospace" font-size="12">'
            f'{value:.4f}s ({ratio * 100:.1f}%)</text>'
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_COUNT
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_LIMIT

    run_generation(min(count, 1000), limit)  # 预热，排除首次运行的额外开销
    clean_elapsed = run_generation(count, limit)

    profiler = cProfile.Profile()
    profiler.enable()
    run_generation(count, limit)
    profiler.disable()

    stats = pstats.Stats(profiler)
    buffer = io.StringIO()
    stats.stream = buffer
    stats.sort_stats("cumulative").print_stats(14)
    stats.sort_stats("tottime").print_stats(10)

    output = [
        f"题目个数：{count}，范围：-r {limit}",
        f"真实耗时（不带 profiler）：{clean_elapsed:.3f} 秒",
        f"带 cProfile 的耗时：{stats.total_tt:.3f} 秒（cProfile 会放大耗时，仅用于定位瓶颈）",
        "",
        "函数耗时排名：",
        buffer.getvalue(),
    ]
    report = "\n".join(output)
    print(report)
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(report + "\n", encoding="utf-8")

    entries: list[tuple[str, float]] = []
    for (filename, lineno, name), data in stats.stats.items():
        if "quiz" not in filename:
            continue
        entries.append((f"{Path(filename).name}:{lineno}({name})", data[3]))
    entries.sort(key=lambda item: item[1], reverse=True)
    write_bar_chart(CHART_PATH, entries[:10], stats.total_tt)

    DATA_PATH.write_text(
        json.dumps(
            {
                "title": (
                    f"cProfile 累计耗时（生成 {count} 道题，总 {stats.total_tt:.3f} 秒，"
                    f"{platform.python_implementation()} {platform.python_version()}）"
                ),
                "total_seconds": stats.total_tt,
                "clean_elapsed_seconds": clean_elapsed,
                "count": count,
                "limit": limit,
                "entries": [
                    {"function": name, "cumulative_seconds": value}
                    for name, value in entries[:10]
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n性能分析图已生成：{CHART_PATH}")
    print(f"性能分析数据已导出：{DATA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
