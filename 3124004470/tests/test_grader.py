"""批改模块（需求 9）的单元测试。

测试思路：

* 正常场景：故意构造"对错掺半"的答案文件，检查判对、判错与统计数量；
* 输出格式：Grade.txt 的文本必须与题目给出的样例逐字符一致；
* 容错场景：空行、缺少序号、答案写成带分数、答案文件用 GBK 编码、
  题目文件里有多余空格等，都要能正确处理；
* 异常场景：文件不存在或传入了目录时报文件错误。
"""

from __future__ import annotations

import random
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

from quiz.errors import MissingFileError
from quiz.expression import evaluate
from quiz.grader import GradeResult, grade, read_answers, read_exercises

EXERCISES = """1. 1 + 2 =
2. 5 - 3 =
3. 1/6 + 1/8 =
4. 1 ÷ 2 =
5. 2 × 3 =
"""


class GraderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.temp_path = Path(self._temp_dir.name)

    def write(self, name: str, text: str, encoding: str = "utf-8") -> str:
        path = self.temp_path / name
        path.write_text(text, encoding=encoding, newline="\n")
        return str(path)


class ReadFileTests(GraderTestCase):
    def test_read_exercises(self) -> None:
        """题目文件解析成 序号 -> 表达式。"""
        path = self.write("Ex.txt", EXERCISES)
        expressions, warnings = read_exercises(path)
        self.assertEqual(sorted(expressions), [1, 2, 3, 4, 5])
        self.assertEqual(warnings, [])
        self.assertEqual(evaluate(expressions[3]), Fraction(7, 24))

    def test_read_answers_with_mixed_number(self) -> None:
        """答案支持整数、真分数与带分数。"""
        path = self.write("An.txt", "1. 3\n2. 2\n3. 7/24\n4. 1/2\n5. 2'1/2\n")
        answers, warnings = read_answers(path)
        self.assertEqual(warnings, [])
        self.assertEqual(answers[3], Fraction(7, 24))
        self.assertEqual(answers[5], Fraction(5, 2))

    def test_read_tolerates_spaces_fullwidth_and_blank_lines(self) -> None:
        """多余空格、全角的句点与数字、空行都不应影响解析。"""
        path = self.write("Ex.txt", "\n1．  1   +   2 =  \n\n２. 3 × 4 =\n")
        expressions, warnings = read_exercises(path)
        self.assertEqual(warnings, [])
        self.assertEqual(sorted(expressions), [1, 2])

    def test_read_gbk_encoded_file(self) -> None:
        """记事本另存为 ANSI（GBK）的题目文件也要能读。"""
        # 内容里放了全角数字：GBK 下的字节不是合法 UTF-8，才能触发"编码回退"分支；
        # 纯 ASCII 的内容用 UTF-8 也能解码，测不到这条分支。
        path = self.write("Ex.txt", "1. １ + ２ =\n", encoding="gb18030")
        expressions, warnings = read_exercises(path)
        self.assertEqual(warnings, [])
        self.assertEqual(len(expressions), 1)
        self.assertEqual(evaluate(expressions[1]), Fraction(3))

    def test_unreadable_file_raises_file_error(self) -> None:
        """底层读取抛出 OSError 时翻译成 MissingFileError（白盒）。"""
        path = self.write("Ex.txt", "1. 1 + 2 =\n")
        with mock.patch.object(Path, "read_text", side_effect=OSError("设备不可用")):
            with self.assertRaises(MissingFileError) as context:
                read_exercises(path)
        self.assertIn("读取文件失败", context.exception.message)

    def test_unparsable_exercise_line_is_warned(self) -> None:
        """题面写坏了的行会被记录并计为错题，而不是让程序崩溃。"""
        path = self.write("Ex.txt", "1. 1 + 2 =\n2. 1 + \n")
        expressions, warnings = read_exercises(path)
        self.assertEqual(sorted(expressions), [1])
        self.assertTrue(any("无法解析" in warning for warning in warnings))

    def test_answer_line_without_index_is_warned(self) -> None:
        """答案文件里缺少序号的行会被跳过并记录警告。"""
        path = self.write("An.txt", "1. 3\n乱七八糟的一行\n")
        answers, warnings = read_answers(path)
        self.assertEqual(sorted(answers), [1])
        self.assertTrue(any("缺少序号" in warning for warning in warnings))

    def test_blank_lines_are_ignored(self) -> None:
        """题目与答案文件中的空行都要被直接跳过，不产生警告。"""
        exercises = self.write("Ex.txt", "1. 1 + 2 =\n\n2. 2 × 3 =\n")
        answers = self.write("An.txt", "1. 3\n\n2. 6\n")
        expressions, exercise_warnings = read_exercises(exercises)
        parsed_answers, answer_warnings = read_answers(answers)
        self.assertEqual(sorted(expressions), [1, 2])
        self.assertEqual(sorted(parsed_answers), [1, 2])
        self.assertEqual(exercise_warnings, [])
        self.assertEqual(answer_warnings, [])

    def test_missing_file_raises(self) -> None:
        """文件不存在时抛 MissingFileError。"""
        with self.assertRaises(MissingFileError):
            read_exercises(str(self.temp_path / "nope.txt"))

    def test_directory_raises(self) -> None:
        """传入目录时抛 MissingFileError，而不是把目录当文件读。"""
        with self.assertRaises(MissingFileError):
            read_exercises(str(self.temp_path))


class GradeTests(GraderTestCase):
    def test_counts_correct_and_wrong(self) -> None:
        """第 2、4 题故意答错，统计与编号必须准确。"""
        exercises = self.write("Ex.txt", EXERCISES)
        answers = self.write(
            "An.txt",
            "1. 3\n2. 9\n3. 7/24\n4. 2\n5. 6\n",
        )
        result = grade(exercises, answers)
        self.assertEqual(result.correct, (1, 3, 5))
        self.assertEqual(result.wrong, (2, 4))
        self.assertEqual(result.total, 5)

    def test_format_matches_required_output(self) -> None:
        """Grade.txt 的内容必须与题目给的样例格式一致（含空行）。"""
        exercises = self.write("Ex.txt", "".join(f"{i}. 1 + 1 =\n" for i in range(1, 11)))
        answers = self.write(
            "An.txt",
            "".join(f"{i}. {2 if i % 2 else 3}\n" for i in range(1, 11)),
        )
        result = grade(exercises, answers)
        self.assertEqual(
            result.format(),
            "Correct: 5 (1, 3, 5, 7, 9)\n\nWrong: 5 (2, 4, 6, 8, 10)\n",
        )

    def test_empty_lists_are_printed_as_empty_parentheses(self) -> None:
        """全对或全错时，括号内为空，格式仍然稳定。"""
        self.assertEqual(GradeResult((1,), ()).format(), "Correct: 1 (1)\n\nWrong: 0 ()\n")

    def test_unparsable_answer_is_counted_wrong(self) -> None:
        """答案写成非法内容时记为错题并给出警告，而不是崩溃。"""
        exercises = self.write("Ex.txt", "1. 1 + 2 =\n2. 2 + 2 =\n")
        answers = self.write("An.txt", "1. 3\n2. 四\n")
        result = grade(exercises, answers)
        self.assertEqual(result.correct, (1,))
        self.assertEqual(result.wrong, (2,))
        self.assertTrue(any("无法解析" in warning for warning in result.warnings))

    def test_line_without_index_is_reported(self) -> None:
        """缺少序号的行会被跳过并记录警告。"""
        exercises = self.write("Ex.txt", "1. 1 + 2 =\n讨厌的坏行\n")
        answers = self.write("An.txt", "1. 3\n")
        result = grade(exercises, answers)
        self.assertEqual(result.correct, (1,))
        self.assertTrue(any("缺少序号" in warning for warning in result.warnings))

    def test_missing_answer_is_counted_wrong(self) -> None:
        """题目在答案文件里没有对应行时按错题处理。"""
        exercises = self.write("Ex.txt", "1. 1 + 2 =\n2. 2 + 2 =\n")
        answers = self.write("An.txt", "1. 3\n")
        result = grade(exercises, answers)
        self.assertEqual(result.correct, (1,))
        self.assertEqual(result.wrong, (2,))
        self.assertTrue(any("没有对应答案" in warning for warning in result.warnings))

    def test_extra_answer_is_counted_wrong(self) -> None:
        """答案文件里多出来的题目编号按错题处理并给出提示。"""
        exercises = self.write("Ex.txt", "1. 1 + 2 =\n")
        answers = self.write("An.txt", "1. 3\n2. 4\n")
        result = grade(exercises, answers)
        self.assertEqual(result.correct, (1,))
        self.assertEqual(result.wrong, (2,))
        self.assertTrue(any("不存在" in warning for warning in result.warnings))

    def test_round_trip_with_generated_files(self) -> None:
        """端到端自检：程序自己生成的题目与答案，批改结果必须全对。"""
        from quiz.generator import QuestionGenerator, format_answers, format_exercises

        questions = QuestionGenerator(10, rng=random.Random(9)).generate(120)
        exercises = self.write("Ex.txt", format_exercises(questions))
        answers = self.write("An.txt", format_answers(questions))
        result = grade(exercises, answers)
        self.assertEqual(len(result.correct), 120)
        self.assertEqual(result.wrong, ())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
