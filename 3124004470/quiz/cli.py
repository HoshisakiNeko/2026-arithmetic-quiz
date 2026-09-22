"""命令行入口：解析参数 → 生成题目 / 批改答案 → 写出结果文件。

两种运行模式（与作业要求一致）::

    python main.py -n 10 -r 10            # 生成 10 道 10 以内的题目
    python main.py -e Exercises.txt -a Answers.txt   # 批改，结果写入 Grade.txt

可选参数（不传即使用默认值，不影响评测调用方式）：

* ``--seed``        固定随机种子，便于复现同一个题目文件；
* ``--output-dir``  结果文件写出的目录，默认为当前目录；
* ``-v/--verbose``  打印更详细的运行信息；
* ``-q/--quiet``    不打印摘要。

返回码：``0`` 成功；``2`` 参数错误；``3`` 文件错误；``4`` 生成或解析错误；
``1`` 未预期的内部错误。
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from .errors import ArgumentError, OutputWriteError, QuizError
from .generator import QuestionGenerator, format_answers, format_exercises
from .grader import GradeResult, grade

#: 不指定 ``-n`` 时默认生成的题目个数。
DEFAULT_COUNT = 10

EXERCISE_FILE = "Exercises.txt"
ANSWER_FILE = "Answers.txt"
GRADE_FILE = "Grade.txt"

USAGE = (
    "python main.py -n <题目个数> -r <数值范围>          # 生成题目\n"
    "python main.py -e <题目文件> -a <答案文件>          # 批改答案"
)


@dataclass(frozen=True)
class GenerateSettings:
    """生成模式的参数。"""

    count: int
    limit: int
    output_dir: Path
    seed: Optional[int] = None
    verbose: bool = False
    quiet: bool = False


@dataclass(frozen=True)
class GradeSettings:
    """批改模式的参数。"""

    exercise_path: str
    answer_path: str
    output_dir: Path
    verbose: bool = False
    quiet: bool = False


Settings = Union[GenerateSettings, GradeSettings]


@dataclass(frozen=True)
class GenerateReport:
    """生成模式的运行结果（供 verbose 输出与单元测试断言）。"""

    count: int
    limit: int
    exercise_path: Path
    answer_path: Path
    elapsed_seconds: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        add_help=False,
        usage=USAGE,
        description="小学四则运算题目生成与批改程序。",
    )
    parser.add_argument("-n", type=int, default=None, help="生成题目的个数（默认 10）")
    parser.add_argument("-r", type=int, default=None, help="数值范围（必须给定）")
    parser.add_argument("-e", default=None, help="待批改的题目文件")
    parser.add_argument("-a", default=None, help="待批改的答案文件")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（便于复现）")
    parser.add_argument("--output-dir", default=".", help="结果文件输出目录")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def parse_args(argv: List[str]) -> Settings:
    """解析命令行参数，返回生成模式或批改模式的配置对象。"""
    parser = build_parser()
    try:
        namespace = parser.parse_args(argv)
    except SystemExit as exc:  # argparse 遇到非法参数会直接退出
        raise ArgumentError(f"命令行参数无法识别：{' '.join(argv)}", USAGE) from exc

    if namespace.help:
        raise ArgumentError("使用说明", USAGE)

    grading = namespace.e is not None or namespace.a is not None
    generating = namespace.n is not None or namespace.r is not None
    if grading and generating:
        raise ArgumentError("生成模式（-n/-r）与批改模式（-e/-a）不能同时使用", USAGE)
    if grading:
        return _parse_grade_settings(namespace)
    return _parse_generate_settings(namespace)


def _parse_generate_settings(namespace: argparse.Namespace) -> GenerateSettings:
    if namespace.r is None:
        # 作业要求：-r 未给出时必须报错并给出帮助信息。
        raise ArgumentError("-r 参数必须给定（它决定题目中数值的范围）", USAGE)
    if namespace.r < 1:
        raise ArgumentError(f"-r 必须是不小于 1 的自然数，当前为 {namespace.r}", USAGE)

    count = DEFAULT_COUNT if namespace.n is None else namespace.n
    if count < 1:
        raise ArgumentError(f"-n 必须是不小于 1 的自然数，当前为 {count}", USAGE)

    return GenerateSettings(
        count=count,
        limit=namespace.r,
        output_dir=Path(namespace.output_dir),
        seed=namespace.seed,
        verbose=namespace.verbose,
        quiet=namespace.quiet,
    )


def _parse_grade_settings(namespace: argparse.Namespace) -> GradeSettings:
    if namespace.e is None or namespace.a is None:
        raise ArgumentError("-e 与 -a 必须同时给出（题目文件与答案文件）", USAGE)
    return GradeSettings(
        exercise_path=namespace.e,
        answer_path=namespace.a,
        output_dir=Path(namespace.output_dir),
        verbose=namespace.verbose,
        quiet=namespace.quiet,
    )


def run_generate(settings: GenerateSettings) -> GenerateReport:
    """执行生成模式：写出 Exercises.txt 与 Answers.txt。"""
    started = time.perf_counter()
    rng = random.Random(settings.seed) if settings.seed is not None else random.Random()
    generator = QuestionGenerator(settings.limit, rng=rng)
    questions = generator.generate(settings.count)

    exercise_path = settings.output_dir / EXERCISE_FILE
    answer_path = settings.output_dir / ANSWER_FILE
    _write_text(exercise_path, format_exercises(questions))
    _write_text(answer_path, format_answers(questions))
    return GenerateReport(
        count=len(questions),
        limit=settings.limit,
        exercise_path=exercise_path,
        answer_path=answer_path,
        elapsed_seconds=time.perf_counter() - started,
    )


def run_grade(settings: GradeSettings) -> GradeResult:
    """执行批改模式：写出 Grade.txt。"""
    result = grade(settings.exercise_path, settings.answer_path)
    _write_text(settings.output_dir / GRADE_FILE, result.format())
    return result


def _write_text(path: Path, text: str) -> None:
    try:
        path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise OutputWriteError(f"文件写入失败：{path}", str(exc)) from exc


def main(argv: Optional[List[str]] = None) -> int:
    """程序主入口，返回进程退出码（便于单元测试直接调用）。"""
    arguments = list(sys.argv[1:] if argv is None else argv)
    _configure_console()

    if "-h" in arguments or "--help" in arguments:
        print(USAGE)
        return 0

    try:
        settings = parse_args(arguments)
        if isinstance(settings, GenerateSettings):
            report = run_generate(settings)
            _report_generate(report, settings)
        else:
            result = run_grade(settings)
            _report_grade(result, settings)
    except QuizError as exc:
        label = "参数错误" if exc.exit_code == 2 else "运行失败"
        # 只打印 message，detail 单独作为"用法"输出，避免提示信息重复冗长。
        print(f"{label}：{exc.message}", file=sys.stderr)
        if exc.exit_code == 2:
            print(f"用法：{exc.detail or USAGE}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # pragma: no cover - 最后一道防线
        print(f"未预期的内部错误：{exc}", file=sys.stderr)
        return 1
    return 0


def _report_generate(report: GenerateReport, settings: GenerateSettings) -> None:
    if not settings.quiet:
        print(f"已生成 {report.count} 道题目（-r {report.limit}）")
        print(f"题目文件：{report.exercise_path}")
        print(f"答案文件：{report.answer_path}")
    if settings.verbose:
        print(f"耗时：{report.elapsed_seconds:.3f} 秒", file=sys.stderr)


def _report_grade(result: GradeResult, settings: GradeSettings) -> None:
    if not settings.quiet:
        print(result.format().rstrip("\n"))
    if settings.verbose:
        for warning in result.warnings:
            print(f"提示：{warning}", file=sys.stderr)


def _configure_console() -> None:
    """让标准输出/错误流在无法表示中文的控制台上也不会抛异常。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # pragma: no cover - 例如 io.StringIO
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):  # pragma: no cover - 极端环境
            continue
