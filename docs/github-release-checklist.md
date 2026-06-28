# GitHub 发布前检查清单

目标：让其他部门同事下载项目后，可以按文档录入本部门数据、执行上传前校验、正式排课、检查质量并只读发布结果。

## 当前已验证

- `python3 -m unittest discover -v` 通过，当前 148 个测试。
- `python3 scheduler.py --input examples/input_example.json --output /tmp/ai_schedule_example.csv --html-output /tmp/ai_schedule_example.html` 可生成样例 CSV 和 HTML。
- `python3 run_scheduling_pipeline.py --source examples/csv_minimal --data-dir /tmp/ai_schedule_demo_data --output-dir /tmp/ai_schedule_demo_outputs` 可用公开最小 CSV 示例生成完整排课结果。
- `bash scripts/verify_release.sh` 可一键执行脚本语法检查、Python 编译、单元测试、核心 JSON 样例和公开 CSV 最小闭环。
- `python3 run_scheduling_pipeline.py --source data --preflight` 可执行上传前校验；当前真实数据被业务门禁拦截，生成 372 条缺老师补录记录。
- 本地后台 `http://127.0.0.1:8765/` 可访问。
- `.gitignore` 已排除 `data/`、`outputs/`、缓存和本地环境文件。
- 低频 ERP 辅助脚本不再携带个人下载目录默认值；ERP 导出、导入模板、专业课固定课表等本地文件均通过显式命令行参数传入，`tests/test_release_static.py` 会阻止个人路径重新进入 `scripts/`。

## 入仓库文件

- 核心代码：`scheduler.py`、`run_scheduling_pipeline.py`、`data_admin_server.py`、`business_class_import.py`、`generate_time_slots.py`、`formal_template.py`。
- 通用脚本：`scripts/` 中排课、校验、审计、发布相关脚本。
- 后台页面：`web_admin/`。
- 只读发布：`schedule_publish_server.py`、`cloudflare_schedule_publish/`、`PUBLIC_SCHEDULE_DEPLOY.md`。
- 示例和测试：`examples/`、`tests/`。
- 说明文档：`README.md`、`docs/department-reuse-user-guide.md`、`docs/ai-scheduling-sop.md`、`docs/github-release-checklist.md`。

## 不入仓库文件

- `data/`：当前部门真实业务数据。
- `outputs/`：历史运行输出、备份、排课结果、报告。
- `.env`、`.env.*`、账号密码、Token、API Key、Cookie。
- `__pycache__/`、`.DS_Store`、本机 IDE 配置。

## 发布前还需处理

- 当前真实数据预检未通过，原因是缺老师安排。该问题是业务数据缺口，不是程序阻塞；正式发布前如果要演示完整真实排课，需要先补齐 `missing_class_teacher_assignments_*.csv`。
- 若 GitHub 仓库面向多部门但不公开，应确认仓库权限和数据脱敏边界。

## 发布操作建议

```bash
git status --short --ignored
bash scripts/verify_release.sh
python3 -m unittest discover -v
python3 scheduler.py --input examples/input_example.json --output /tmp/ai_schedule_example.csv --html-output /tmp/ai_schedule_example.html
python3 run_scheduling_pipeline.py --source examples/csv_minimal --data-dir /tmp/ai_schedule_demo_data --output-dir /tmp/ai_schedule_demo_outputs --preflight
python3 run_scheduling_pipeline.py --source examples/csv_minimal --data-dir /tmp/ai_schedule_demo_data --output-dir /tmp/ai_schedule_demo_outputs
python3 run_scheduling_pipeline.py --source data --preflight --output-dir /tmp/ai_schedule_release_preflight
```

确认无误后再执行：

```bash
git add .gitignore README.md requirements.txt Procfile *.py scripts web_admin examples docs share tests cloudflare_schedule_publish PUBLIC_SCHEDULE_DEPLOY.md LAUNCH_CHECKLIST.md SCHEDULING_RULES_REVIEW_20260524.md
git commit -m "Prepare AI scheduling project for department reuse"
git remote add origin <GitHub仓库地址>
git push -u origin main
```
