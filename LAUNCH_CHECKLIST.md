# 本机排课试运行检查清单

## 1. 安装依赖

```bash
python3 -m pip install -r requirements.txt
```

## 2. 启动后台

```bash
./scripts/start_admin.sh
```

打开 `http://127.0.0.1:8765`，进入“排课运行维护”。

## 3. 生成预填模板

- 在“排课运行维护”的“填写/导入模板”区域上传业务班级导出、历史已排课明细和可选标准数据。
- 页面会生成：
  - `formal_launch_template_<timestamp>.xlsx`
  - `formal_launch_csv_templates_<timestamp>.zip`
  - `template_report_<timestamp>.md`
- 模板会预填产品清单、2026-12 考研班级筛选结果、历史学习到的老师安排、已排课时抵扣、疑似合班候选和缺口清单。

## 4. 补齐人工确认表

- 上传一个多 Sheet Excel，或一次选择多份 CSV/Excel 文件。
- 若上传业务系统班级导出，例如 `20260429班级查询导出.csv`，需同时提供或补齐：
  - `business_product_mappings.csv` / `18_ERP产品对应表`
  - `class_teacher_assignments.csv` / `12_班级老师安排表`
  - 合班共享课表关系：优先在班级老师安排表里维护 `class_schedule_mode` 和 `actual_scheduled_class_id`
  - 可选上传 `scheduled_lessons.csv` / `已排课明细.csv`，用于抵扣 2026-06-30 前已排课时并学习老师安排。
- 首批考研试运行只纳入 `管理项目=考研/考博`、`考试月份=2026-12`、且与 `2026-07-01` 至 `2026-12-31` 有交集的班级。
- `常规体系` 默认排课，`专项体系` 完成 ERP 产品对应并有班级排课窗口后纳入，`计费体系` 自动排除。

## 5. 上传前校验

- 在“排课运行维护”的“校验数据”区域上传补齐后的 Excel 模板或 CSV 包解压后的多份 CSV。
- 校验只做识别、转换和缺口检查，不备份、不写 `data/`、不排课。
- 校验未通过时先下载校验报告，补齐后重新上传。

## 6. 正式运行

- 校验通过后，在“排课运行维护”的“生成课表”区域上传同一批补齐文件并运行。
- 每次正式运行都会进入独立批次目录 `outputs/uploads/<timestamp>/`。
- 运行前会自动备份当前 `data/` 到 `outputs/backups/`。

## 7. 验收结果

成功后页面会显示：

- 导入报告 `outputs/import_report_<timestamp>.md`
- 排课明细 `outputs/schedule_<timestamp>.csv`
- 甘特图 `outputs/schedule_<timestamp>.html`
- 生成参考文件，例如 `learned_class_teacher_assignments_<timestamp>.csv`、`missing_class_teacher_assignments_<timestamp>.csv`
- 页面内嵌甘特图预览

## 8. 失败排查

- 先打开导入报告，查看阻塞错误。
- 常见问题包括班级排课窗口过窄、窗口级教室不可用、老师安排缺失、班级缺少开课日期、课程课时不能被产品规则的单次连续课时整除。
- 业务班级导出常见阻塞包括：未命中 ERP 产品对应、专项缺少班级排课窗口、共享课表关系未确认、阶段+课程组级老师安排缺失。
- 上传历史课表后，查看报告中的“生成参考文件”和“已排课时抵扣”提示，重点核对老师冲突、剩余课时为 0 的课程、疑似合班候选。
- 修正源表后重新上传，系统会保留每次上传和备份记录。

## 9. 命令行兜底

```bash
./scripts/run_pipeline.sh incoming
```

## 10. 公网只读发布

生成查看密码哈希：

```bash
python3 schedule_publish_server.py --hash-password
```

本地预览只读发布站：

```bash
export SCHEDULE_VIEWER_USERNAME="schedule-viewer"
export SCHEDULE_VIEWER_PASSWORD_HASH="上一步生成的哈希"
export SCHEDULE_VIEWER_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
PORT=8780 ./scripts/start_schedule_publish.sh
```

打开 `http://127.0.0.1:8780/schedule` 验证。线上部署时将同样的环境变量配置到平台，并设置 `SCHEDULE_VIEWER_COOKIE_SECURE=1`。详细说明见 `PUBLIC_SCHEDULE_DEPLOY.md`。
