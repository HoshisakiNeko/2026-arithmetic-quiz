"""小学四则运算题目生成与批改程序（结对项目）。

包内模块划分：

* :mod:`quiz.notation`   —— 取值池与分数写法（``3/5``、``2'3/8``）的格式化与解析；
* :mod:`quiz.expression` —— 表达式树的求值、打印、去重指纹与解析；
* :mod:`quiz.generator`  —— 核心模块：在运算约束下生成互不重复的题目；
* :mod:`quiz.grader`     —— 需求 9：批改题目文件与答案文件；
* :mod:`quiz.cli`        —— 命令行参数解析与流程编排；
* :mod:`quiz.errors`     —— 异常体系。
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"

