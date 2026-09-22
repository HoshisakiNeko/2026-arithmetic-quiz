"""表达式模块的单元测试。

测试思路：

* **求值**：用 `Fraction` 精确比较，覆盖优先级与括号；
* **打印**：验证括号规则——既要"该加括号的时候加"，也要保证
  "结构不同的表达式打印出的字符串不同"，否则题目文件里会出现
  看起来重复的题目；
* **去重指纹**：直接采用题目里给出的四个例子（``23+45`` 与 ``45+23``
  重复、``3+(2+1)`` 与 ``1+2+3`` 重复、``1+2+3`` 与 ``3+2+1`` 不重复）
  作为断言，确保实现与题意完全一致；
* **解析**：与打印互为逆运算，非法输入抛 ``ParseError``。
"""

from __future__ import annotations

import unittest
from fractions import Fraction

from quiz.errors import ParseError
from quiz.expression import (
    ADD,
    DIV,
    MUL,
    SUB,
    Leaf,
    Node,
    canonical_key,
    evaluate,
    is_valid,
    iter_leaves,
    operator_count,
    parse_expression,
    to_expression,
    tokenize,
    within_range,
)
from quiz.notation import ValuePool


def parse(text: str):
    return parse_expression(text)


class EvaluateTests(unittest.TestCase):
    def test_leaf_and_priority(self) -> None:
        """乘除优先于加减。"""
        self.assertEqual(evaluate(Leaf(Fraction(3))), Fraction(3))
        self.assertEqual(evaluate(parse("1 + 2 × 3")), Fraction(7))
        self.assertEqual(evaluate(parse("(1 + 2) × 3")), Fraction(9))

    def test_fraction_arithmetic(self) -> None:
        """分数的四则运算必须精确（例：1/6 + 1/8 = 7/24）。"""
        self.assertEqual(evaluate(parse("1/6 + 1/8")), Fraction(7, 24))
        self.assertEqual(evaluate(parse("2'3/8")), Fraction(19, 8))
        self.assertEqual(evaluate(parse("1/2 ÷ 3")), Fraction(1, 6))

    def test_left_associative_chain(self) -> None:
        """同级运算按左结合理解（与打印规则一致）。"""
        self.assertEqual(evaluate(parse("8 - 3 - 2")), Fraction(3))
        self.assertEqual(evaluate(parse("8 ÷ 4 ÷ 2")), Fraction(1))

    def test_operator_count_and_leaves(self) -> None:
        """运算符个数与叶子遍历。"""
        expression = parse("1 + 2 × (3 - 1)")
        self.assertEqual(operator_count(expression), 3)
        self.assertEqual(operator_count(Leaf(Fraction(1))), 0)
        values = [leaf.value for leaf in iter_leaves(expression)]
        self.assertEqual(values, [Fraction(1), Fraction(2), Fraction(3), Fraction(1)])

    def test_manually_built_tree_prints_like_source(self) -> None:
        """手工搭出的树（不经过解析）也应打印正确。"""
        tree = Node(ADD, Leaf(Fraction(1)), Node(MUL, Leaf(Fraction(2)), Leaf(Fraction(3))))
        self.assertEqual(to_expression(tree), "1 + 2 × 3")


class PrintTests(unittest.TestCase):
    def test_no_parentheses_when_not_needed(self) -> None:
        """左结合链不需要括号。"""
        self.assertEqual(to_expression(parse("1 + 2 + 3")), "1 + 2 + 3")
        self.assertEqual(to_expression(parse("1 + 2 × 3")), "1 + 2 × 3")
        self.assertEqual(to_expression(parse("8 ÷ 4 ÷ 2")), "8 ÷ 4 ÷ 2")

    def test_parentheses_for_right_nested_same_precedence(self) -> None:
        """右侧嵌套同优先级时必须加括号，否则会变成另一棵树。"""
        self.assertEqual(to_expression(parse("1 + (2 + 3)")), "1 + (2 + 3)")
        self.assertEqual(to_expression(parse("1 - (2 - 3)")), "1 - (2 - 3)")
        self.assertEqual(to_expression(parse("1 × (2 ÷ 3)")), "1 × (2 ÷ 3)")

    def test_parentheses_for_lower_precedence_child(self) -> None:
        """子表达式优先级更低时必须加括号。"""
        self.assertEqual(to_expression(parse("(1 + 2) × 3")), "(1 + 2) × 3")
        self.assertEqual(to_expression(parse("(1 - 2) ÷ 3")), "(1 - 2) ÷ 3")

    def test_printed_text_is_unique_per_tree(self) -> None:
        """结构不同的树（1+(2+3) 与 (1+2)+3）必须打印出不同的字符串。"""
        left_nested = parse("1 + (2 + 3)")
        right_nested = parse("(1 + 2) + 3")
        self.assertNotEqual(to_expression(left_nested), to_expression(right_nested))

    def test_print_parse_round_trip(self) -> None:
        """打印再解析必须得到同一棵树。"""
        for text in (
            "1 + 2",
            "1 + 2 + 3",
            "1 + (2 + 3)",
            "(1 + 2) × 3",
            "2/3 ÷ (1/2 + 1/4)",
            "2'3/8 - 1/2",
        ):
            with self.subTest(text=text):
                expression = parse(text)
                self.assertEqual(parse(to_expression(expression)), expression)


class CanonicalKeyTests(unittest.TestCase):
    def test_commutative_swap_is_duplicate(self) -> None:
        """交换 + 或 × 的左右操作数算同一道题。"""
        self.assertEqual(canonical_key(parse("23 + 45")), canonical_key(parse("45 + 23")))
        self.assertEqual(canonical_key(parse("6 × 8")), canonical_key(parse("8 × 6")))

    def test_associativity_alone_is_not_duplicate(self) -> None:
        """题目明确要求：1+2+3 与 3+2+1 不是同一道题。"""
        self.assertNotEqual(canonical_key(parse("1 + 2 + 3")), canonical_key(parse("3 + 2 + 1")))

    def test_nested_swap_with_same_shape_is_duplicate(self) -> None:
        """题目给出的例子：3+(2+1) 与 1+2+3 是同一道题。"""
        self.assertEqual(canonical_key(parse("3 + (2 + 1)")), canonical_key(parse("1 + 2 + 3")))

    def test_non_commutative_order_matters(self) -> None:
        """减法与除法交换左右就变成另一道题。"""
        self.assertNotEqual(canonical_key(parse("5 - 3")), canonical_key(parse("3 - 5")))
        self.assertNotEqual(canonical_key(parse("1 ÷ 2")), canonical_key(parse("2 ÷ 1")))

    def test_commutativity_inside_subtraction(self) -> None:
        """被减数内部的加法可以交换。"""
        self.assertEqual(canonical_key(parse("(1 + 2) - 3")), canonical_key(parse("(2 + 1) - 3")))

    def test_equal_values_with_different_notation(self) -> None:
        """2/4 与 1/2 是同一个数值，指纹也应相同。"""
        self.assertEqual(canonical_key(parse("1/2 + 1")), canonical_key(parse("2/4 + 1")))


class ValidityTests(unittest.TestCase):
    def test_subtraction_must_not_be_negative(self) -> None:
        """减法不允许出现负数。"""
        self.assertTrue(is_valid(parse("5 - 3")))
        self.assertFalse(is_valid(parse("3 - 5")))

    def test_division_result_must_be_proper_fraction(self) -> None:
        """除法的结果必须是真分数（0 < 商 < 1）。"""
        self.assertTrue(is_valid(parse("1 ÷ 2")))
        self.assertTrue(is_valid(parse("1/3 ÷ 1/2")))
        self.assertFalse(is_valid(parse("2 ÷ 1")))
        self.assertFalse(is_valid(parse("1 ÷ 1")))

    def test_invalid_subtree_makes_whole_expression_invalid(self) -> None:
        """任何一个子表达式违规，整道题就不合法。"""
        self.assertFalse(is_valid(parse("1 + (2 - 3)")))
        self.assertFalse(is_valid(parse("1 + (3 ÷ 2)")))

    def test_within_range_checks_every_leaf(self) -> None:
        """范围校验：所有叶子都要落在 -r 的取值池里。"""
        pool = ValuePool(10)
        self.assertTrue(within_range(parse("9 × 1/2"), pool))
        self.assertFalse(within_range(parse("10 + 1"), pool))
        self.assertFalse(within_range(parse("1/10 + 1"), pool))  # 分母不小于 10


class ParseTests(unittest.TestCase):
    def test_tokenize_skips_spaces_and_trailing_equals(self) -> None:
        """切分记号时忽略空格与结尾的等号。"""
        self.assertEqual(tokenize("1 + 2 ="), ["1", "+", "2"])
        self.assertEqual(tokenize(" ( 3 × 4 ) "), ["(", "3", "×", "4", ")"])

    def test_parse_accepts_alternative_symbols(self) -> None:
        """兼容 ASCII 的 * / 与全角符号，方便批改别人给的文件。"""
        self.assertEqual(parse_expression("1 * 2").op, MUL)
        self.assertEqual(parse_expression("1 / 2").op, DIV)
        self.assertEqual(parse_expression("3 － 1").op, SUB)
        self.assertEqual(parse_expression("2 ＋ 1").op, ADD)

    def test_invalid_expressions_raise_parse_error(self) -> None:
        """各种非法输入都要报 ParseError，而不是抛 IndexError 之类。"""
        for text in ("1 +", "(1 + 2", "1 + 2)", "1 2", "", "1 + + 2", "abc"):
            with self.subTest(text=text):
                with self.assertRaises(ParseError):
                    parse_expression(text)

    def test_unrecognized_characters_are_reported(self) -> None:
        """夹在记号之间的奇怪字符（如 # 或汉字）要报错并指出内容。"""
        with self.assertRaises(ParseError) as context:
            parse_expression("1 + # 2")
        self.assertIn("#", context.exception.message)
        with self.assertRaises(ParseError):
            parse_expression("1 + 二")

    def test_extra_closing_parenthesis_is_reported(self) -> None:
        """多余的右括号要报“括号不匹配”。"""
        with self.assertRaises(ParseError) as context:
            parse_expression(")")
        self.assertIn("括号不匹配", context.exception.message)
        with self.assertRaises(ParseError):
            parse_expression("1 + )")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
