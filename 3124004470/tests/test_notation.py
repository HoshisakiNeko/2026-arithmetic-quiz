"""数值写法与取值池的单元测试。

测试思路：数值的格式化（``7/24``、``2'3/8``）与解析是一对互逆操作，
重点验证"界面上看到的写法"与"内部精确分数"能够来回转换，
并覆盖取值池的边界（``-r 1``、``-r 2``）与非法输入。
"""

from __future__ import annotations

import random
import unittest
from fractions import Fraction

from quiz.errors import ParseError
from quiz.notation import ValuePool, build_value_pool, format_value, parse_value


class FormatValueTests(unittest.TestCase):
    def test_natural_number(self) -> None:
        """自然数直接输出整数。"""
        self.assertEqual(format_value(Fraction(0)), "0")
        self.assertEqual(format_value(Fraction(9)), "9")

    def test_proper_fraction(self) -> None:
        """真分数输出 分子/分母。"""
        self.assertEqual(format_value(Fraction(3, 5)), "3/5")
        self.assertEqual(format_value(Fraction(7, 24)), "7/24")

    def test_improper_fraction_becomes_mixed_number(self) -> None:
        """假分数输出带分数（题目要求 2'3/8 这种写法）。"""
        self.assertEqual(format_value(Fraction(19, 8)), "2'3/8")
        self.assertEqual(format_value(Fraction(3, 2)), "1'1/2")

    def test_fraction_is_reduced(self) -> None:
        """分子分母会约分，避免出现 2/4 这种写法。"""
        self.assertEqual(format_value(Fraction(2, 4)), "1/2")


class ParseValueTests(unittest.TestCase):
    def test_parse_forms(self) -> None:
        """四种常见写法都要能解析出来。"""
        self.assertEqual(parse_value("7"), Fraction(7))
        self.assertEqual(parse_value("3/5"), Fraction(3, 5))
        self.assertEqual(parse_value("2'3/8"), Fraction(19, 8))
        self.assertEqual(parse_value("2’3/8"), Fraction(19, 8))  # Word 的右单引号

    def test_parse_tolerates_spaces_and_fullwidth(self) -> None:
        """多余空格与全角数字不应导致判分失败。"""
        self.assertEqual(parse_value(" 2 ' 3 / 8 "), Fraction(19, 8))
        self.assertEqual(parse_value("７"), Fraction(7))

    def test_round_trip(self) -> None:
        """格式化后再解析必须得到原值。"""
        for value in (Fraction(0), Fraction(5), Fraction(3, 7), Fraction(29, 6)):
            with self.subTest(value=value):
                self.assertEqual(parse_value(format_value(value)), value)

    def test_invalid_values_raise_parse_error(self) -> None:
        """非法写法统一抛出 ParseError（便于按错题处理而不是崩溃）。"""
        for text in ("", "abc", "1/0", "2'", "'3/8", "1//2", None):
            with self.subTest(text=text):
                with self.assertRaises(ParseError):
                    parse_value(text)


class ValuePoolTests(unittest.TestCase):
    def test_pool_for_ten_contains_naturals_and_fractions(self) -> None:
        """-r 10 的取值池：9 个自然数 + 27 个最简真分数，按大小有序。"""
        values = build_value_pool(10)
        self.assertEqual(len(values), 36)
        self.assertEqual(len([v for v in values if v.denominator == 1]), 9)
        self.assertEqual(values[0], Fraction(1, 9))  # 最小的是 1/9
        self.assertEqual(values[-1], Fraction(9))  # 最大的是自然数 9
        self.assertIn(Fraction(1), values)
        self.assertTrue(all(value < 10 for value in values))
        self.assertIn(Fraction(1, 2), values)
        self.assertIn(Fraction(8, 9), values)
        # 每个数值只出现一次（例如 1/2 与 2/4 是同一个数值，只保留最简形式）
        self.assertEqual(len(values), len(set(values)))
        self.assertEqual(values.count(Fraction(1, 2)), 1)
        self.assertEqual(values, sorted(values))

    def test_pool_for_one_is_degenerate(self) -> None:
        """-r 1 时不存在小于 1 的自然数，退化为只含 0 的取值池。"""
        self.assertEqual(build_value_pool(1), [Fraction(0)])

    def test_pool_for_two_contains_only_one(self) -> None:
        """-r 2 时只有自然数 1 可用（分母必须小于 2，因此没有真分数）。"""
        self.assertEqual(build_value_pool(2), [Fraction(1)])

    def test_pool_rejects_invalid_limit(self) -> None:
        """范围上限必须是自然数。"""
        with self.assertRaises(ValueError):
            build_value_pool(0)

    def test_choose_respects_constraints(self) -> None:
        """带上限/下界取值时不会越界（减法与除法的约束靠它保证）。"""
        pool = ValuePool(10, random.Random(1))
        for _ in range(200):
            value = pool.choose(at_most=Fraction(3))
            self.assertIsNotNone(value)
            self.assertLessEqual(value, Fraction(3))
            other = pool.choose(greater_than=Fraction(1, 2))
            self.assertGreater(other, Fraction(1, 2))

    def test_choose_returns_none_when_no_candidate(self) -> None:
        """约束区间为空时返回 None，由调用方重试，而不是抛异常。"""
        pool = ValuePool(10, random.Random(1))
        self.assertIsNone(pool.choose(at_most=Fraction(1, 2), greater_than=Fraction(1, 2)))
        self.assertIsNone(pool.choose(greater_than=Fraction(9)))

    def test_has_strictly_greater_pair(self) -> None:
        """判断取值池里是否存在 e1 < e2 的一对值（能否出除法题）。"""
        self.assertTrue(ValuePool(10).has_strictly_greater_pair())
        self.assertFalse(ValuePool(2).has_strictly_greater_pair())
        self.assertFalse(ValuePool(1).has_strictly_greater_pair())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
