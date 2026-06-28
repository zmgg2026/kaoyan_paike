# AI 排课项目部门复用使用攻略

这份攻略面向第一次接触本项目的其他部门同事。目标不是让大家理解全部代码，而是按顺序完成：下载项目、准备数据、上传前校验、正式排课、检查质量、发布只读结果。

## 1. 本地安装

先安装 Python 3.11 或更高版本，然后在项目目录执行：

```bash
python3 -m pip install -r requirements.txt
bash scripts/verify_release.sh
```

启动后台工作台：

```bash
./scripts/start_admin.sh
```

打开浏览器访问：

```text
http://127.0.0.1:8765
```

![后台总览](assets/user-guide/admin-overview.png)

如果 8765 端口被占用，可以换端口：

```bash
PORT=8766 ./scripts/start_admin.sh
```

也可以先用公开最小 CSV 示例验证命令行闭环：

```bash
python3 run_scheduling_pipeline.py --source examples/csv_minimal --data-dir /tmp/ai_schedule_demo_data --output-dir /tmp/ai_schedule_demo_outputs --preflight
python3 run_scheduling_pipeline.py --source examples/csv_minimal --data-dir /tmp/ai_schedule_demo_data --output-dir /tmp/ai_schedule_demo_outputs
```

`verify_release.sh` 会自动跑单元测试、核心 JSON 样例和公开最小 CSV 示例；单独运行上面两条命令，适合排查 CSV 示例的预检和正式排课。这个示例只排一个班级的一次 4 小时课程，用于证明环境、模板读取、预检、正式排课、CSV/HTML 输出都正常。

## 2. 工作台模块怎么看

后台左侧按排课工作流分组：

- 全局时间：维护年度排课窗口、课节明细、全局停课日期。
- 基础资源：维护教学区、教室、教师、教师不可排时间。
- 产品规则：维护产品、课程课时、产品窗口规则、ERP 产品对应关系。
- 班级需求：维护班级基础信息、班级排课窗口、班级老师安排、班级互斥关系。
- 控制交付：维护锁定课表，执行上传前校验、正式排课、结果查看和只读发布。

日常使用不需要从代码入口开始，优先用“排课运行维护”页按步骤推进。

![排课运行维护](assets/user-guide/admin-launch.png)

## 3. 准备基础数据

建议先在“排课运行维护”页下载或生成基础数据模板，再按本部门数据补齐。核心表按优先级填写：

| 优先级 | 表 | 必填原因 |
| --- | --- | --- |
| 1 | 年度排课窗口、课节表 | 决定有哪些日期和时段可以排课 |
| 2 | 教学区、教室、教师 | 决定资源是否可用、容量是否够 |
| 3 | 产品管理、产品课程课时、产品窗口规则 | 决定每个产品上什么课、在哪些季节窗口和时段上 |
| 4 | 班级基础信息、班级排课窗口 | 决定每个班级实际能在哪些年度窗口、日期、时段、教学区、教室排课 |
| 5 | 班级老师安排 | 决定每个班级每个科目/阶段/课程组由谁上课 |
| 6 | 班级互斥关系、锁定课表、教师不可排时间 | 决定哪些课不能撞车、哪些已有课不能移动 |
| 7 | ERP 产品对应、历史已排课明细 | 用于导入 ERP、扣减已上课时、学习历史老师安排 |

最容易出错的三类数据：

- 班级老师安排缺失：预检会生成 `missing_class_teacher_assignments_*.csv`，按文件补齐后重新上传。
- 班级排课窗口不准：同一个班级跨暑假、秋季、寒假等多个年度窗口时，必须逐窗口维护日期、时段、教学区和教室。
- 产品窗口规则混淆：产品规则只写寒假/春季/暑假/秋季这类季节窗口；具体年份窗口由班级排课窗口决定。

## 4. 上传前校验

在后台使用：

1. 打开“排课运行维护”。
2. 上传原始导出或补齐后的模板。
3. 点击上传前校验。
4. 查看预检报告和参考文件。

也可以用命令行：

```bash
python3 run_scheduling_pipeline.py --source incoming --preflight
```

校验通过才进入正式排课。校验未通过时不要强行排课，先处理报告里的阻塞项。

常见预检结果：

| 结果 | 处理方式 |
| --- | --- |
| 缺老师安排 | 下载 `missing_class_teacher_assignments_*.csv`，补齐老师后重新上传 |
| 缺产品映射 | 在 ERP 产品对应页补齐本地产品和 ERP 标准课程产品关系 |
| 无可用课节 | 检查课节表 `is_usable`、全局停课日期、产品窗口规则和班级排课窗口 |
| 教室不可用或容量为 0 | 回到教学区与教室页核对启用状态、容量和班级窗口里的教室选择 |

## 5. 正式排课

预检通过后，再执行完整排课：

```bash
python3 run_scheduling_pipeline.py --source incoming
```

后台运行时会自动生成：

- `data/scheduler_input_draft.json`：排课器实际输入。
- `outputs/schedule_<timestamp>.csv`：排课明细。
- `outputs/schedule_<timestamp>.html`：可视化课表。
- `outputs/import_report_<timestamp>.md`：导入和排课报告。
- `outputs/backups/`：正式运行前的数据备份。

命令行样例验证：

```bash
python3 scheduler.py \
  --input examples/input_example.json \
  --output /tmp/schedule.csv \
  --html-output /tmp/schedule.html
```

如果这条样例命令能生成 CSV 和 HTML，说明本机 Python 环境和核心排课器基本可用。

## 6. 排课结果质量检查

排课成功不等于可以发布。至少检查 5 个信号：

| 检查项 | 合格标准 |
| --- | --- |
| 不撞车 | 同一老师、班级、教室、互斥组没有同课节冲突 |
| 不漏课 | 每个进入排课范围的班级需求课时都被覆盖 |
| 日期合理 | 每个班只排在自己的班级排课窗口内 |
| 规则合理 | 产品可排星期、时段、每日上限、同半天连续块规则被执行 |
| 能交付 | CSV 可核对，HTML 可阅读，报告说明清楚 |

当前项目已有自动化测试覆盖这些方向，但业务发布前仍建议抽查重点班级、重点老师和跨教学区课程。

可执行的审计命令：

```bash
python3 scripts/audit_schedule_coverage.py \
  --data-dir data \
  --schedule-csv outputs/schedule_<timestamp>.csv \
  --out-dir outputs \
  --timestamp <timestamp>

python3 scripts/audit_schedule_quality.py \
  --data-dir data \
  --schedule-csv outputs/schedule_<timestamp>.csv \
  --out-dir outputs \
  --timestamp <timestamp>
```

覆盖审计用于看课时是否排足；质量审计用于看周课量、同日负载、老师跨教学区移动等体验问题。硬冲突和覆盖缺口必须处理，质量问题按优先级处理或说明原因。

## 7. 只读发布

只读发布用于给同事查看结果，不开放后台保存、导入和排课接口。

本地生成登录密码哈希：

```bash
python3 schedule_publish_server.py --hash-password
```

本地预览：

```bash
export SCHEDULE_VIEWER_USERNAME="schedule-viewer"
export SCHEDULE_VIEWER_PASSWORD_HASH="上一步生成的哈希"
export SCHEDULE_VIEWER_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
PORT=8780 ./scripts/start_schedule_publish.sh
```

访问：

```text
http://127.0.0.1:8780/schedule
```

## 8. GitHub 下载复用建议

给其他部门复用时，仓库里建议包含：

- 程序代码：`scheduler.py`、`run_scheduling_pipeline.py`、`data_admin_server.py`、`business_class_import.py`。
- 后台页面：`web_admin/`。
- 脚本：`scripts/` 中通用排课、校验、发布脚本。
- 示例：`examples/`。
- 文档：`README.md`、本攻略、SOP、发布说明。
- 测试：`tests/`。

仓库里不建议包含：

- 本部门真实 `data/` 数据。
- `outputs/` 历史输出。
- `.env`、密码、Cookie、Token、API Key。
- 个人电脑路径下的 ERP 导出文件。

其他部门 clone 后的推荐顺序：

```bash
git clone <仓库地址>
cd <项目目录>
python3 -m pip install -r requirements.txt
python3 -m unittest discover -v
./scripts/start_admin.sh
```

## 9. 问题排查

| 现象 | 优先检查 |
| --- | --- |
| 端口打不开 | 终端是否还在运行、端口是否被占用、是否改用 `PORT=8766` |
| 上传后没有排课结果 | 是否只做了预检，或预检报告是否有阻塞项 |
| 课表缺很多课 | 产品课程课时、班级适用阶段、历史课表扣减、班级窗口是否正确 |
| 老师冲突多 | 教师不可排时间、合班共享课表、锁定课表是否维护准确 |
| 教室不对 | 班级排课窗口里的教学区/教室是否覆盖了班级默认教室 |

每次修改基础数据后，建议先跑 `--preflight`，再正式排课。
