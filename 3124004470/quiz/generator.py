"""题目生成器（本程序的核心模块）。

生成一道题目的过程
------------------

1. 随机决定这道题用几个运算符（1 ~ 3 个，满足"不超过 3 个"的要求）；
2. 递归地拼出一棵表达式树，**在拼接时就地满足运算约束**：

   * 减法 ``e1 - e2``：先算好左子树的值，再把右子树的取值限制在
     ``<= e1``，因此不可能出现负数；
   * 除法 ``e1 ÷ e2``：要求 ``0 < e1 < e2``，这样商一定落在 ``(0, 1)``
     区间，即真分数；
   * 加法和乘法没有额外约束，可以直接拼。

3. 计算这道题的去重指纹（:func:`quiz.expression.canonical_key`），
   如果指纹已经出现过就丢弃重来——用集合判重是 O(1)，即使生成一万道题
   也不会退化。

所有叶子节点都从 ``-r`` 指定的取值池里挑，取值池里只含"小于 r 的自然数"
与"分子、分母都小于 r 的真分数"，因此天然满足范围要求。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction
from typing import List, Optional, Sequence

from .errors import GenerationError
from .expression import (
    ADD,
    DIV,
    Leaf,
    MUL,
    SUB,
    Expression,
    Node,
    apply_operator,
    canonical_key,
    evaluate,
    to_expression,
)
from .notation import ValuePool, format_value

#: 题目中运算符个数的上限（题目要求"不超过 3 个"）。
MAX_OPERATORS = 3

#: 同一个节点反复尝试仍然拼不出合法子表达式时的重试次数。
#: 实测（tools/benchmark.py）：数值越小越快——不可行的子树能更早放弃，
#: 让上一层换一种结构再试；取值 2~4 时生成一万道题约 0.4~0.5 秒，
#: 而 48 时约 0.5 秒并且在小范围里更容易卡在死路上。这里取 4 作为折中，
#: 同时自检脚本确认它对"范围内所有题目"的覆盖率没有影响。
_NODE_RETRIES = 4

#: 连续多少次没能产生"新的不重复题目"就判断为"范围内题目已被取完"。
_MAX_CONSECUTIVE_FAILURES = 20000


@dataclass(frozen=True)
class Question:
    """一道题目：表达式、题面文本、答案与答案文本。"""

    index: int
    expression: Expression
    expression_text: str
    answer: Fraction
    answer_text: str

    @classmethod
    def build(
        cls, index: int, expression: Expression, answer: Optional[Fraction] = None
    ) -> "Question":
        # 生成器在拼树时已经算出答案，允许直接传入，避免重复遍历求值。
        if answer is None:
            answer = evaluate(expression)
        return cls(
            index=index,
            expression=expression,
            expression_text=f"{to_expression(expression)} =",
            answer=answer,
            answer_text=format_value(answer),
        )


class QuestionGenerator:
    """按 ``-r`` 的范围生成互不重复的四则运算题目。"""

    def __init__(
        self,
        limit: int,
        rng: Optional[random.Random] = None,
        max_operators: int = MAX_OPERATORS,
        max_consecutive_failures: int = _MAX_CONSECUTIVE_FAILURES,
    ) -> None:
        self.limit = limit
        self.rng = rng or random.Random()
        self.max_operators = max_operators
        self.max_consecutive_failures = max_consecutive_failures
        self.pool = ValuePool(limit, self.rng)

        operators = [ADD, SUB, MUL]
        # 是否把除法纳入候选运算符：
        # * 取值池里存在 e1 < e2 的两个值 → 一次除法就能得到真分数；
        # * 否则只要允许 2 个以上运算符，仍可以用 (1 × 1) ÷ (1 + 1) 这种方式
        #   造出真分数（-r 2 时只有数值 1，但这条路依然成立，穷举对照证实
        #   该范围内确实存在除法题目）；
        # * -r 1 时所有取值都是 0，除法结果恒为 0，只能放弃除法。
        has_greater_pair = self.pool.has_strictly_greater_pair()
        can_build_fraction_with_two_operators = (
            self.pool.values[-1] > 0 and max_operators >= 2
        )
        if has_greater_pair or can_build_fraction_with_two_operators:
            operators.append(DIV)
        self.operators: Sequence[str] = tuple(operators)

    def generate(self, count: int) -> List[Question]:
        """生成 ``count`` 道互不重复的题目。

        在给定范围内题目确实不够多时抛出 :class:`GenerationError`，
        而不是无限循环。
        """
        if count < 1:
            raise ValueError("题目个数必须是不小于 1 的整数")

        questions: List[Question] = []
        seen: set[str] = set()
        consecutive_failures = 0
        while len(questions) < count:
            built = self._random_expression_with_value()
            if built is None:
                consecutive_failures += 1
            else:
                expression, answer = built
                key = canonical_key(expression)
                if key not in seen:
                    seen.add(key)
                    consecutive_failures = 0
                    questions.append(
                        Question.build(len(questions) + 1, expression, answer)
                    )
                    continue
                consecutive_failures += 1

            if consecutive_failures >= self.max_consecutive_failures:
                raise GenerationError(
                    f"在 -r {self.limit} 的范围内无法再生成新的题目："
                    f"已生成 {len(questions)} 道，要求 {count} 道",
                    "可以增大 -r 的范围，或减少 -n 的题目个数",
                    produced=len(questions),
                )
        return questions

    # ---------------------------------------------------------------- 内部实现

    def _random_expression(self) -> Optional[Expression]:
        """随机拼出一个满足全部约束的表达式。"""
        built = self._random_expression_with_value()
        return None if built is None else built[0]

    def _random_expression_with_value(
        self,
    ) -> Optional[tuple[Expression, Fraction]]:
        """随机拼出一个表达式，同时返回它的值（避免重复求值）。"""
        operator_total = self.rng.randint(1, self.max_operators)
        for _ in range(_NODE_RETRIES):
            built = self._build(operator_total)
            if built is not None:
                return built
        return None

    def _build(
        self,
        operators: int,
        at_most: Optional[Fraction] = None,
        greater_than: Optional[Fraction] = None,
    ) -> Optional[tuple[Expression, Fraction]]:
        """构造恰好含 ``operators`` 个运算符、且取值满足约束的表达式。

        返回值是 ``(表达式, 表达式的值)``：把值一路往上传递，父节点可以直接
        运算得到自己的值，避免对子表达式反复做整树求值（这是性能优化的关键一步）。
        """
        if operators == 0:
            value = self.pool.choose(at_most, greater_than)
            return None if value is None else (Leaf(value), value)

        for _ in range(_NODE_RETRIES):
            built = self._build_once(operators)
            if built is None:
                continue
            expression, value = built
            if at_most is not None and value > at_most:
                continue
            if greater_than is not None and value <= greater_than:
                continue
            return built
        return None

    def _build_once(self, operators: int) -> Optional[tuple[Expression, Fraction]]:
        op = self.rng.choice(self.operators)
        left_operators = self.rng.randint(0, operators - 1)
        right_operators = operators - 1 - left_operators

        left_built = self._build(left_operators)
        if left_built is None:
            return None
        left, left_value = left_built

        if op == SUB:
            # 减法：右子树的值必须不超过左子树的值，保证不出现负数。
            right_built = self._build(right_operators, at_most=left_value)
        elif op == DIV:
            # 除法：要求 0 < 左值 < 右值，商才是真分数。
            if left_value <= 0:
                return None
            right_built = self._build(right_operators, greater_than=left_value)
        else:
            right_built = self._build(right_operators)
        if right_built is None:
            return None
        right, right_value = right_built
        return Node(op, left, right), apply_operator(op, left_value, right_value)


def format_exercises(questions: Sequence[Question]) -> str:
    """按题目要求的格式拼出 Exercises.txt 的内容。"""
    return "".join(f"{item.index}. {item.expression_text}\n" for item in questions)


def format_answers(questions: Sequence[Question]) -> str:
    """按题目要求的格式拼出 Answers.txt 的内容。"""
    return "".join(f"{item.index}. {item.answer_text}\n" for item in questions)
