"""算术表达式的表示、求值、打印、去重指纹与解析。

表达式用"二叉树 + 冻结数据类"表示，好处是：

* 表达式天然不可变，子树可以被多个题目共享，不需要深拷贝；
* :func:`canonical_key` 只需要比较结构，不必反复做字符串处理；
* :func:`to_expression` 与 :func:`parse_expression` 互为逆运算，
  程序可以把自己打印出来的题目重新解析回来验证答案（自检用）。

三种运算符在内部统一用 ``+ - * /`` 表示，打印时再通过
:data:`DISPLAY_OPERATORS` 映射成题目要求的 ``+ - × ÷``。
如果老师要求输出 ``*`` 和 ``/``，只需要改这一张映射表。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterator, List, Tuple, Union

from .errors import ParseError
from .notation import ValuePool, format_value, parse_value

#: 内部运算符编码。
ADD = "+"
SUB = "-"
MUL = "*"
DIV = "/"

OPERATORS: Tuple[str, ...] = (ADD, SUB, MUL, DIV)

#: 打印表达式时使用的符号（题目要求的写法）。
DISPLAY_OPERATORS = {ADD: "+", SUB: "-", MUL: "×", DIV: "÷"}

#: 运算符优先级：+ - 为 1 级，× ÷ 为 2 级。
PRECEDENCE = {ADD: 1, SUB: 1, MUL: 2, DIV: 2}

#: 满足交换律的运算符（用于题目去重）。
COMMUTATIVE = frozenset({ADD, MUL})

#: 解析时把各种等价写法统一成内部编码。
_OPERATOR_ALIASES = {
    "+": ADD,
    "＋": ADD,
    "-": SUB,
    "−": SUB,  # U+2212
    "－": SUB,
    "*": MUL,
    "×": MUL,
    "＊": MUL,
    "/": DIV,
    "÷": DIV,
    "／": DIV,
}

_TOKEN_PATTERN = re.compile(r"(\d+(?:'\d+/\d+|/\d+)?)|([()+\-−－＋*×＊/÷／])")

#: 解析时用到的记号集合：加減法与乘除法分别处理，保证 × ÷ 优先级高于 + -。
_ADDITIVE_TOKENS = frozenset({"+", "＋", "-", "−", "－"})
_MULTIPLICATIVE_TOKENS = frozenset({"*", "×", "＊", "/", "÷", "／"})


@dataclass(frozen=True)
class Leaf:
    """叶子节点：一个自然数或真分数。"""

    value: Fraction


@dataclass(frozen=True)
class Node:
    """内部节点：``left op right``。"""

    op: str
    left: "Expression"
    right: "Expression"


Expression = Union[Leaf, Node]


def evaluate(expr: Expression) -> Fraction:
    """精确求值（使用 ``Fraction``，不会出现浮点误差）。"""
    if isinstance(expr, Leaf):
        return expr.value
    return apply_operator(expr.op, evaluate(expr.left), evaluate(expr.right))


def apply_operator(op: str, left: Fraction, right: Fraction) -> Fraction:
    """对两个已经求好值的操作数应用运算符。

    生成器在拼装表达式时会同时保存子树的值，直接调用这个函数就能得到父节点的值，
    不必再对整棵树做一次遍历求值。
    """
    if op == ADD:
        return left + right
    if op == SUB:
        return left - right
    if op == MUL:
        return left * right
    return left / right


def operator_count(expr: Expression) -> int:
    """表达式中运算符的个数（题目要求不超过 3 个）。"""
    if isinstance(expr, Leaf):
        return 0
    return 1 + operator_count(expr.left) + operator_count(expr.right)


def iter_leaves(expr: Expression) -> Iterator[Leaf]:
    """深度优先遍历所有叶子节点。"""
    if isinstance(expr, Leaf):
        yield expr
        return
    yield from iter_leaves(expr.left)
    yield from iter_leaves(expr.right)


def to_expression(expr: Expression) -> str:
    """把表达式树打印成题目字符串（运算符与等号前后留空格）。

    括号规则：当子表达式的优先级更低，或者优先级相同却出现在右侧时加括号
    （四则运算按左结合理解）。这样"结构不同的表达式一定打印出不同的字符串"，
    生成结果里不会出现看起来一模一样的题目。

    >>> to_expression(Node(ADD, Leaf(Fraction(1)), Leaf(Fraction(2))))
    '1 + 2'
    """
    return _render(expr, None, False)


def _render(expr: Expression, parent_op: str | None, is_right: bool) -> str:
    if isinstance(expr, Leaf):
        return format_value(expr.value)
    text = (
        f"{_render(expr.left, expr.op, False)} "
        f"{DISPLAY_OPERATORS[expr.op]} "
        f"{_render(expr.right, expr.op, True)}"
    )
    if parent_op is not None and _needs_parentheses(expr.op, parent_op, is_right):
        return f"({text})"
    return text


def _needs_parentheses(child_op: str, parent_op: str, is_right: bool) -> bool:
    child_precedence = PRECEDENCE[child_op]
    parent_precedence = PRECEDENCE[parent_op]
    if child_precedence != parent_precedence:
        return child_precedence < parent_precedence
    # 同级运算按左结合理解，因此右侧的子表达式必须补括号。
    return is_right


def canonical_key(expr: Expression) -> str:
    """题目的去重指纹。

    按题目要求，"可以通过有限次交换 ``+`` / ``×`` 左右操作数变成同一道"
    的题目算重复，而结合律**不算**（题目明确指出 ``1+2+3`` 与 ``3+2+1``
    不是同一道题）。因此这里只做一件事：对满足交换律的节点，把两个子树的
    指纹排成固定顺序，再拼成字符串。

    >>> key1 = canonical_key(parse_expression("1 + 2 + 3"))
    >>> key2 = canonical_key(parse_expression("3 + (2 + 1)"))
    >>> key1 == key2
    True
    >>> key3 = canonical_key(parse_expression("3 + 2 + 1"))
    >>> key1 == key3
    False
    """
    if isinstance(expr, Leaf):
        # 叶子直接用"分子/分母"作为指纹：数值等价的两个写法（1/2 与 2/4）
        # 会被 Fraction 约分成同一个值，因此指纹必然一致，同时省掉一次
        # 带分数格式化的分支判断。
        return f"n{expr.value.numerator}/{expr.value.denominator}"
    left = canonical_key(expr.left)
    right = canonical_key(expr.right)
    if expr.op in COMMUTATIVE and right < left:
        left, right = right, left
    return f"{expr.op}[{left}|{right}]"


def is_valid(expr: Expression) -> bool:
    """检查表达式是否满足题目的两条运算约束。

    1. 减法不允许出现负数（``e1 >= e2``）；
    2. 除法的结果必须是真分数（``0 < e1 / e2 < 1``，且除数不为 0）。
    """
    if isinstance(expr, Leaf):
        return expr.value >= 0
    if not (is_valid(expr.left) and is_valid(expr.right)):
        return False
    left = evaluate(expr.left)
    right = evaluate(expr.right)
    if expr.op == SUB:
        return left >= right
    if expr.op == DIV:
        return right > 0 and 0 < left / right < 1
    return True


def within_range(expr: Expression, pool: ValuePool) -> bool:
    """检查所有叶子是否都取自 ``-r`` 指定的取值池。"""
    allowed = set(pool.values)
    return all(leaf.value in allowed for leaf in iter_leaves(expr))


def tokenize(text: str) -> List[str]:
    """把表达式切分成记号（数字/分数、运算符、括号）。"""
    cleaned = text.strip()
    if cleaned.endswith("="):
        cleaned = cleaned[:-1].strip()
    tokens: List[str] = []
    position = 0
    for match in _TOKEN_PATTERN.finditer(cleaned):
        if match.start() != position:
            gap = cleaned[position : match.start()]
            if gap.strip():
                raise ParseError(f"表达式中有无法识别的内容：{gap!r}")
        tokens.append(match.group(0))
        position = match.end()
    if cleaned[position:].strip():
        raise ParseError(f"表达式中有无法识别的内容：{cleaned[position:]!r}")
    if not tokens:
        raise ParseError("表达式为空")
    return tokens


def parse_expression(text: str) -> Expression:
    """解析表达式字符串，非法输入抛出 :class:`ParseError`。

    文法::

        expression := term (('+' | '-') term)*
        term       := factor (('×' | '÷') factor)*
        factor     := number | fraction | '(' expression ')'
    """
    parser = _Parser(tokenize(text))
    expr = parser.parse_expression()
    if not parser.at_end():
        raise ParseError(f"表达式在 {parser.peek()!r} 之后出现了多余内容")
    return expr


class _Parser:
    """递归下降解析器。"""

    def __init__(self, tokens: List[str]) -> None:
        self._tokens = tokens
        self._index = 0

    def at_end(self) -> bool:
        return self._index >= len(self._tokens)

    def peek(self) -> str:
        if self.at_end():
            raise ParseError("表达式不完整")
        return self._tokens[self._index]

    def next_token(self) -> str:
        token = self.peek()
        self._index += 1
        return token

    def parse_expression(self) -> Expression:
        expr = self.parse_term()
        while not self.at_end() and self.peek() in _ADDITIVE_TOKENS:
            op = _OPERATOR_ALIASES[self.next_token()]
            expr = Node(op, expr, self.parse_term())
        return expr

    def parse_term(self) -> Expression:
        expr = self.parse_factor()
        while not self.at_end() and self.peek() in _MULTIPLICATIVE_TOKENS:
            op = _OPERATOR_ALIASES[self.next_token()]
            expr = Node(op, expr, self.parse_factor())
        return expr

    def parse_factor(self) -> Expression:
        token = self.next_token()
        if token == "(":
            expr = self.parse_expression()
            if self.at_end() or self.next_token() != ")":
                raise ParseError("括号不匹配")
            return expr
        if token == ")":
            raise ParseError("括号不匹配")
        return Leaf(parse_number(token))


def parse_number(token: str) -> Fraction:
    """解析叶子节点的数值（复用 notation 模块的规则）。"""
    return parse_value(token)
