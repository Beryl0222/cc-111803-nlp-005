# 报关品名变体与申报属性核对

本地文本工作区用于保存品名与规格实体抽取相关的合成记录，并提供基础规范化和词项查看能力。

## 环境

需要 Python 3.11 或更新版本。运行程序仅使用 Python 标准库。测试依赖固定为 pytest 8.3.4，可执行 `python -m pip install -r requirements-dev.txt` 安装。

## 运行

运行 `PYTHONPATH=src python -m nlp_customs_description_normalizer.desk_cli` 核查样品的品名和包装单位，并查看没有余额的申报草稿。样品登记在 fixtures/work.json，采购与既有申报在 fixtures/business.json。数量按最小销售单位结算，已提交数量占用采购额。

运行 `PYTHONPATH=src python -m nlp_customs_description_normalizer.review_cli` 复核 fixtures/review-case.json 中的申报草稿。复核台解析外箱清单与发票的自由描述，分清商品、材质、规格和包装数量的关系，并判断配件是另计还是包含在前一组里。简称用于查目录；单据没有写明的材质和规格保持待核。每项结论给出数量换算、所用单据和原文片段，以及与已提交申报的关系；同一批到货的多份单据按批次归组，与另一批到货区分。`--round 1` 只使用第一次复核时在手的单据，可对比装箱资料补齐前后的结论；后到的单据取代被其取代的旧单据，能够独立核实的数量不受待核项影响，争用同一采购余额的拆分单独列出。

fixtures/review-corrections.json 演示补报、冲减、重报：更正必须指明已提交申报标识，冲减释放已占用数量，重报以新数量替换原提交数量，补报在已提交申报上追加数量；更正数量不会再次从采购余额中扣减。已提交的品名和数量可在结论的 submitted 一节回查。

从项目根目录执行 `PYTHONPATH=src python -m nlp_customs_description_normalizer.cli ingest fixtures/records.json` 导入样例，随后执行 `PYTHONPATH=src python -m nlp_customs_description_normalizer.cli list` 查看记录。工作数据写入 `var/records.json`。业务查询使用 fixtures/business.json 中的初始资料，约定见 fixtures/business-contract.md。执行 PYTHONPATH=src python -m nlp_customs_description_normalizer.cli business 可查看当前业务目录结果。

样例为本地合成文本。记录包含来源、修订号和原文，当前工作区对空白做统一处理，并提供字符及英文词项切分。

## 测试

执行 `python -m pytest -q` 检查规范化、记录持久化和来源筛选。
