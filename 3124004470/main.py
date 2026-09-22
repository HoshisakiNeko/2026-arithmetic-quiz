#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小学四则运算题目生成程序（结对项目）入口。

用法::

    python main.py -n 10 -r 10                        # 生成题目
    python main.py -n 10000 -r 10                     # 生成一万道题目
    python main.py -e Exercises.txt -a Answers.txt    # 批改并输出 Grade.txt

生成结果写入当前目录的 Exercises.txt 与 Answers.txt，批改结果写入 Grade.txt。
"""

from __future__ import annotations

import sys

from quiz.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

