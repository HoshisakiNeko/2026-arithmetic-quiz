"""命令行入口与端到端流程的单元测试。

测试思路：直接调用 ``quiz.cli.main(argv)``（等价于 ``python main.py ...``），
断言"返回码 + 生成的三个文件内容"，避免启动子进程带来的额外开销。

覆盖范围：

* 生成模式：默认目录、指定目录、``-n`` 默认值、随机种子可复现、一万道题；
* 批改模式：全对、部分错、写出的 Grade.txt 内容；
* 参数校验：缺少 ``-r``、``-n``/``-r`` 非法、模式冲突、``-e`` 缺 ``-a``、帮助；
* 文件错误：题目文件不存在、输出目录不存在；
* 控制台编码：标准输出不支持中文时也不能异常退出。
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from quiz.cli import (
    ANSWER_FILE,
    EXERCISE_FILE,
    GRADE_FILE,
    GenerateSettings,
    GradeSettings,
    main,
    parse_args,
)
from quiz.errors import ArgumentError, OutputWriteError


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.temp_path = Path(self._temp_dir.name)

    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        """调用命令行入口，返回 (返回码, 标准输出, 标准错误)。"""
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def read(self, name: str) -> str:
        return (self.temp_path / name).read_text(encoding="utf-8")


class GenerateModeTests(CliTestCase):
    def test_generates_two_files_with_expected_format(self) -> None:
        """-n 5 -r 10 应生成 5 道题，两个文件的格式都要符合要求。"""
        code, stdout, _ = self.invoke(
            "-n", "5", "-r", "10", "--output-dir", str(self.temp_path)
        )
        self.assertEqual(code, 0)
        exercises = self.read(EXERCISE_FILE).splitlines()
        answers = self.read(ANSWER_FILE).splitlines()
        self.assertEqual(len(exercises), 5)
        self.assertEqual(len(answers), 5)
        for number, line in enumerate(exercises, start=1):
            self.assertTrue(line.startswith(f"{number}. "), line)
            self.assertTrue(line.endswith(" ="), line)
        for number, line in enumerate(answers, start=1):
            self.assertTrue(line.startswith(f"{number}. "), line)
        self.assertIn("已生成 5 道题目", stdout)

    def test_default_count_is_ten(self) -> None:
        """只给 -r 时默认生成 10 道题。"""
        code, _, _ = self.invoke("-r", "10", "--output-dir", str(self.temp_path))
        self.assertEqual(code, 0)
        self.assertEqual(len(self.read(EXERCISE_FILE).splitlines()), 10)

    def test_seed_makes_output_reproducible(self) -> None:
        """同样的种子应生成完全相同的题目文件。"""
        self.invoke("-n", "20", "-r", "10", "--seed", "2024", "--output-dir", str(self.temp_path))
        first = self.read(EXERCISE_FILE)
        self.invoke("-n", "20", "-r", "10", "--seed", "2024", "--output-dir", str(self.temp_path))
        self.assertEqual(first, self.read(EXERCISE_FILE))

    def test_writes_into_current_directory_by_default(self) -> None:
        """不指定 --output-dir 时，结果写在当前目录（题目要求）。"""
        previous = os.getcwd()
        os.chdir(self.temp_path)
        self.addCleanup(os.chdir, previous)
        code, _, _ = self.invoke("-n", "3", "-r", "10")
        self.assertEqual(code, 0)
        self.assertTrue((self.temp_path / EXERCISE_FILE).exists())
        self.assertTrue((self.temp_path / ANSWER_FILE).exists())

    def test_ten_thousand_questions_end_to_end(self) -> None:
        """需求 8 的端到端验证：一万道题要在合理时间内生成。"""
        started = time.perf_counter()
        code, _, _ = self.invoke(
            "-n", "10000", "-r", "10", "--output-dir", str(self.temp_path)
        )
        elapsed = time.perf_counter() - started
        self.assertEqual(code, 0)
        self.assertEqual(len(self.read(EXERCISE_FILE).splitlines()), 10000)
        self.assertEqual(len(self.read(ANSWER_FILE).splitlines()), 10000)
        # 覆盖率工具会给每行插桩，此时耗时不代表真实性能，故只在正常运行时断言。
        if sys.gettrace() is None:
            self.assertLess(elapsed, 15.0)

    def test_quiet_mode_suppresses_stdout(self) -> None:
        """--quiet 时不打印摘要，但仍然写出文件。"""
        code, stdout, _ = self.invoke(
            "-n", "2", "-r", "10", "--quiet", "--output-dir", str(self.temp_path)
        )
        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")
        self.assertTrue((self.temp_path / EXERCISE_FILE).exists())

    def test_verbose_mode_prints_timing(self) -> None:
        """--verbose 时把耗时写到标准错误流。"""
        code, stdout, stderr = self.invoke(
            "-n", "2", "-r", "10", "--verbose", "--output-dir", str(self.temp_path)
        )
        self.assertEqual(code, 0)
        self.assertIn("耗时", stderr)
        self.assertNotIn("耗时", stdout)

    def test_output_directory_missing_returns_code_three(self) -> None:
        """输出目录不存在时返回 3，而不是抛出未捕获异常。"""
        code, _, stderr = self.invoke(
            "-n", "2", "-r", "10", "--output-dir", str(self.temp_path / "nope")
        )
        self.assertEqual(code, 3)
        self.assertIn("写入失败", stderr)

    def test_impossible_count_returns_code_four(self) -> None:
        """范围内题目不够时返回 4，并给出可读的提示。"""
        code, _, stderr = self.invoke("-n", "10000", "-r", "2", "--output-dir", str(self.temp_path))
        self.assertEqual(code, 4)
        self.assertIn("无法再生成新的题目", stderr)


class GradeModeTests(CliTestCase):
    def write(self, name: str, text: str) -> str:
        path = self.temp_path / name
        path.write_text(text, encoding="utf-8", newline="\n")
        return str(path)

    def test_grade_writes_grade_file(self) -> None:
        """批改结果写入 Grade.txt，格式与题目样例一致。"""
        exercises = self.write("Ex.txt", "1. 1 + 2 =\n2. 2 + 2 =\n")
        answers = self.write("An.txt", "1. 3\n2. 5\n")
        code, stdout, _ = self.invoke(
            "-e", exercises, "-a", answers, "--output-dir", str(self.temp_path)
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.read(GRADE_FILE), "Correct: 1 (1)\n\nWrong: 1 (2)\n")
        self.assertIn("Correct: 1 (1)", stdout)

    def test_generate_then_grade_is_all_correct(self) -> None:
        """先生成再批改自己生成的答案，应当全部判对（端到端回归）。"""
        self.invoke("-n", "30", "-r", "10", "--seed", "99", "--output-dir", str(self.temp_path))
        code, _, _ = self.invoke(
            "-e", str(self.temp_path / EXERCISE_FILE),
            "-a", str(self.temp_path / ANSWER_FILE),
            "--output-dir", str(self.temp_path),
        )
        self.assertEqual(code, 0)
        grade_text = self.read(GRADE_FILE)
        self.assertIn("Correct: 30 (", grade_text)
        self.assertIn("Wrong: 0 ()", grade_text)

    def test_wrong_answers_are_detected(self) -> None:
        """篡改答案文件后，批改程序必须能指出错误的题号。"""
        self.invoke("-n", "5", "-r", "10", "--seed", "5", "--output-dir", str(self.temp_path))
        lines = self.read(ANSWER_FILE).splitlines()
        lines[0] = "1. 123456"  # 故意改错第一题
        tampered = self.write("Wrong.txt", "\n".join(lines) + "\n")
        code, _, _ = self.invoke(
            "-e", str(self.temp_path / EXERCISE_FILE), "-a", tampered,
            "--output-dir", str(self.temp_path),
        )
        self.assertEqual(code, 0)
        self.assertIn("Wrong: 1 (1)", self.read(GRADE_FILE))

    def test_missing_exercise_file_returns_code_three(self) -> None:
        """题目文件不存在时返回 3。"""
        answers = self.write("An.txt", "1. 3\n")
        code, _, stderr = self.invoke(
            "-e", str(self.temp_path / "missing.txt"), "-a", answers
        )
        self.assertEqual(code, 3)
        self.assertIn("文件不存在", stderr)

    def test_verbose_prints_warnings(self) -> None:
        """--verbose 时把容错产生的警告写到标准错误流。"""
        exercises = self.write("Ex.txt", "1. 1 + 2 =\n坏行\n")
        answers = self.write("An.txt", "1. 3\n")
        code, _, stderr = self.invoke(
            "-e", exercises, "-a", answers, "--verbose", "--output-dir", str(self.temp_path)
        )
        self.assertEqual(code, 0)
        self.assertIn("缺少序号", stderr)


class ArgumentTests(CliTestCase):
    def test_missing_range_parameter(self) -> None:
        """作业要求：-r 必须给定，否则报错并给出帮助信息。"""
        code, _, stderr = self.invoke("-n", "10")
        self.assertEqual(code, 2)
        self.assertIn("-r 参数必须给定", stderr)
        self.assertIn("用法", stderr)

    def test_no_arguments_at_all(self) -> None:
        """一个参数都不给时同样报参数错误。"""
        code, _, stderr = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("用法", stderr)

    def test_invalid_range_values(self) -> None:
        """-r 小于 1 属于非法参数。"""
        code, _, stderr = self.invoke("-n", "1", "-r", "0")
        self.assertEqual(code, 2)
        self.assertIn("-r 必须是不小于 1", stderr)

    def test_invalid_count_values(self) -> None:
        """-n 小于 1 属于非法参数。"""
        code, _, stderr = self.invoke("-n", "0", "-r", "10")
        self.assertEqual(code, 2)
        self.assertIn("-n 必须是不小于 1", stderr)

    def test_modes_cannot_be_mixed(self) -> None:
        """生成模式与批改模式不能同时使用。"""
        code, _, stderr = self.invoke("-n", "5", "-r", "10", "-e", "a.txt", "-a", "b.txt")
        self.assertEqual(code, 2)
        self.assertIn("不能同时使用", stderr)

    def test_grade_requires_both_files(self) -> None:
        """只给 -e 或只给 -a 都是错误的。"""
        code, _, stderr = self.invoke("-e", "Ex.txt")
        self.assertEqual(code, 2)
        self.assertIn("必须同时给出", stderr)

    def test_non_integer_argument_is_rejected(self) -> None:
        """-n abc 由 argparse 拦截，转换成参数错误而不是直接退出。"""
        code, _, stderr = self.invoke("-n", "abc", "-r", "10")
        self.assertEqual(code, 2)
        self.assertIn("参数错误", stderr)

    def test_help_returns_zero(self) -> None:
        """--help 输出用法并以 0 退出。"""
        code, stdout, stderr = self.invoke("--help")
        self.assertEqual(code, 0)
        self.assertIn("python main.py", stdout)
        self.assertEqual(stderr, "")

    def test_parse_args_help_request(self) -> None:
        """parse_args 遇到 -h 时用 ArgumentError 传递用法说明（API 层约定）。"""
        with self.assertRaises(ArgumentError) as context:
            parse_args(["-h"])
        self.assertEqual(context.exception.exit_code, 2)
        self.assertIn("python main.py", str(context.exception.detail))

    def test_parse_args_returns_settings_objects(self) -> None:
        """两种模式分别返回 GenerateSettings / GradeSettings。"""
        generate = parse_args(["-n", "3", "-r", "8"])
        self.assertIsInstance(generate, GenerateSettings)
        self.assertEqual((generate.count, generate.limit, generate.output_dir), (3, 8, Path(".")))
        grade = parse_args(["-e", "Ex.txt", "-a", "An.txt"])
        self.assertIsInstance(grade, GradeSettings)
        self.assertEqual(grade.exercise_path, "Ex.txt")

    def test_unexpected_error_returns_code_one(self) -> None:
        """最后一道防线：未预期异常转成返回码 1，绝不异常退出。"""
        with mock.patch("quiz.cli.run_generate", side_effect=RuntimeError("内部故障")):
            code, _, stderr = self.invoke("-n", "1", "-r", "10")
        self.assertEqual(code, 1)
        self.assertIn("未预期的内部错误", stderr)

    def test_output_write_error_is_translated(self) -> None:
        """_write_text 把 OSError 翻译成 OutputWriteError（白盒）。"""
        from quiz.cli import _write_text

        with self.assertRaises(OutputWriteError):
            _write_text(self.temp_path / "nope" / "a.txt", "x")

    def test_ascii_console_does_not_break_the_program(self) -> None:
        """标准输出是 ASCII 编码时也不能异常退出（真实环境常见问题）。"""
        buffer = io.BytesIO()
        ascii_stdout = io.TextIOWrapper(buffer, encoding="ascii", errors="strict")
        self.addCleanup(ascii_stdout.close)
        stderr = io.StringIO()
        with contextlib.redirect_stdout(ascii_stdout), contextlib.redirect_stderr(stderr):
            code = main(["-n", "2", "-r", "10", "--output-dir", str(self.temp_path)])
        ascii_stdout.flush()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.read(EXERCISE_FILE).splitlines()), 2)

    def test_configure_console_tolerates_failure(self) -> None:
        """极端环境下 reconfigure 失败也不能让程序崩溃（防御性分支）。"""
        from quiz.cli import _configure_console

        broken = mock.Mock()
        broken.reconfigure.side_effect = ValueError("该流不支持重配置")
        with mock.patch.object(sys, "stdout", broken), mock.patch.object(sys, "stderr", broken):
            _configure_console()
        self.assertEqual(broken.reconfigure.call_count, 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
