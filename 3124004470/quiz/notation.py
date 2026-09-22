"""数值表示与取值池。

本模块负责三件事：

1. **取值池**：按照 ``-r`` 参数构造所有可用的数值。题目中的数值包括
   自然数与真分数，且"自然数、真分数、真分数的分母"都要落在范围之内：

   * 自然数：``1 ~ r-1``（要求里"``-r 10`` 生成 10 以内、不包括 10"）；
   * 真分数：``p/q``，其中 ``1 <= p < q <= r-1``，并且只保留最简形式，
     因此同一个数值不会重复出现。

2. **输出格式**：按题目要求把分数写成 ``3/5``（真分数）或 ``2'3/8``
   （假分数写成带分数）。

3. **输入解析**：解析时同时兼容 ``'``、``’``（Word 自动替换出的右单引号）、
   全角数字等常见写法，避免因为一个字符差异导致判分失败。
"""

from __future__ import annotations

import math
import random
import unicodedata
from bisect import bisect_right
from fractions import Fraction
from typing import List, Optional

from .errors import ParseError

#: 带分数的分隔符（输出用 ASCII 单引号，解析时同时接受 ’ 与 ` ）。
MIXED_SEPARATOR = "'"

#: 解析时需要先归一化的引号字符。
_QUOTE_CHARACTERS = str.maketrans({"’": "'", "‘": "'", "`": "'", "′": "'"})


def format_value(value: Fraction) -> str:
    """把数值格式化成题目要求的写法。

    说明：曾经尝试用 ``functools.lru_cache`` 缓存结果（取值池里的数值只有
    几十个，看起来命中率很高），但实测反而变慢——``Fraction`` 的哈希需要
    处理分子与分母两个整数，缓存查找的开销超过了省下的分支判断，
    所以最终没有使用缓存。

    >>> format_value(Fraction(7, 24))
    '7/24'
    >>> format_value(Fraction(19, 8))
    "2'3/8"
    >>> format_value(Fraction(4, 1))
    '4'
    """
    if value.denominator == 1:
        return str(value.numerator)
    if abs(value.numerator) < value.denominator:  # 真分数
        return f"{value.numerator}/{value.denominator}"
    # 假分数写成带分数：整数部分'分子/分母
    whole, remainder = divmod(value.numerator, value.denominator)
    return f"{whole}{MIXED_SEPARATOR}{remainder}/{value.denominator}"


def parse_value(text: str) -> Fraction:
    """解析一个数值（自然数、真分数或带分数）。

    支持 ``7``、``3/5``、``2'3/8``、``2’3/8``、全角数字等写法，
    其他情况抛出 :class:`ParseError`。
    """
    if text is None:
        raise ParseError("数值不能为空")
    cleaned = unicodedata.normalize("NFKC", str(text)).translate(_QUOTE_CHARACTERS)
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        raise ParseError("数值不能为空")

    if MIXED_SEPARATOR in cleaned:
        whole_text, _, fraction_text = cleaned.partition(MIXED_SEPARATOR)
        if not whole_text or not fraction_text:
            raise ParseError(f"带分数格式不正确：{text}")
        return _to_natural(whole_text) + _parse_fraction(fraction_text, text)
    if "/" in cleaned:
        return _parse_fraction(cleaned, text)
    return _to_natural(cleaned)


def _to_natural(text: str) -> Fraction:
    if not text.isdigit():
        raise ParseError(f"不是合法的自然数：{text}")
    return Fraction(int(text))


def _parse_fraction(text: str, original: str) -> Fraction:
    numerator_text, sep, denominator_text = text.partition("/")
    if not sep or not numerator_text.isdigit() or not denominator_text.isdigit():
        raise ParseError(f"不是合法的分数：{original}")
    denominator = int(denominator_text)
    if denominator == 0:
        raise ParseError(f"分数的分母不能为 0：{original}")
    return Fraction(int(numerator_text), denominator)


def build_value_pool(limit: int) -> List[Fraction]:
    """按范围上限 ``limit`` 生成所有可用数值（由小到大）。

    ``limit`` 为 1 时没有任何小于 1 的自然数，按题目"自然数包括 0"
    的定义退化为只含 ``0`` 的取值池，程序仍能正常运行。
    """
    if limit < 1:
        raise ValueError("limit 必须是不小于 1 的整数")
    if limit == 1:
        return [Fraction(0)]

    values = {Fraction(number) for number in range(1, limit)}
    for numerator in range(1, limit):
        for denominator in range(numerator + 1, limit):
            if math.gcd(numerator, denominator) == 1:
                values.add(Fraction(numerator, denominator))
    return sorted(values)


class ValuePool:
    """取值池：支持按区间随机取值，供生成器在约束下挑选叶子节点。"""

    def __init__(self, limit: int, rng: Optional[random.Random] = None) -> None:
        self.limit = limit
        self.values = build_value_pool(limit)
        self._rng = rng or random.Random()

    def choose(
        self,
        at_most: Optional[Fraction] = None,
        greater_than: Optional[Fraction] = None,
    ) -> Optional[Fraction]:
        """在 ``[at_most]`` 与 ``(greater_than, ...)`` 约束下随机取一个值。

        没有满足条件的取值时返回 ``None``，由调用方决定重试或放弃。
        """
        low_index = 0
        high_index = len(self.values)
        if greater_than is not None:
            low_index = bisect_right(self.values, greater_than)
        if at_most is not None:
            # 闭区间：等于 at_most 的取值也要保留，因此用 bisect_right。
            high_index = bisect_right(self.values, at_most)
        if low_index >= high_index:
            return None
        # 直接取下标而不是 self.values[low:high]：切片会为每次取值复制一个列表，
        # 而叶子节点是生成过程中调用最频繁的地方（一万道题要取几万个值）。
        return self.values[self._rng.randrange(low_index, high_index)]

    def has_strictly_greater_pair(self) -> bool:
        """是否存在 ``L < R`` 的两个取值（除法的必要前提）。"""
        return len(self.values) >= 2 and self.values[0] < self.values[-1]
