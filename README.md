# 班级自动化排课程序

这是一个可直接在本地运行的 Python 排课工具。它会根据考研班级课程需求、固定课节、班级对应老师、教学区和套班冲突组，自动生成课表 CSV，也可以同步输出班级课表甘特图 HTML。

## 功能特性

- 支持自定义固定课节，例如 `上午一`、`上午二`、`下午一`、`下午二`、`晚上`。
- 每个课节默认 2 小时，也可在 `time_slots.duration_hours` 单独指定。
- 课程需求按小时填写，使用 `total_hours` 和 `block_hours` 自动拆成连续课程块。
- 支持产品排课规则：可按产品、科目、阶段限制日期范围、可排时段、可排星期和单次连续时长。
- 支持公共课和专业课分类：公共课包括英语、政治、数学；专业课包括管综、计算机、西医。
- 支持产品化课程配置：先定义产品内固定课程和课时，班级引用产品后补老师安排。
- 支持独立产品管理：项目、产品线、子产品、产品体系、标准人数、班容类型、科目、科目类型和课程性质由产品统一维护，班级自动继承；考季和套班编码由班级维护。
- 支持教师基础信息表：维护教师员工ID、姓名、归属项目、教师角色、用工类型、主教学科目、合同状态和在职状态。
- 自动校验硬约束：
  - 同一班级同一课节不能有两节课
  - 同一老师同一课节不能上两个班
  - 同一教室同一课节不能被重复占用
  - 课程只能排在班级窗口、老师不可排例外和产品窗口规则允许的课节内
  - 同一冲突组内的班级不能在同一课节上课
- 输出为 CSV，方便导入表格软件。
- 可选输出 HTML 甘特图，按班级展示课程块占用的连续课节。

## 快速开始

给其他部门下载复用时，建议先阅读 [部门复用使用攻略](docs/department-reuse-user-guide.md) 和 [GitHub 发布前检查清单](docs/github-release-checklist.md)。

下载后可以先用公开最小示例验证环境：

```bash
python3 -m pip install -r requirements.txt
bash scripts/verify_release.sh
python3 run_scheduling_pipeline.py --source examples/csv_minimal --data-dir /tmp/ai_schedule_demo_data --output-dir /tmp/ai_schedule_demo_outputs --preflight
python3 run_scheduling_pipeline.py --source examples/csv_minimal --data-dir /tmp/ai_schedule_demo_data --output-dir /tmp/ai_schedule_demo_outputs
```

`verify_release.sh` 会先检查 shell 语法、编译根目录核心 Python 和全部 `scripts/*.py`，再确认根目录核心入口与 `scripts/` 中带命令行参数的脚本都能打开 `--help`，随后继续跑发布包审计、单元测试、公开最小样例、覆盖审计和质量审计。

启动本地数据管理网页：

```bash
python3 data_admin_server.py --port 8765
```

然后打开 `http://127.0.0.1:8765`。网页会读取并保存 `data/*.json`，可以通过“产品管理”维护产品标签，通过“产品课程”维护课程课时，通过“班级基础信息”和“班级排课窗口”维护班级日期、时段和场地。“产品管理”和“班级管理”都支持下载 CSV，编辑后再导入更新。页面中的“导出排课输入”会生成 `data/scheduler_input_draft.json`，用于后续运行排课。

从混合 Excel/CSV 源数据跑完整闭环：

```bash
python3 -m pip install -r requirements.txt
python3 run_scheduling_pipeline.py --source incoming --preflight
python3 run_scheduling_pipeline.py --source incoming
```

`incoming` 可以是目录，也可以是单个 Excel/CSV 文件。目录中可混放 `.xlsx` 和 `.csv`；Excel sheet 名或 CSV 文件名可使用英文表名或中文表名，例如 `products`、`产品管理表`、`class_teacher_assignments`、`班级老师安排表`。建议先加 `--preflight` 只做上传前校验；校验通过后再去掉该参数正式运行。正式运行时会先把当前 `data/` 备份到 `outputs/backups/`，再生成 `data/scheduler_input_draft.json`、`outputs/schedule_<timestamp>.csv`、`outputs/schedule_<timestamp>.html` 和 `outputs/import_report_<timestamp>.md`。

### 可选：考研 2026-12 业务班级导出适配器

这段是首批考研试运行留下的业务导入适配器，用于直接上传特定业务系统导出的班级 CSV，例如 `20260429班级查询导出.csv`。其他部门复用时，不需要套用这里的固定年份口径；优先按“排课运行维护”页生成的模板表补齐本部门数据，再复用完整 pipeline。

固定口径如下：

- 只处理 `管理项目=考研/考博`。
- 只处理 `考试月份=2026-12`。
- 固定排课窗口为 `2026-07-01` 到 `2026-12-31`。
- `产品体系=常规体系` 和 `专项体系` 在完成 ERP 产品对应后按班级排课窗口进入本轮排课；`计费体系` 永不排课。
- 班级排课日期会按窗口裁剪：`start_date=max(实际开课日期, 2026-07-01)`，`end_date=min(实际结课日期, 2026-12-31)`。

业务班级导出不能单独完成排课，必须同时补充以下控制表：

| 文件或 sheet 名 | 字段 | 用途 |
| --- | --- | --- |
| `business_product_mappings` / `ERP产品对应表` | `local_product_id`, `erp_course_code`, `erp_version_code`, `match_status`, `notes` | 把本地排课产品关联到 ERP 标准课程产品和版本，供导入、核对和追溯使用。 |
| `class_window_boundaries` / `班级排课窗口表` | `class_id`, `schedule_window_id`, `earliest_date`, `latest_date`, `preferred_room_ids`, `is_class_window_included` | 逐班、逐年度窗口维护日期、时段、教学区和教室；寒暑营、无忧寒等跨窗口资源差异统一放这里。 |
| `class_teacher_assignments` / `班级老师安排表` | `class_id`, `subject`, `stage`, `course_group`, `class_schedule_mode`, `actual_scheduled_class_id`, `teacher_id`, `teacher_name` | 老师安排按班级、科目、阶段、课程组维护；合班共享课表通过实际排课班级表达。 |
| `teacher_unavailability` / `教师不可排日期时段表` | `employee_id`, `unavailable_type`, `start_date`, `end_date`, `weekdays`, `periods`, `schedule_window_ids`, `is_active` | 只记录兼职限制、请假、培训等不可排例外；全职老师默认可排。 |
| `scheduled_lessons` / `已排课明细` / `历史课表` | `class_id`, `date`, `start_time`, `end_time`, `duration_hours`, `teacher_id`, `teacher_name`, `room_id`, `business_product_id`, `subject`, `stage`, `course_module`, `course_group` | 2024-03-01 至 2026-06-30 已排课节明细，用于学习老师安排、抵扣 2026-07-01 前已排课时、生成规则和合班候选参考。 |
| `locked_scheduled_lessons` / `锁定课表` | `class_id`, `date`, `start_time`, `end_time`, `room_id`, `subject`, `quarter`, `stage`, `course_module`, `course_group` | 已经人工排定且不能移动的课节。导出排课输入后会占用对应教室课节和套班互斥关系；教师为空时不参与现有教师冲突。 |

若进入排课范围的班级缺产品映射或缺课程老师安排，pipeline 会阻塞并在导入报告中列出问题。业务导出自带 `合班详情` 时，在 `班级老师安排表` 维护共享课表关系即可，不需要额外维护第二张合班表。

历史课表不会直接变成 2026-07-01 之后的排课结果。系统会按 `class_id + subject + stage + course_module + course_group` 统计 2026-06-30 及以前的已排课时，从 27考研目标班级的产品课程总课时中扣除；课程剩余课时为 0 时不再排，整班无剩余课程时不进入 scheduler。若没有上传老师安排，系统会从历史课表按 `class_id + subject + stage + course_group` 学习老师；多老师冲突时按最近一次课节选择，并在报告中提示。

上传历史课表后，会额外生成参考文件：

- `outputs/learned_class_teacher_assignments_<timestamp>.csv`
- `outputs/learned_product_course_hours_<timestamp>.csv`
- `outputs/learned_schedule_rules_<timestamp>.csv`
- `outputs/shared_schedule_candidates_<timestamp>.csv`
- 若历史课表有明确合班字段，还会生成 `outputs/learned_shared_schedule_relations_<timestamp>.csv` 草稿。

本机正式试运行：

```bash
./scripts/start_admin.sh
```

打开 `http://127.0.0.1:8765`，进入“排课运行维护”。页面现在按向导运行：

1. 上传业务班级导出、历史已排课明细和可选标准数据，生成预填模板。
2. 下载 `formal_launch_template_<timestamp>.xlsx` 或 `formal_launch_csv_templates_<timestamp>.zip`，补齐人工确认字段。
3. 上传补齐后的模板，执行上传前校验；校验只检查缺口并生成报告，不备份、不写 `data/`、不排课。
4. 校验通过后正式运行完整闭环；运行前会备份当前 `data/`。
5. 页面显示导入报告、CSV 明细、HTML 甘特图、生成参考文件下载链接，并内嵌预览甘特图。

模板 Excel 按当前后台数据框架生成，核心维护点是 ERP 产品对应、班级排课窗口、班级老师安排、教师不可排例外和锁定课表。寒暑营、暑假营等暑假面授窗口的日期、时段和场地统一维护在班级排课窗口表，避免重复维护。历史课表建议直接上传业务系统导出的明细，不建议手工填。若 8765 已被占用，可临时使用 `PORT=8766 ./scripts/start_admin.sh`。

公网只读发布：

```bash
python3 schedule_publish_server.py --hash-password
export SCHEDULE_VIEWER_USERNAME="schedule-viewer"
export SCHEDULE_VIEWER_PASSWORD_HASH="上一步生成的哈希"
export SCHEDULE_VIEWER_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
PORT=8780 ./scripts/start_schedule_publish.sh
```

打开 `http://127.0.0.1:8780/schedule` 验证登录和只读查看。线上部署时使用平台提供的 `PORT`，并将 `SCHEDULE_VIEWER_COOKIE_SECURE=1`。只读发布站只暴露 `/schedule`、`/download/schedule.csv`、`/download/report.md` 和 `/healthz`，不会开放后台保存、导入或排课接口；详细步骤见 `PUBLIC_SCHEDULE_DEPLOY.md`。

## 开发验证入口

下面的命令用于开发排查核心排课器和课节生成器。其他部门正式复用时，优先按 [部门复用使用攻略](docs/department-reuse-user-guide.md) 走“下载模板 -> 后台预检 -> 正式排课 -> 审计验收”的完整流程。

```bash
python3 scheduler.py \
  --input examples/input_example.json \
  --output schedule.csv
```

若排课成功，将在 `schedule.csv` 中生成结果。

同时生成班级课表甘特图：

```bash
python3 scheduler.py \
  --input examples/input_example.json \
  --output schedule.csv \
  --html-output schedule.html
```

运行完成后，用浏览器打开 `schedule.html` 即可查看可视化课表。这个 HTML 是自包含文件，不需要启动服务器。

生成排课课节：

```bash
python3 generate_time_slots.py \
  --start 2026-07-01 \
  --end 2026-12-13 \
  --output examples/summer_2026_time_slots.json \
  --sunday-policy summer-only
```

该命令会在 7-8 月排除周日，9-12 月保留周日课节，后续由产品排课规则决定哪些产品可用周日。默认生成每天 5 个标准课节：白天 4 个课节加晚上 `19:00-21:00`。如只需要白天课节，可增加 `--slot-set day`。

## 输入格式

详见 [examples/input_example.json](examples/input_example.json)，核心结构如下：

```json
{
  "time_slots": [
    {
      "id": "2026-05-01-AM-1",
      "date": "2026-05-01",
      "period": "AM",
      "name": "上午一",
      "order": 1,
      "start_time": "08:00",
      "end_time": "10:00",
      "duration_hours": 2
    }
  ],
  "teaching_areas": [
    { "id": "A区", "capacity": 60 }
  ],
  "products": [
    {
      "id": "P_ENGLISH_BASIC",
      "name": "英语基础产品",
      "requirements": [
        {
          "subject_category": "公共课",
          "subject": "英语",
          "stage": "基础",
          "course_module": "词汇",
          "course_group": "阅读类",
          "total_hours": 4,
          "block_hours": 2
        },
        {
          "subject_category": "公共课",
          "subject": "英语",
          "stage": "强化",
          "course_module": "阅读",
          "course_group": "阅读类",
          "total_hours": 8,
          "block_hours": 4
        }
      ]
    }
  ],
  "classes": [
    {
      "id": "Class_English_A",
      "product_id": "P_ENGLISH_BASIC",
      "name": "考研英语寒暑集训营（27届50班）",
      "subject": "英语",
      "exam_season": "27考研",
      "exam_month": "2026-12",
      "suite_code": "27KY-HSY-EN-50",
      "size": 30,
      "start_date": "2026-07-06",
      "start_period": "PM",
      "first_lesson_date": "2026-07-06",
      "first_lesson_period": "PM",
      "end_date": "2026-08-20",
      "end_period": "AM",
      "preferred_room_ids": ["R1"],
      "teacher_assignments": [
        {
          "subject": "英语",
          "stage": "基础",
          "course_module": "词汇",
          "course_group": "阅读类",
          "teacher_id": "T_LI",
          "teacher_name": "李老师"
        },
        {
          "subject": "英语",
          "stage": "强化",
          "course_module": "阅读",
          "course_group": "阅读类",
          "teacher_id": "T_ZHAO",
          "teacher_name": "赵老师"
        }
      ]
    }
  ],
  "conflict_groups": [
    {
      "id": "Group_1",
      "class_ids": ["Class_A", "Class_B"]
    }
  ]
}
```

当前标准课节建议固定为：

| period | name | start_time | end_time | duration_hours |
| --- | --- | --- | --- | --- |
| AM | 上午一 | 08:00 | 10:00 | 2 |
| AM | 上午二 | 10:20 | 12:20 | 2 |
| PM | 下午一 | 14:00 | 16:00 | 2 |
| PM | 下午二 | 16:20 | 18:20 | 2 |
| EVENING | 晚上 | 19:00 | 21:00 | 2 |

上面的课节生成命令只是公开示例。正式排课范围以 `01_年度排课窗口表`、`02_课节表` 和 `11_班级排课窗口表` 为准；后台会按班级实际开结课日期、年度窗口、产品窗口规则和全局停课日期共同过滤可用课节。

### 考研考季规则

考研产品需要按考季组织班级。考季对应的是学生参加考试的年份后一位，例如：

| 考试时间 | 考季 | 说明 |
| --- | --- | --- |
| 2025 年 12 月考试 | 26考研 | 报名 26考研班级 |
| 2026 年 12 月考试 | 27考研 | 报名 27考研班级 |

`2026-12`、`2027-12` 这类值属于考试月份，单独填写在 `exam_month`。后续排课时，同一产品在不同考季下会对应不同的一批班级，且每个考季的可排日期范围可能不同。所有班级都需要在对应考季的考试日期之前结课；班级层面的 `end_date` / `end_period` 可以作为“最晚结课时间”的具体约束。

产品课程课时表只固定“上什么课、多少课时、先后顺序”：

| product_id | product_name | subject_category | subject | window_name | stage | stage_priority | course_group | course_module | module_priority_in_group | course_code | course_name | total_hours |
| --- | --- | --- | --- | --- | --- | ---: | --- | --- | ---: | --- | --- | ---: |
| P_KY_YEAR_ROUND | 考研全年营 | 公共课 | 英语 | 暑假 | 基础 | 1 | 阅读类 | 词汇 | 1 | 待填 | 词汇 | 待填 |
| P_KY_YEAR_ROUND | 考研全年营 | 公共课 | 英语 | 暑假 | 基础 | 1 | 写作类 | 语法 | 1 | 待填 | 语法 | 待填 |
| P_KY_YEAR_ROUND | 考研全年营 | 公共课 | 英语 | 暑假 | 强化 | 2 | 阅读类 | 阅读 | 1 | 待填 | 阅读 | 待填 |
| P_KY_YEAR_ROUND | 考研全年营 | 公共课 | 英语 | 暑假 | 强化 | 2 | 写作类 | 写作 | 1 | 待填 | 写作 | 待填 |
| P_KY_YEAR_ROUND | 考研全年营 | 公共课 | 英语 | 秋季 | 冲刺 | 3 | 写作类 | 翻译 | 1 | 待填 | 翻译 | 待填 |

班级再引用产品并填写老师分工。老师安排只需要到阶段和课程类别；如果第一阶段的某个课程类别填写了老师，后续阶段同课程类别未填写时会默认沿用第一阶段老师：

| class_id | product_id | subject | stage | course_group | teacher_id | teacher_name |
| --- | --- | --- | --- | --- | --- | --- |
| Class_English_A | P_KY_YEAR_ROUND | 英语 | 基础 | 阅读类 | T_LI | 李老师 |
| Class_English_A | P_KY_YEAR_ROUND | 英语 | 基础 | 写作类 | T_ZHAO | 赵老师 |

产品如存在不同季节窗口的排课节奏，单独整理 `产品窗口排课规则表`，不要写在课程备注里：

| rule_id | product_id | season_window_id | window_name | allowed_periods | allowed_weekdays | block_hours | lessons_per_block | max_hours_per_class_per_day | max_blocks_per_class_per_day | delivery_mode |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| RULE_HSY_WINTER_DAY | P_HSY_ENGLISH | WINDOW_WINTER | 寒假 | AM\|PM | 周一\|周二\|周三\|周四\|周五\|周六 | 4 | 2 | 4 | 1 | 面授 |
| RULE_HSY_SUMMER_DAY | P_HSY_ENGLISH | WINDOW_SUMMER | 暑假 | AM\|PM | 周一\|周二\|周三\|周四\|周五\|周六 | 4 | 2 | 4 | 1 | 面授 |
| RULE_SJY_AUTUMN_EVENING | P_SUMMER_CAMP_ENGLISH | WINDOW_AUTUMN | 秋季 | EVENING | 周二\|周三\|周四\|周五 | 2 | 1 | 2 | 1 | 直播 |

### 字段说明

- `time_slots`: 所有可排课节。`schedule_window_id` 引用年度窗口，`period` 用 `AM`、`PM` 或 `EVENING`，同一天同一 `half_day_id` 内按 `order` 判断连续课节。
- `time_slots.start_time` / `time_slots.end_time`: 课节实际起止时间，例如 `08:00` 到 `10:00`。可选，但建议填写，CSV 和甘特图会显示。
- `time_slots.duration_hours`: 每个课节时长，不填默认 `2`。
- `teaching_areas` / `rooms`: 教学区和教室基础资源。住宿地点、咨询点、废弃或停用资源保留追溯但不启用；实际排课占用按教室判断。
- `products`: 产品主数据。项目、产品线、子产品、产品体系、标准人数、班容类型、科目、科目类型和课程性质都在这里维护。
- `products.project`: 项目标签。系统会按产品名称自动推断：包含 `考研` 为 `考研`，包含 `专升本` 为 `专升本`，其余默认为 `四六级`。
- `products.product_line`: 产品线标签。考研项目会按产品名自动推断为 `考研复试`、`考研无忧`、`考研集训营`、`考研个性化` 或 `考研其他`。
- `products.sub_product`: 子产品标签。会按产品线继续推断，例如 `寒暑营`、`全年营`、`无忧秋`、`考研复试大班` 等。
- `products.standard_capacity`: 标准人数，用于生成班容类型。标准人数小于等于 2 为 `VIP`，大于 2 为 `班课`。
- `products.subject` / `products.subject_category` / `products.course_nature`: 产品所属科目、科目类型和课程性质。班级选择产品后会自动继承。
- `classes.product_id`: 班级对应产品。填写后，班级会自动继承该产品标签、课程和课时。
- `classes.exam_season`: 班级考季标签。考研/专升本可选 `26考研`、`27考研`、`28考研`、`29考研`、`30考研`；四六级可选 `202512`、`202606`、`202612`、`202706`、`202712`、`202806`、`202812`。
- `classes.exam_month`: 考试月份，使用 `YYYY-MM` 格式，例如 `2026-12`、`2027-12`。
- `classes.suite_code`: 套班编码，用于后续把存在套班关系的班级归到同一组。
- `classes.subject`: 班级科目。若产品已维护科目，班级会自动继承；若产品未维护科目，可在班级侧选择科目，用于同步老师安排和导出排课输入时筛选课程。
- `classes.stages`: 班级阶段，可多选。可选值来自已选产品和已选科目下的阶段；不选表示继承该科目的全部阶段。
- `classes.start_date` / `classes.start_period`: 班级可排窗口的最早日期和时段，可选。例如 `2026-07-06` + `PM` 表示这个班不早于 7 月 6 日下午排课；不再表示首课必须当天开始。
- `classes.first_lesson_date` / `classes.first_lesson_period`: 固定首课锚点，可选。只有真正要求第一节课落在某天时才填写。例如 `2026-07-06` + `PM` 表示首课必须排在 7 月 6 日下午或更晚时段；如果填 `AM`，首课可以排在当天上午、下午或晚上。
- `classes.end_date` / `classes.end_period`: 班级最晚可上课的日期和时段，可选。例如 `2026-08-20` + `AM` 表示最后只能排到 8 月 20 日上午。
- `products.requirements.subject_category`: 科目类别，建议填写 `公共课` 或 `专业课`。
- `products.requirements.subject`: 科目名称。公共课建议使用 `英语`、`政治`、`数学`；专业课建议使用 `管综`、`计算机`、`西医`。
- `products.requirements.window_name`: 排课窗口期标签，主要用于寒假/春季/暑假/秋季等课程课时拆分；不按年份展开。
- `products.requirements.stage`: 课程阶段，例如 `基础`、`强化`、`冲刺`。
- `products.requirements.course_module`: 课程模块，可选。英语可填写 `词汇`、`语法`、`阅读`、`完形`、`新题型`、`写作`、`翻译`。同一个产品同一个科目有多个模块时，每个模块单独填写一行。
- `products.requirements.course_group`: 产品内的课程分组，例如 `阅读类`、`写作类`、`政治A类`、`数学类`。课程分组只表示产品课程结构，不限制老师能力；同一位老师可以在班级老师安排里绑定到任意课程分组。
- `products.requirements.total_hours`: 产品内该科目模块的总课时。
- `product_schedule_rules.block_hours`: 每次连续上课时长。例如总课时 8、每次 4 小时，会自动排成两次连续 4 小时课程。
- 若同一班级、同一阶段、同一课程分组由同一老师授课，系统允许多个短模块在同一规则课块内合并。例如马原 2 小时、思修 2 小时，且同属马原类、同老师、规则 `block_hours=4`，会合并为一次 4 小时课。
- 班级默认场地维护在 `classes.preferred_teaching_area_ids` / `classes.preferred_room_ids`，主要用于生成班级排课窗口的初始值；自动排课时优先使用班级排课窗口表中的年度窗口日期、时段和场地。已有班级排课窗口记录的班级，不再叠加班级级场地硬约束。
- `teachers`: 教师基础信息。`employee_id` / `id` 是教师员工ID，也是班级老师安排中的 `teacher_id`；可维护 `name`、`gender`、`project`、`teacher_role`、`employment_type`、`primary_subject`、`subject_type`、`contract_status`、`employment_status`。
- `product_schedule_rules`: 产品窗口规则，可选。按 `product_id + season_window_id` 维护，可继续用 `subject`、`stage`、`course_module`、`course_group` 缩小到具体课程，并限制 `allowed_periods`、`allowed_weekdays`、`block_hours`、每日上限和同半天连续块。
- `global_blackout_dates`: 全局停课日期，可选。这里填写的日期范围会在导出排课输入时从课节表中移除，适合维护所有产品都不排课的特殊假期。
- `classes.teacher_assignments.teacher_id`: 老师唯一编号。网页中填写老师姓名时，如果姓名在教师基础信息中唯一，会自动带出该 ID；若有同名老师，需要手动选择具体员工 ID。若同一位老师带多个班，必须使用同一个 `teacher_id`，程序会据此避免老师时间冲突。
- `classes.teacher_assignments.teacher_name`: 老师姓名，用于输出展示。
- `teacher_unavailability`: 老师本人不可排日期时段。兼职长期限制、全职请假、培训会议都在这里按多行例外维护。
- `conflict_groups`: 套班冲突组。同一组内的班级不能在同一课节同时上课。

## 输出格式

### CSV

列说明：

- `date`: 日期
- `period`: `AM`、`PM` 或 `EVENING`
- `start_slot_id`, `start_slot_name`: 连续课程开始课节
- `end_slot_id`, `end_slot_name`: 连续课程结束课节
- `start_time`, `end_time`: 连续课程实际起止时间
- `slot_ids`: 该连续课程占用的全部课节，用 `|` 分隔
- `class_id`, `class_name`
- `product_id`, `product_name`
- `subject_category`
- `subject`
- `stage`
- `course_module`
- `course_group`
- `teacher_id`, `teacher_name`
- `teaching_area_id`
- `duration_hours`: 该课程块总时长

### HTML 甘特图

使用 `--html-output schedule.html` 后会额外生成可视化页面：

- 每一行是一个班级。
- 每一列是一个固定课节。
- 每个色块代表一个连续课程块。
- 色块内显示科目、老师和教学区。
- 页面底部附带明细表，便于核对日期、课节、班级、老师和教学区。

## 正式数据整理建议

正式模板以后台当前数据框架为准，共 19 张业务表。每张表第 5 行是中文字段名，第 6 行是程序字段名，数据从第 7 行开始；不要手工改表名和第 6 行字段名。

1. 全局时间：`01_年度排课窗口表`、`02_课节表`
2. 基础资源：`03_教学区表`、`04_教室表`、`05_教师基础信息表`、`06_教师不可排日期时段表`
3. 产品规则：`07_产品管理表`、`08_产品课程课时表`、`09_产品窗口排课规则表`
4. 班级需求：`10_班级基础信息表`、`11_班级排课窗口表`、`12_班级老师安排表`、`13_班级排课互斥关系表`
5. 控制交付：`14_锁定课表`、`15_教学区通勤关系表`、`16_全局停课日期表`、`17_历史已排课明细表`、`18_ERP产品对应表`、`19_ERP标准产品清单`

`教学区表.short_name` 是前端筛选、关联和填写时显示的教学区简称；不填时系统会从 `name/campus` 自动推导。`region_tag` 是教学区区域标签，用于把距离相近的教学区归类，例如 `蜀山`、`经开/翡翠湖`、`集训营基地`。`address`、`longitude`、`latitude` 用于后续地图定位、跨校区距离和换教室建议；可用 `AMAP_KEY=你的高德Key python3 scripts/geocode_teaching_areas_amap.py` 从高德地理编码补齐。
`班级排课互斥关系表.class_ids` 用 `|` 分隔；默认会按同一 `exam_season + suite_code` 生成基础互斥组。

把表格发给我后，可以继续转换成程序需要的 JSON。

## 失败时排查建议

当提示 `无法找到满足约束的排课方案` 时，通常是：

- 教师不可排例外过多，或班级排课窗口过窄
- 课程的连续课时找不到足够相邻课节
- 教学区数量或容量不足
- 套班冲突组约束过紧
- 同一老师绑定了多个班，且班级窗口、产品窗口规则无法错开

建议优先检查年度课节是否充足、班级排课窗口是否过窄、教师不可排例外是否过多、产品窗口规则是否过紧，必要时再补充可用教室。
