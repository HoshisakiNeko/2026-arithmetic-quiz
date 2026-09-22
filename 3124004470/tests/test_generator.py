"""生成器模块的单元测试（核心模块测试）。

测试思路：把需求 3~6、8 逐条翻译成断言——

* 需求 3：减法不出现负数；
* 需求 4：除法的商是真分数；
* 需求 5：运算符不超过 3 个；
* 需求 6：任意两道题不能通过交换 ``+`` / ``×`` 变成同一道；
* 需求 2：所有数值都在 ``-r`` 范围内；
* 需求 8：能生成一万道题。

另外附上"自己判自己"的回归测试：把生成出来的题面重新解析、重新求值，
必须与 Answers.txt 里写的答案完全一致。
"""

from __future__ import annotations

import random
import sys
import time
import unittest
from fractions import Fraction
from unittest import mock

from quiz.errors import GenerationError
from quiz.expression import (
    DIV,
    Leaf,
    Node,
    canonical_key,
    evaluate,
    is_valid,
    operator_count,
    parse_expression,
    within_range,
)
from quiz.generator import (
    MAX_OPERATORS,
    Question,
    QuestionGenerator,
    format_answers,
    format_exercises,
)
from quiz.notation import ValuePool, format_value


class GeneratorConstraintTests(unittest.TestCase):
    """用小批量题目逐条验证需求约束。"""

    @classmethod
    def setUpClass(cls) -> None:
        generator = QuestionGenerator(10, rng=random.Random(20240915))
        cls.questions = generator.generate(400)
        cls.pool = ValuePool(10)

    def test_count_and_indexing(self) -> None:
        """题目数量正确，编号从 1 开始连续。"""
        self.assertEqual(len(self.questions), 400)
        self.assertEqual([q.index for q in self.questions], list(range(1, 401)))

    def test_operator_count_within_limit(self) -> None:
        """需求 5：每道题的运算符个数在 1~3 之间。"""
        for question in self.questions:
            with self.subTest(index=question.index):
                count = operator_count(question.expression)
                self.assertGreaterEqual(count, 1)
                self.assertLessEqual(count, MAX_OPERATORS)

    def test_no_negative_intermediate_result(self) -> None:
        """需求 3：不存在减法结果为负的子表达式。"""
        for question in self.questions:
            with self.subTest(index=question.index):
                self.assertTrue(is_valid(question.expression), question.expression_text)

    def test_division_results_are_proper_fractions(self) -> None:
        """需求 4：每个除法子表达式的商都是真分数。"""
        checked = 0
        for question in self.questions:
            for node in _iter_division_nodes(question.expression):
                checked += 1
                quotient = evaluate(node)
                self.assertGreater(quotient, 0)
                self.assertLess(quotient, 1)
        self.assertGreater(checked, 0, "生成的题目里应当包含除法题")

    def test_all_leaves_within_range(self) -> None:
        """需求 2：所有数值（含真分数分母）都小于 r。"""
        for question in self.questions:
            with self.subTest(index=question.index):
                self.assertTrue(within_range(question.expression, self.pool))

    def test_no_duplicate_questions(self) -> None:
        """需求 6：去重指纹互不相同。"""
        keys = [canonical_key(question.expression) for question in self.questions]
        self.assertEqual(len(keys), len(set(keys)))

    def test_no_visually_identical_questions(self) -> None:
        """打印出的题面也必须互不相同（否则文件里会出现"看起来重复"的题）。"""
        texts = [question.expression_text for question in self.questions]
        self.assertEqual(len(texts), len(set(texts)))

    def test_answers_match_printed_expressions(self) -> None:
        """回归自检：题面重新解析求值后必须等于记录的答案。"""
        for question in self.questions:
            with self.subTest(index=question.index):
                reparsed = parse_expression(question.expression_text)
                self.assertEqual(evaluate(reparsed), question.answer)

    def test_answers_are_formatted_exactly(self) -> None:
        """答案文本与数值一致（直接调用格式化函数再比较）。"""
        for question in self.questions:
            with self.subTest(index=question.index):
                self.assertEqual(question.answer_text, format_value(question.answer))


def _iter_division_nodes(expression):
    """遍历所有除法节点（供上面的断言使用）。"""
    if isinstance(expression, Node):
        if expression.op == DIV:
            yield expression
        yield from _iter_division_nodes(expression.left)
        yield from _iter_division_nodes(expression.right)


class GeneratorBehaviourTests(unittest.TestCase):
    def test_same_seed_generates_same_questions(self) -> None:
        """固定随机种子后结果可复现（便于写测试和写博客）。"""
        first = QuestionGenerator(10, rng=random.Random(42)).generate(20)
        second = QuestionGenerator(10, rng=random.Random(42)).generate(20)
        self.assertEqual([q.expression_text for q in first], [q.expression_text for q in second])

    def test_different_seeds_generate_different_questions(self) -> None:
        """不同种子应给出不同的题目集合。"""
        first = QuestionGenerator(10, rng=random.Random(1)).generate(20)
        second = QuestionGenerator(10, rng=random.Random(2)).generate(20)
        self.assertNotEqual(
            [q.expression_text for q in first], [q.expression_text for q in second]
        )

    def test_single_question(self) -> None:
        """-n 1 也要正常工作。"""
        questions = QuestionGenerator(10, rng=random.Random(5)).generate(1)
        self.assertEqual(len(questions), 1)
        self.assertTrue(is_valid(questions[0].expression))

    def test_count_must_be_positive(self) -> None:
        """-n 0 之类的输入属于调用错误。"""
        with self.assertRaises(ValueError):
            QuestionGenerator(10).generate(0)

    def test_small_range_still_works(self) -> None:
        """-r 2 时只有数值 1，也要能生成若干合法题目。"""
        questions = QuestionGenerator(2, rng=random.Random(3)).generate(5)
        self.assertEqual(len(questions), 5)
        for question in questions:
            self.assertTrue(is_valid(question.expression))
            self.assertNotIn("÷", question.expression_text)

    def test_range_one_does_not_crash(self) -> None:
        """-r 1 的退化情况（只有 0 可用）不应崩溃。"""
        questions = QuestionGenerator(1, rng=random.Random(3)).generate(3)
        self.assertEqual(len(questions), 3)
        for question in questions:
            self.assertEqual(question.answer, 0)

    def test_impossible_request_raises_generation_error(self) -> None:
        """范围内题目不够时必须明确报错，而不是死循环。"""
        generator = QuestionGenerator(2, rng=random.Random(7), max_consecutive_failures=2000)
        with self.assertRaises(GenerationError) as context:
            generator.generate(5000)
        self.assertIn("无法再生成新的题目", context.exception.message)

    def test_duplicate_expressions_are_retried(self) -> None:
        """范围很小时会不断碰到重复题目，程序应当丢弃重试而不是卡住。"""
        generator = QuestionGenerator(3, rng=random.Random(11), max_consecutive_failures=5000)
        questions = generator.generate(300)
        keys = {canonical_key(question.expression) for question in questions}
        self.assertEqual(len(questions), 300)
        self.assertEqual(len(keys), 300)

    def test_random_expression_helper_returns_valid_expression(self) -> None:
        """内部辅助方法 _random_expression 返回的表达式必须合法。"""
        generator = QuestionGenerator(10, rng=random.Random(3))
        for _ in range(20):
            expression = generator._random_expression()
            self.assertIsNotNone(expression)
            self.assertTrue(is_valid(expression))
            self.assertLessEqual(operator_count(expression), MAX_OPERATORS)

    def test_generation_gives_up_when_building_always_fails(self) -> None:
        """构造器完全失败时要返回 None 并最终报 GenerationError（防御性分支）。"""
        generator = QuestionGenerator(10, rng=random.Random(3), max_consecutive_failures=3)
        with mock.patch.object(QuestionGenerator, "_build", return_value=None):
            self.assertIsNone(generator._random_expression_with_value())
            self.assertIsNone(generator._random_expression())
            with self.assertRaises(GenerationError):
                generator.generate(1)

    def test_division_with_zero_left_operand_is_rejected(self) -> None:
        """左操作数为 0 的除法（商为 0，不是真分数）必须放弃重试。"""
        generator = QuestionGenerator(3, rng=random.Random(0))
        zero = (Leaf(Fraction(0)), Fraction(0))
        with mock.patch.object(generator.rng, "choice", return_value=DIV), mock.patch.object(
            QuestionGenerator, "_build", return_value=zero
        ):
            self.assertIsNone(generator._build_once(1))

    def test_node_build_fails_when_left_subtree_fails(self) -> None:
        """左子树构造失败时整棵子树也要放弃（防御性分支）。"""
        generator = QuestionGenerator(10, rng=random.Random(0))
        with mock.patch.object(QuestionGenerator, "_build", return_value=None):
            self.assertIsNone(generator._build_once(2))

    def test_ten_thousand_questions(self) -> None:
        """需求 8：支持生成一万道题目，并且全部满足约束。"""
        generator = QuestionGenerator(10, rng=random.Random(20240915))
        started = time.perf_counter()
        questions = generator.generate(10000)
        elapsed = time.perf_counter() - started

        self.assertEqual(len(questions), 10000)
        # 覆盖率工具（trace）会给每一行插桩，耗时不再代表真实性能，
        # 因此只有在正常运行时才检查时间上限。
        if sys.gettrace() is None:
            self.assertLess(elapsed, 10.0, "一万道题目应在 10 秒内生成完毕")

        keys = {canonical_key(question.expression) for question in questions}
        self.assertEqual(len(keys), 10000)
        # 抽检 200 道，确认约束与答案都对得上，避免全量校验拖慢测试。
        for question in random.Random(1).sample(questions, 200):
            self.assertLessEqual(operator_count(question.expression), MAX_OPERATORS)
            self.assertTrue(is_valid(question.expression))
            self.assertTrue(within_range(question.expression, generator.pool))
            self.assertEqual(
                evaluate(parse_expression(question.expression_text)), question.answer
            )


class FileFormatTests(unittest.TestCase):
    def test_exercise_and_answer_file_content(self) -> None:
        """Exercises.txt / Answers.txt 的行格式为 "序号. 内容"。"""
        question = Question(
            index=1,
            expression=parse_expression("1 + 2"),
            expression_text="1 + 2 =",
            answer=Fraction(3),
            answer_text="3",
        )
        self.assertEqual(format_exercises([question]), "1. 1 + 2 =\n")
        self.assertEqual(format_answers([question]), "1. 3\n")

    def test_question_build_computes_answer_when_not_given(self) -> None:
        """不传答案时 Question.build 会自己求值（默认参数分支）。"""
        question = Question.build(2, parse_expression("1/2 + 1/3"))
        self.assertEqual(question.answer, Fraction(5, 6))
        self.assertEqual(question.answer_text, "5/6")
        self.assertEqual(question.index, 2)
        self.assertEqual(question.expression_text, "1/2 + 1/3 =")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
