"""异常体系的单元测试。

设计目标：确认每种异常都带正确的返回码，并且都属于 ``QuizError``
这一基类，这样命令行层只需要捕获基类即可避免"异常退出"。
"""

from __future__ import annotations

import unittest

from quiz.errors import (
    ArgumentError,
    FileAccessError,
    GenerationError,
    MissingFileError,
    OutputWriteError,
    ParseError,
    QuizError,
)


class ExceptionHierarchyTests(unittest.TestCase):
    def test_all_errors_inherit_base(self) -> None:
        """所有自定义异常都必须继承 QuizError。"""
        for exception_type in (
            ArgumentError,
            FileAccessError,
            MissingFileError,
            OutputWriteError,
            GenerationError,
            ParseError,
        ):
            with self.subTest(exception=exception_type.__name__):
                self.assertTrue(issubclass(exception_type, QuizError))

    def test_exit_codes(self) -> None:
        """返回码约定：参数 2、文件 3、生成/解析 4、未知 1。"""
        self.assertEqual(ArgumentError.exit_code, 2)
        self.assertEqual(MissingFileError.exit_code, 3)
        self.assertEqual(OutputWriteError.exit_code, 3)
        self.assertEqual(GenerationError.exit_code, 4)
        self.assertEqual(ParseError.exit_code, 4)
        self.assertEqual(QuizError.exit_code, 1)

    def test_message_and_detail(self) -> None:
        """异常保留 message 与 detail，便于打印帮助信息。"""
        error = ArgumentError("-r 参数必须给定", "python main.py -n 10 -r 10")
        self.assertEqual(error.message, "-r 参数必须给定")
        self.assertIn("python main.py", str(error))
        self.assertEqual(ArgumentError("-r 必须给定").__str__(), "-r 必须给定")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
