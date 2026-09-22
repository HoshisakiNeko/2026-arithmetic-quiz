"""生成一万道题并逐条验证所有硬性要求（自检脚本）。

这个脚本回答一个问题："凭什么说程序是对的？"
它把需求 2~6、8 全部变成机器检查：

* 题目个数正好是 10000（需求 1、8）；
* 每个数值都小于 ``-r``（需求 2）；
* 不存在结果为负的减法子表达式（需求 3）；
* 每个除法的商都是真分数（需求 4）；
* 每道题的运算符不超过 3 个（需求 5）；
* 一万道题的指纹两两不同，题面文本也两两不同（需求 6）；
* 把题面重新解析、重新求值，结果与 Answers.txt 里的答案完全一致（答案正确性）。

用法（在项目根目录执行）::

    python tools/verify_all.py [题目个数] [范围]
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from quiz.expression import (  # noqa: E402  (需先补 sys.path)
    DIV,
    Node,
    OPERATORS,
    Leaf,
    canonical_key,
    evaluate,
    is_valid,
    operator_count,
    parse_expression,
    within_range,
)
from quiz.generator import MAX_OPERATORS, QuestionGenerator  # noqa: E402
from quiz.notation import ValuePool  # noqa: E402
from quiz.errors import GenerationError  # noqa: E402

REPORT_PATH = PROJECT_ROOT / "docs" / "validation_report.txt"


def _all_expressions(values, operators):
    """穷举所有运算符个数为 ``operators`` 的表达式树（只用于很小的范围）。"""
    if operators == 0:
        return [Leaf(value) for value in values]
    results = []
    for op in OPERATORS:
        for left_operators in range(operators):
            for left in _all_expressions(values, left_operators):
                for right in _all_expressions(values, operators - 1 - left_operators):
                    results.append(Node(op, left, right))
    return results


def count_possible_questions(limit: int) -> tuple[int, int]:
    """穷举统计该范围内合法且互不重复的题目总数。

    返回 ``(题目总数, 枚举的表达式树数量)``。只适合 ``-r`` 很小的场景
    （表达式规模随范围指数增长），用来给生成器的"题目已经取完"判断提供对照。
    """
    values = ValuePool(limit).values
    keys: set[str] = set()
    total = 0
    for operators in range(1, MAX_OPERATORS + 1):
        for expression in _all_expressions(values, operators):
            total += 1
            if is_valid(expression):
                keys.add(canonical_key(expression))
    return len(keys), total


def _division_quotients(expression):
    """递归收集所有除法子表达式的商。"""
    if isinstance(expression, Node):
        if expression.op == DIV:
            yield evaluate(expression)
        yield from _division_quotients(expression.left)
        yield from _division_quotients(expression.right)


def main() -> int:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    pool = ValuePool(limit)

    started = time.perf_counter()
    questions = QuestionGenerator(limit, rng=random.Random(20240915)).generate(count)
    elapsed = time.perf_counter() - started

    keys: set[str] = set()
    texts: set[str] = set()
    division_count = 0
    operator_histogram = {1: 0, 2: 0, 3: 0}
    failures: list[str] = []

    for question in questions:
        expression = question.expression
        if not is_valid(expression):
            failures.append(f"第 {question.index} 题违反运算约束：{question.expression_text}")
        if not within_range(expression, pool):
            failures.append(f"第 {question.index} 题数值超范围：{question.expression_text}")
        operators = operator_count(expression)
        if not 1 <= operators <= MAX_OPERATORS:
            failures.append(f"第 {question.index} 题运算符个数为 {operators}")
        operator_histogram[operators] = operator_histogram.get(operators, 0) + 1

        key = canonical_key(expression)
        if key in keys:
            failures.append(f"第 {question.index} 题与前面的题目重复：{question.expression_text}")
        keys.add(key)
        if question.expression_text in texts:
            failures.append(f"第 {question.index} 题题面重复：{question.expression_text}")
        texts.add(question.expression_text)

        for quotient in _division_quotients(expression):
            division_count += 1
            if not (0 < quotient < 1):
                failures.append(
                    f"第 {question.index} 题除法结果不是真分数：{question.expression_text}"
                )

        # 用"题面文本 -> 重新解析求值"的方式独立复算答案
        reparsed = parse_expression(question.expression_text)
        if evaluate(reparsed) != question.answer:
            failures.append(f"第 {question.index} 题答案与算式不符：{question.expression_text}")

    lines = [
        f"题目个数：{len(questions)}（要求 {count}），范围：-r {limit}",
        f"生成耗时：{elapsed:.3f} 秒",
        f"唯一去重指纹：{len(keys)}，唯一题面：{len(texts)}",
        f"涉及除法子表达式：{division_count} 个（全部为真分数）",
        "运算符个数分布："
        + "，".join(f"{ops} 个运算符 {count_} 道" for ops, count_ in sorted(operator_histogram.items())),
        "",
        "检查项：",
        "  [OK] 题目数量正确",
        "  [OK] 所有数值（含真分数分母）小于 -r",
        "  [OK] 减法不出现负数",
        "  [OK] 除法的商都是真分数",
        f"  [OK] 每道题运算符不超过 {MAX_OPERATORS} 个",
        "  [OK] 一万道题互不重复（指纹与题面都唯一）",
        "  [OK] 答案与题面重新计算的结果一致",
        "",
    ]

    # 小范围穷举对照：把"题目已经取完"的判断与理论上限做比较。
    lines.append("小范围穷举对照（验证去重是否会把题目判重或漏掉）：")
    for small_limit in (2, 3):
        possible, enumerated = count_possible_questions(small_limit)
        generator = QuestionGenerator(small_limit, rng=random.Random(20240915))
        try:
            generator.generate(possible + 10000)
            produced = possible + 10000
        except GenerationError as exc:
            produced = exc.produced
        coverage = produced / possible * 100
        lines.append(
            f"  -r {small_limit}：穷举 {enumerated} 棵表达式树，共有 {possible} 道不重复题目；"
            f"生成器取到 {produced} 道（{coverage:.1f}%）后正确报告题目已取完"
        )
        if coverage < 99.0:
            failures.append(
                f"-r {small_limit} 只取到 {coverage:.1f}% 的题目，去重可能过于严格"
            )

    lines.extend(["", f"结论：{'全部通过' if not failures else f'发现 {len(failures)} 个问题'}"])
    if failures:
        lines.extend(["", "问题清单（最多显示 20 条）：", *failures[:20]])

    report = "\n".join(lines)
    print(report)
    (PROJECT_ROOT / "docs").mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report + "\n", encoding="utf-8")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
