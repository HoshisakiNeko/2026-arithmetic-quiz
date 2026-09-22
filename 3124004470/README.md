# 结对项目：小学四则运算题目生成程序

用 Python 3 实现的小学四则运算题目生成与批改程序：

* 生成 **互不重复** 的四则运算题目，写入 `Exercises.txt`；
* 同时算出全部答案，写入 `Answers.txt`；
* 支持对给定的题目文件与答案文件 **批改**，把统计结果写入 `Grade.txt`。

只使用 Python 标准库（`requirements.txt` 是空操作），所有数值运算都用
`fractions.Fraction` 精确完成，不会出现浮点数误差。

## 一、运行方式

### 1. 生成题目

```bash
python main.py -n 10 -r 10      # 生成 10 道 10 以内的题目
python main.py -n 10000 -r 10   # 需求 8：一次性生成一万道题目
python main.py -r 10            # 不写 -n 时默认生成 10 道
```

* `-n`：题目个数（默认 10）；
* `-r`：题目中数值（自然数、真分数及其分母）的范围，**必须给定**，
  否则程序报错并给出帮助信息；
* 结果文件写在**当前目录**（也可以用 `--output-dir` 指定目录）。

### 2. 批改答案（需求 9）

```bash
python main.py -e Exercises.txt -a Answers.txt
```

批改结果写入 `Grade.txt`：

```
Correct: 7 (2, 3, 4, 5, 6, 8, 9)

Wrong: 3 (1, 7, 10)
```

### 3. 其他可选参数

| 参数 | 说明 |
| --- | --- |
| `--seed N` | 固定随机种子，便于复现同一个题目文件 |
| `--output-dir DIR` | 结果文件的输出目录，默认当前目录 |
| `-v, --verbose` | 打印耗时、容错提示等细节 |
| `-q, --quiet` | 不打印摘要 |
| `-h, --help` | 显示用法 |

返回码：`0` 成功；`2` 参数错误；`3` 文件错误；`4` 生成/解析错误；`1` 其他未预期错误。

## 二、目录结构

```
main.py                入口文件（评测调用的就是它）
quiz/
    notation.py        取值池与分数写法（3/5、2'3/8）的格式化与解析
    expression.py      表达式树的求值、打印、去重指纹与解析
    generator.py       核心模块：在运算约束下生成互不重复的题目
    grader.py          需求 9：批改题目文件与答案文件
    cli.py             命令行参数解析与流程编排
    errors.py          异常体系
tests/                 113 个单元测试用例（语句覆盖率 100%）
tools/                 开发期工具：覆盖率、性能分析、基准对比、一万道题自检
sample_data/           样例：Exercises.txt / Answers.txt / Grade.txt 等
docs/                  博客草稿与各工具生成的报告
requirements.txt       说明"无需第三方依赖"
```

## 三、算法与设计要点

### 1. 数值范围与取值池

`-r r` 时，所有叶子节点的取值来自：

* 自然数 `1 ~ r-1`；
* 真分数 `p/q`，其中 `1 <= p < q <= r-1`（分子与分母都小于 r），只保留最简形式。

例如 `-r 10` 的取值池共 36 个值：9 个自然数 + 27 个最简真分数。

### 2. 在"拼树的过程中"就满足约束

* 减法 `e1 - e2`：先算出左子树的值，再把右子树的取值限制为 `<= e1`，因此不会出现负数；
* 除法 `e1 ÷ e2`：要求 `0 < e1 < e2`，商必然落在 `(0, 1)`，即真分数；
* 运算符个数随机取 1~3 个，满足"不超过 3 个"的要求。

### 3. 题目去重：只认交换律，不认结合律

去重指纹对满足交换律的 `+`、`×` 节点把两个子树的指纹排成固定顺序，
但不做结合律的重新结合。这样正好符合题目要求：

* `23 + 45` 与 `45 + 23` 是同一道题；
* `3 + (2 + 1)` 与 `1 + 2 + 3` 是同一道题；
* `1 + 2 + 3` 与 `3 + 2 + 1` **不是**同一道题。

### 4. 打印规则保证题面唯一

子表达式优先级更低、或者优先级相同且位于右侧时补括号（四则运算按左结合理解），
因此结构不同的表达式一定打印出不同的字符串，题目文件里不会出现"看起来重复"的题目。

### 5. 分数写法

真分数写成 `3/5`，假分数写成带分数 `2'3/8`；解析时同时兼容 `’`（Word 自动替换
出的右单引号）、全角数字、多余空格等写法，避免因为字符差异导致批改失败。

## 四、需求对照表

| 需求 | 落实位置 |
| --- | --- |
| 1. `-n` 控制题目个数 | `quiz/cli.py`（默认 10） |
| 2. `-r` 控制数值范围，必须给定 | `quiz/notation.py:build_value_pool`、`quiz/cli.py`（缺 `-r` 报错并给出用法） |
| 3. 减法不出现负数 | `quiz/generator.py:_build_once`（右子树受 `<= 左值` 约束） |
| 4. 除法的商是真分数 | 同上（要求 `0 < 左值 < 右值`） |
| 5. 运算符不超过 3 个 | `quiz/generator.py:MAX_OPERATORS` |
| 6. 题目不能重复 | `quiz/expression.py:canonical_key` + 指纹集合判重 |
| 7. 题目与答案分别写入 `Exercises.txt` / `Answers.txt` | `quiz/generator.py:format_exercises/format_answers`、`quiz/cli.py` |
| 8. 支持一万道题 | 实测约 0.5 秒（`tools/verify_all.py` 逐条校验） |
| 9. `-e/-a` 批改并输出 `Grade.txt` | `quiz/grader.py`、`quiz/cli.py` |

## 五、开发期工具（可复现所有报告）

```bash
# 1. 单元测试：113 个用例
python -m unittest discover -s tests -t . -v

# 2. 语句覆盖率（标准库 trace，输出 docs/coverage_report.txt 与 docs/coverage/）
python tools/coverage_report.py

# 3. 生成一万道题并逐条校验全部硬性要求（输出 docs/validation_report.txt）
python tools/verify_all.py

# 4. 性能分析（cProfile，输出 docs/profile_stats.txt、profile_chart.svg、profile_data.json）
python tools/profile_report.py 10000 10

# 5. 三代实现对比与参数调优记录（输出 docs/benchmark.txt）
python tools/benchmark.py
```

## 六、PSP 表格

| PSP2.1 | 预估耗时（分钟） | 实际耗时（分钟） |
| --- | --- | --- |
| Planning 计划 | 30 | 30 |
| · Estimate 估计这个任务需要多少时间 | 30 | 30 |
| Development 开发 | 780 | 835 |
| · Analysis 需求分析（包括学习新技术） | 70 | 60 |
| · Design Spec 生成设计文档 | 50 | 55 |
| · Design Review 设计复审（和同事审核设计文档） | 40 | 45 |
| · Coding Standard 代码规范 | 20 | 15 |
| · Design 具体设计 | 80 | 95 |
| · Coding 具体编码 | 220 | 235 |
| · Code Review 代码复审 | 60 | 70 |
| · Test 测试（自我测试，修改代码，提交修改） | 240 | 260 |
| Reporting 报告 | 120 | 130 |
| · Test Report 测试报告 | 50 | 55 |
| · Size Measurement 计算工作量 | 20 | 20 |
| · Postmortem & Process Improvement Plan 事后总结与改进计划 | 50 | 55 |
| **合计** | **930** | **995** |

## 七、样例数据

`sample_data/` 下的文件由程序自己生成，可以直接用来验证：

| 文件 | 说明 |
| --- | --- |
| `Exercises.txt` / `Answers.txt` | `-n 10 -r 10 --seed 20240915` 生成的题目与答案 |
| `Grade.txt` | 用上面的答案批改自己的题目，结果全对 |
| `Answers_demo.txt` / `Grade_demo.txt` | 故意把第 1、7、10 题答错后的批改结果 |

```bash
python main.py -e sample_data/Exercises.txt -a sample_data/Answers_demo.txt --output-dir sample_data
cat sample_data/Grade.txt     # Correct: 7 (2, 3, 4, 5, 6, 8, 9) / Wrong: 3 (1, 7, 10)
```

详细的效能分析、设计说明、测试与结对感受见
[docs/结对项目-博客.md](docs/结对项目-博客.md)。
