# 最小 CSV 闭环示例

这个目录用于验证下载后的项目是否可以完整跑通上传前校验和正式排课。它只包含一个教学区、一间教室、一位老师、一个产品和一个班级，不代表真实业务规模。

运行上传前校验：

```bash
python3 run_scheduling_pipeline.py --source examples/csv_minimal --data-dir /tmp/ai_schedule_demo_data --output-dir /tmp/ai_schedule_demo_outputs --preflight
```

正式生成课表：

```bash
python3 run_scheduling_pipeline.py --source examples/csv_minimal --data-dir /tmp/ai_schedule_demo_data --output-dir /tmp/ai_schedule_demo_outputs
```

成功后查看：

- `/tmp/ai_schedule_demo_outputs/schedule_<timestamp>.csv`
- `/tmp/ai_schedule_demo_outputs/schedule_<timestamp>.html`
- `/tmp/ai_schedule_demo_outputs/import_report_<timestamp>.md`
