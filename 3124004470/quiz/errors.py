"""异常体系。

程序只抛出本模块定义的异常，每个异常都带有自己的进程返回码：

* ``2`` 命令行参数错误（例如缺少必须的 ``-r``）；
* ``3`` 文件读写错误（题目文件/答案文件不存在、无法写出）；
* ``4`` 生成或解析错误（范围内凑不出足够多的不重复题目、表达式无法解析）。

所有异常都继承自 :class:`QuizError`，因此上层只需要 ``except QuizError``
就能保证"任何已知错误都不会让程序以未捕获异常的方式退出"。
"""

from __future__ import annotations


class QuizError(Exception):
    """本程序所有自定义异常的基类。"""

    exit_code = 1

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __str__(self) -> str:  # pragma: no cover - 仅影响展示
        if self.detail:
            return f"{self.message}（{self.detail}）"
        return self.message


class ArgumentError(QuizError):
    """命令行参数不合法（缺参数、数值越界、模式冲突）。"""

    exit_code = 2


class FileAccessError(QuizError):
    """文件读写相关的错误基类。"""

    exit_code = 3


class MissingFileError(FileAccessError):
    """待读取的文件不存在，或者路径指向目录。"""


class OutputWriteError(FileAccessError):
    """结果文件无法写出（目录不存在、无权限等）。"""


class GenerationError(QuizError):
    """在给定范围内无法生成要求数量的不重复题目。

    这是"数学上做不到"的情形（例如 ``-r 2`` 时可能的题目总数很少），
    程序会给出明确的提示而不是一直死循环。
    """

    exit_code = 4

    def __init__(self, message: str, detail: str | None = None, produced: int = 0) -> None:
        super().__init__(message, detail)
        #: 放弃前实际已经生成的题目个数，便于调用方（如自检脚本）与
        #: "该范围的理论上限"做对照。
        self.produced = produced


class ParseError(QuizError):
    """表达式或答案文本不符合规范，无法解析。"""

    exit_code = 4
