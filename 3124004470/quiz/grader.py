"""批改模块：对应需求 9（``-e`` 题目文件 + ``-a`` 答案文件）。

批改流程：

1. 逐行读入题目文件，剥掉行首的序号，把剩下的表达式解析成表达式树；
2. 逐行读入答案文件，把答案解析成精确分数；
3. 用 ``Fraction`` 精确比较（不使用浮点数，避免 1/3 之类的舍入误差）；
4. 按题目要求的格式输出 ``Grade.txt``：

   ``Correct: 5 (1, 3, 5, 7, 9)`` / ``Wrong: 5 (2, 4, 6, 8, 10)``。

容错策略：题目要求"假设输入的题目都是符合规范的"，但真实文件里难免出现
空行、序号缺失、答案写成 ``2'3/8`` 或 ``2’3/8`` 等情况。这里的原则是
**能判就读、读不懂就算错**：解析不了的行会被记入警告信息并计为错题，
不会让程序直接崩溃。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Tuple

from .errors import MissingFileError, ParseError
from .expression import Expression, evaluate, parse_expression
from .notation import parse_value

#: 形如 "12. 3 + 4 =" 或 "12、3 + 4 =" 的行。
_NUMBERED_LINE = re.compile(r"^\s*(\d+)\s*[.．、:：]\s*(.*?)\s*$")


@dataclass(frozen=True)
class GradeResult:
    """批改结果。"""

    correct: Tuple[int, ...]
    wrong: Tuple[int, ...]
    warnings: Tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.correct) + len(self.wrong)

    def format(self) -> str:
        """按题目要求的格式生成 Grade.txt 的内容。"""
        correct = ", ".join(str(number) for number in self.correct)
        wrong = ", ".join(str(number) for number in self.wrong)
        return (
            f"Correct: {len(self.correct)} ({correct})\n"
            f"\n"
            f"Wrong: {len(self.wrong)} ({wrong})\n"
        )


def read_exercises(path: str) -> Tuple[Dict[int, Expression], List[str]]:
    """读取题目文件，返回 ``(序号 -> 表达式, 警告列表)``。"""
    expressions: Dict[int, Expression] = {}
    warnings: List[str] = []
    for line_number, line in enumerate(_read_lines(path), start=1):
        if not line.strip():
            continue
        match = _NUMBERED_LINE.match(line)
        if not match:
            warnings.append(f"题目文件第 {line_number} 行缺少序号，已跳过：{line}")
            continue
        index = int(match.group(1))
        try:
            expressions[index] = parse_expression(match.group(2))
        except ParseError as exc:
            warnings.append(f"题目文件第 {line_number} 行无法解析（{exc}），按错误处理")
    return expressions, warnings


def read_answers(path: str) -> Tuple[Dict[int, Fraction], List[str]]:
    """读取答案文件，返回 ``(序号 -> 答案, 警告列表)``。"""
    answers: Dict[int, Fraction] = {}
    warnings: List[str] = []
    for line_number, line in enumerate(_read_lines(path), start=1):
        if not line.strip():
            continue
        match = _NUMBERED_LINE.match(line)
        if not match:
            warnings.append(f"答案文件第 {line_number} 行缺少序号，已跳过：{line}")
            continue
        index = int(match.group(1))
        try:
            answers[index] = parse_value(match.group(2))
        except ParseError as exc:
            warnings.append(f"答案文件第 {line_number} 行无法解析（{exc}），按错误处理")
    return answers, warnings


def grade(exercise_path: str, answer_path: str) -> GradeResult:
    """批改两个文件，返回 :class:`GradeResult`。"""
    expressions, warnings = read_exercises(exercise_path)
    answers, answer_warnings = read_answers(answer_path)
    warnings.extend(answer_warnings)

    correct: List[int] = []
    wrong: List[int] = []
    for index in sorted(set(expressions) | set(answers)):
        expression = expressions.get(index)
        answer = answers.get(index)
        if expression is None:
            warnings.append(f"第 {index} 题在题目文件中不存在，按错误处理")
            wrong.append(index)
            continue
        if answer is None:
            warnings.append(f"第 {index} 题在答案文件中没有对应答案，按错误处理")
            wrong.append(index)
            continue
        if evaluate(expression) == answer:
            correct.append(index)
        else:
            wrong.append(index)
    return GradeResult(tuple(correct), tuple(wrong), tuple(warnings))


def _read_lines(path: str) -> List[str]:
    file_path = Path(path)
    if file_path.is_dir():
        raise MissingFileError(f"路径是一个目录而不是文件：{path}")
    if not file_path.exists():
        raise MissingFileError(f"文件不存在：{path}")
    try:
        text = file_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # 兼容记事本另存为 ANSI（GBK）的情况。
        text = file_path.read_text(encoding="gb18030")
    except OSError as exc:  # pragma: no cover - 依赖具体文件系统
        raise MissingFileError(f"读取文件失败：{path}", str(exc)) from exc
    return text.splitlines()
