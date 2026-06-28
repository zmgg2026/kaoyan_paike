const content = document.querySelector("#content");
const statusBox = document.querySelector("#status");
const pageTitle = document.querySelector("#pageTitle");
const pageSubtitle = document.querySelector("#pageSubtitle");
const saveDock = document.querySelector(".save-dock");
const saveDockStatus = document.querySelector("#saveDockStatus");
const saveButtons = [document.querySelector("#saveBtn"), document.querySelector("#fixedSaveBtn")].filter(Boolean);

const tabs = {
  overview: ["总览", "按时间、资源、产品规则、班级需求和交付控制查看准备度。"],
  timeData: ["年度窗口与课节", "核对年度排课窗口、课节明细、可用状态和不可排说明。"],
  rooms: ["教学区与教室", "维护可排教学区、教室容量和场地状态。"],
  teachers: ["教师基础信息", "维护教师员工ID、姓名、主科、用工类型和在职状态。"],
  teacherUnavailable: ["教师不可排时间", "维护兼职限制、请假和临时不可排日期时段。"],
  productMeta: ["产品管理", "维护产品标签、科目和课程性质，供班级自动继承。"],
  products: ["产品课程课时", "维护产品课程、阶段、课程组、优先级和总课时。"],
  rules: ["产品窗口规则", "维护产品在季节窗口内的授课形式、星期、时段和课时约束。"],
  classMeta: ["班级基础信息", "维护班级产品、实际日期边界、场地偏好和排课状态。"],
  classWindows: ["班级排课窗口", "维护班级在每个年度窗口内的可排日期、时段和窗口级场地。"],
  classes: ["班级老师安排", "维护班级任课老师，以及合班共享实际课表关系。"],
  classConflicts: ["班级互斥关系", "维护不能排在同一课节的班级分组。"],
  lockedLessons: ["锁定课表", "查看已固定课表和资源占用，排课时不自动移动。"],
  areaLinks: ["教学区通勤关系", "维护教学区之间的通勤距离、联排建议和跨区风险。"],
  businessMappings: ["ERP产品对应", "维护本地排课产品与 ERP 标准课程产品、课程编码和版本的对应关系。"],
  batchSchedules: ["排课运行维护", "先校验数据，再生成或更新课表，最后查看结果。"],
  launch: ["排课运行维护", "先校验数据，再生成或更新课表，最后查看结果。"],
  publish: ["只读发布与复用资料", "确认发布门禁，打开只读课表和复用资料。"],
};

const publicTeacherSubjects = new Set(["英语", "政治", "数学", "语文"]);
const teacherAssignmentScheduleModeOptions = [
  { value: "独立排课", label: "本班实际排课" },
  { value: "合班主班", label: "合班实际排课班级" },
  { value: "共享课表", label: "共享实际排课班级" },
];
const mutatingControlActions = new Set([
  "class-product-picker",
  "class-area-picker",
  "class-room-picker",
  "class-window-area-picker",
  "class-window-room-picker",
  "course-name-picker",
  "product-field",
  "rename-product-id",
  "rename-product-name",
]);
const mutatingButtonActions = new Set([
  "add-area",
  "add-room",
  "delete-room",
  "add-teacher",
  "delete-teacher",
  "add-teacher-unavailable",
  "delete-teacher-unavailable",
  "add-product",
  "refresh-product-tags",
  "delete-product",
  "add-course",
  "delete-course",
  "sync-course-name-tags",
  "load-rule-templates",
  "add-rule",
  "delete-rule",
  "add-blackout",
  "delete-blackout",
  "add-schedule-window",
  "generate-window-time-slots",
  "generate-all-time-slots",
  "add-class",
  "delete-class",
  "remove-class-area",
  "remove-class-room",
  "remove-class-window-area",
  "remove-class-window-room",
  "refresh-class-tags",
  "sync-teachers",
  "sync-all-teachers",
  "delete-assignment",
  "add-class-window",
  "delete-class-window",
  "add-area-link",
  "delete-area-link",
  "add-class-conflict",
  "sync-suite-conflicts",
  "remove-class-conflict-class",
  "delete-class-conflict",
  "refresh-business-product-mappings",
]);
const productTagFilterFields = [
  { field: "project", label: "项目", placeholder: "全部项目" },
  { field: "product_line", label: "产品线", placeholder: "全部产品线" },
  { field: "sub_product", label: "子产品", placeholder: "全部子产品" },
  { field: "product_system", label: "产品体系", placeholder: "全部体系" },
  { field: "subject_category", label: "科目类型", placeholder: "全部类型" },
  { field: "subject", label: "科目", placeholder: "全部科目" },
  { field: "course_nature", label: "课程性质", placeholder: "全部性质" },
];
const stageOrder = ["导学", "专项", "基础", "强化", "冲刺", "一轮", "二轮", "三轮", "四轮", "复试"];
const stageOrderIndex = new Map(stageOrder.map((stage, index) => [stage, index]));
const seasonWindowOrder = ["寒假", "春季", "暑假", "秋季"];
const seasonWindowOrderIndex = new Map(seasonWindowOrder.map((name, index) => [name, index]));
const visibleRowLimits = {
  rules: 40,
  classMeta: 40,
  classWindows: 30,
  classTeachers: 50,
  classConflicts: 25,
};

let state = null;
let activeTab = "overview";
let hasUnsavedChanges = false;
let isSavingData = false;
let selected = {
  areaId: "",
  areaSearch: "",
  productId: "",
  classId: "",
  roomSearch: "",
  teacherSearch: "",
  productSearch: "",
  productMetaFilters: emptyProductTagFilters(),
  classSearch: "",
  classProductFilter: "",
  classSubjectFilter: "",
  classTeacherSearch: "",
  classMetaFilters: emptyProductTagFilters(),
  classConflictSearch: "",
  ruleSearch: "",
  ruleWindowFilter: "",
  ruleDeliveryFilter: "",
  ruleIssueFilter: "",
  timeSlotSearch: "",
  teacherUnavailableSearch: "",
  classWindowSearch: "",
  lockedLessonSearch: "",
  areaLinkSearch: "",
  areaLinkRelationFilter: "",
  areaLinkIssueFilter: "",
  businessMappingSearch: "",
  businessMappingStatusFilter: "",
  productListScrollTop: 0,
  productLineFilter: "",
  productCourseProductFilters: emptyProductTagFilters(),
  batchSuiteCodes: "",
  batchClassIds: "",
  batchSubProducts: "",
  courseFilters: {
    keyword: "",
    quarter: "",
    stage: "",
    course_module: "",
    course_name: "",
    course_group: "",
  },
};
let pipelineJob = null;
let pipelinePollTimer = null;
let templateResult = null;
let preflightResult = null;
let batchScheduleJob = null;
let batchSchedulePollTimer = null;
let classTeacherSearchRenderTimer = null;

const batchSchedulePage = {
  title: "排课结果核对总表",
  detail: "用于核对已生成课表，重点查看班级、课次、老师、教室、日期和锁定状态。",
  url: "/outputs/batch_schedule_maintenance.html",
};
const dataTemplatePage = {
  title: "AI排课基础数据模板",
  detail: "用于填写或核对排课基础数据，完成后在本页上传校验或运行排课。",
  url: "/outputs/ai_scheduling_sop_20260625/AI排课基础数据模板.xlsx",
};

function html(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function teacherSubjectType(primarySubject) {
  const subject = String(primarySubject || "").trim();
  if (!subject) return "";
  return publicTeacherSubjects.has(subject) ? "公共课" : "专业课";
}

function inferSuiteCodeFromClassName(value) {
  const match = String(value || "").match(/(\d{2})届\s*(\d{1,2})班/);
  if (!match) return "";
  return `${match[1]}${String(Number(match[2])).padStart(2, "0")}`;
}

function applyTeacherSubjectType(teacher) {
  const subjectType = teacherSubjectType(teacher.primary_subject);
  if (subjectType) teacher.subject_type = subjectType;
}

function showStatus(message, type = "") {
  statusBox.textContent = message || "";
  statusBox.title = message || "";
  statusBox.className = `status topbar-status ${type}`.trim();
}

function updateSaveControls(message = "") {
  const statusText = message || (hasUnsavedChanges ? "有未保存修改" : "当前数据已保存");
  if (saveDockStatus) saveDockStatus.textContent = statusText;
  if (saveDock) {
    saveDock.classList.toggle("unsaved", hasUnsavedChanges && !isSavingData);
    saveDock.classList.toggle("saving", isSavingData);
    saveDock.classList.toggle("saved", !hasUnsavedChanges && !isSavingData);
    saveDock.classList.toggle("error", false);
  }
  for (const button of saveButtons) {
    button.disabled = isSavingData || !state;
    button.textContent = isSavingData
      ? "保存中..."
      : button.id === "fixedSaveBtn"
        ? "保存"
        : "保存数据修改";
  }
}

function markUnsavedChange(message = "有未保存修改，请保存数据修改") {
  if (!state || isSavingData) return;
  hasUnsavedChanges = true;
  updateSaveControls(message);
}

function markSaveError(message) {
  if (saveDock) {
    saveDock.classList.remove("saving", "saved");
    saveDock.classList.add("error");
  }
  if (saveDockStatus) saveDockStatus.textContent = message || "保存失败，请查看页面提示";
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `${response.status} ${response.statusText}`);
  }
  return data;
}

async function loadData() {
  showStatus("正在加载本地数据...");
  updateSaveControls("正在加载本地数据...");
  state = await requestJson("/api/data");
  state.global_blackout_dates = state.global_blackout_dates || [];
  state.schedule_windows = state.schedule_windows || [];
  state.time_slots = state.time_slots || [];
  state.class_conflict_groups = state.class_conflict_groups || [];
  state.class_window_boundaries = state.class_window_boundaries || [];
  state.teacher_unavailability = state.teacher_unavailability || [];
  state.locked_scheduled_lessons = state.locked_scheduled_lessons || [];
  state.historical_scheduled_lessons = state.historical_scheduled_lessons || [];
  state.erp_standard_products = state.erp_standard_products || [];
  state.business_product_mappings = state.business_product_mappings || [];
  state.teachers = state.teachers || [];
  state.products = state.products || [];
  hydrateLabels();
  selected.areaId = selected.areaId || state.teaching_areas[0]?.id || "";
  selected.productId = selected.productId || products()[0]?.id || "";
  selected.classId = selected.classId || state.classes[0]?.id || "";
  hasUnsavedChanges = false;
  updateSaveControls("数据已加载，修改后请保存");
  showStatus("数据已加载。", "ok");
  render();
}

function hydrateLabels() {
  for (const teacher of state.teachers || []) {
    applyTeacherSubjectType(teacher);
  }
  for (const product of products()) {
    applyProductAutoTags(product.id, false);
  }
  for (const cls of state.classes || []) {
    cls.preferred_room_is_required = Boolean(cls.preferred_room_is_required);
    cls.is_schedule_locked = Boolean(cls.is_schedule_locked || cls.is_manual_schedule_locked);
    cls.is_manual_schedule_locked = cls.is_schedule_locked;
    if (!arrayValues(cls.stages).length && arrayValues(cls.selected_stages).length) cls.stages = arrayValues(cls.selected_stages);
    applyClassAutoTags(cls, false);
    pruneClassStages(cls, true);
  }
}

function conflictGroupIsActive(group) {
  const value = group?.is_conflict_group_active;
  if (value === "" || value === undefined || value === null) return group?.is_active !== false;
  const normalized = String(value).trim().toLowerCase();
  return value !== false && normalized !== "否" && normalized !== "false";
}

function conflictGroupSource(group) {
  return group?.conflict_source || group?.source || "手动";
}

async function saveData() {
  if (isSavingData) return;
  isSavingData = true;
  updateSaveControls("正在保存数据修改...");
  showStatus("正在保存...");
  let finalMessage = "数据已保存";
  let failed = false;
  try {
    const result = await requestJson("/api/save", {
      method: "POST",
      body: JSON.stringify(state),
    });
    await loadData();
    hasUnsavedChanges = false;
    finalMessage = `已保存：${result.updated_at}`;
    showStatus(`已保存。更新时间：${result.updated_at}`, "ok");
  } catch (error) {
    failed = true;
    markSaveError(error.message);
    throw error;
  } finally {
    isSavingData = false;
    if (!failed) {
      updateSaveControls(finalMessage);
    } else {
      for (const button of saveButtons) {
        button.disabled = !state;
        button.textContent = button.id === "fixedSaveBtn" ? "保存" : "保存数据修改";
      }
    }
  }
}

async function exportSchedulerInput() {
  showStatus("正在导出排课输入...");
  const result = await requestJson("/api/export-scheduler-input", {
    method: "POST",
    body: JSON.stringify(state),
  });
  showStatus(
    `已导出：${result.path}\n课节 ${result.counts.time_slots} 个，教室 ${result.counts.rooms} 间，产品 ${result.counts.products} 个，班级 ${result.counts.classes} 个。`,
    "ok",
  );
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",", 2)[1] : value);
    };
    reader.onerror = () => reject(reader.error || new Error("读取文件失败"));
    reader.readAsDataURL(file);
  });
}

async function uploadAndRunPipeline(input) {
  showStatus("正在上传排课数据...");
  const payloadFiles = await filesPayload(input);
  const result = await requestJson("/api/pipeline/upload-run", {
    method: "POST",
    body: JSON.stringify({ files: payloadFiles }),
  });
  input.value = "";
  pipelineJob = result;
  showStatus(`已创建排课任务：${result.job_id}`, "ok");
  renderLaunch();
  pollPipelineJob(result.job_id);
}

async function filesPayload(input) {
  const files = [...(input?.files || [])];
  if (!files.length) {
    throw new Error("请先选择 Excel 或 CSV 文件。");
  }
  const payloadFiles = [];
  for (const file of files) {
    payloadFiles.push({
      name: file.name,
      content_base64: await fileToBase64(file),
    });
  }
  return payloadFiles;
}

async function generateFormalTemplate(input) {
  showStatus("正在生成预填模板...");
  const payloadFiles = await filesPayload(input);
  const result = await requestJson("/api/templates/generate", {
    method: "POST",
    body: JSON.stringify({ files: payloadFiles }),
  });
  input.value = "";
  templateResult = result;
  showStatus("预填模板已生成。", "ok");
  renderLaunch();
}

async function runPipelinePreflight(input) {
  showStatus("正在执行上传前校验...");
  const payloadFiles = await filesPayload(input);
  const result = await requestJson("/api/pipeline/preflight", {
    method: "POST",
    body: JSON.stringify({ files: payloadFiles }),
  });
  input.value = "";
  preflightResult = result;
  showStatus(result.passed ? "上传前校验通过，可以运行完整排课。" : "上传前校验未通过，请查看报告。", result.passed ? "ok" : "error");
  renderLaunch();
}

async function pollPipelineJob(jobId) {
  if (pipelinePollTimer) clearTimeout(pipelinePollTimer);
  const result = await requestJson(`/api/pipeline/jobs/${encodeURIComponent(jobId)}`);
  pipelineJob = result;
  if (activeTab === "launch" || activeTab === "batchSchedules") renderLaunch();
  if (result.status === "queued" || result.status === "running") {
    pipelinePollTimer = setTimeout(() => {
      pollPipelineJob(jobId).catch((error) => showStatus(error.message, "error"));
    }, 1200);
  } else if (result.status === "succeeded") {
    await loadData();
    activeTab = "launch";
    showStatus("排课闭环已完成。", "ok");
  } else if (result.status === "failed") {
    showStatus(result.error || "排课任务失败。", "error");
  }
}

function batchSchedulePayload(mode) {
  selected.batchSuiteCodes = content.querySelector('[data-action="batch-suite-codes"]')?.value || "";
  selected.batchClassIds = content.querySelector('[data-action="batch-class-ids"]')?.value || "";
  selected.batchSubProducts = content.querySelector('[data-action="batch-sub-products"]')?.value || "";
  return {
    mode,
    suite_codes: selected.batchSuiteCodes,
    class_ids: selected.batchClassIds,
    sub_products: selected.batchSubProducts,
  };
}

async function runBatchSchedule(mode) {
  const payload = batchSchedulePayload(mode);
  showStatus(mode === "fast" ? "正在启动快速局部重排..." : "正在启动全量重算...");
  const result = await requestJson("/api/batch-schedule/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  batchScheduleJob = result;
  showStatus(`已创建课表维护任务：${result.job_id}`, "ok");
  renderLaunch();
  pollBatchScheduleJob(result.job_id);
}

async function pollBatchScheduleJob(jobId) {
  if (batchSchedulePollTimer) clearTimeout(batchSchedulePollTimer);
  const result = await requestJson(`/api/batch-schedule/jobs/${encodeURIComponent(jobId)}`);
  batchScheduleJob = result;
  if (activeTab === "launch" || activeTab === "batchSchedules") renderLaunch();
  if (result.status === "queued" || result.status === "running") {
    batchSchedulePollTimer = setTimeout(() => {
      pollBatchScheduleJob(jobId).catch((error) => showStatus(error.message, "error"));
    }, 1200);
  } else if (result.status === "succeeded") {
    batchSchedulePage.url = `/outputs/batch_schedule_maintenance.html?ts=${Date.now()}`;
    showStatus("课表维护页已更新。", "ok");
    if (activeTab === "launch" || activeTab === "batchSchedules") renderLaunch();
  } else if (result.status === "failed") {
    showStatus(result.error || "课表维护任务失败。", "error");
  }
}

function downloadProductsCsv() {
  window.location.href = "/api/products/download";
  showStatus("正在下载产品管理表 CSV。", "ok");
}

function downloadClassesCsv() {
  window.location.href = "/api/classes/download";
  showStatus("正在下载班级管理表 CSV。", "ok");
}

async function importProductsFile(input) {
  const file = input.files?.[0];
  if (!file) return;
  showStatus("正在导入产品管理表...");
  const csv = await file.text();
  const result = await requestJson("/api/products/import", {
    method: "POST",
    body: JSON.stringify({ csv }),
  });
  input.value = "";
  await loadData();
  showStatus(`已导入 ${result.imported} 条产品数据，当前共 ${result.total_products} 个产品。`, "ok");
}

async function importClassesFile(input) {
  const file = input.files?.[0];
  if (!file) return;
  showStatus("正在导入班级管理表...");
  const csv = await file.text();
  const result = await requestJson("/api/classes/import", {
    method: "POST",
    body: JSON.stringify({ csv }),
  });
  input.value = "";
  await loadData();
  showStatus(`已导入 ${result.imported} 条班级数据，当前共 ${result.total_classes} 个班级。`, "ok");
}

function products() {
  const rows = state.products?.length ? state.products : deriveProductsFromCourses();
  return rows
    .filter((product) => product.id)
    .map((product) => {
      const project = product.project || inferProject(product.name || product.id);
      const productLine = product.product_line || inferProductLine(product.name || product.id, "", project);
      const standardCapacity = Number(product.standard_capacity || 0);
      return {
        ...product,
        project,
        product_line: productLine,
        sub_product: product.sub_product || inferSubProduct(productLine, product.name || product.id),
        standard_capacity: standardCapacity,
        capacity_type: product.capacity_type || inferCapacityType(standardCapacity),
      };
    })
    .sort((a, b) => productLineOrder(a.product_line) - productLineOrder(b.product_line) || a.id.localeCompare(b.id));
}

function deriveProductsFromCourses() {
  const map = new Map();
  for (const course of state.product_courses || []) {
    if (!course.product_id) continue;
    const existing = map.get(course.product_id) || {
      id: course.product_id,
      name: course.product_name || course.product_id,
      project: course.project || "",
      product_line: course.product_line || "",
      sub_product: course.sub_product || "",
      product_system: course.product_system || "",
      standard_capacity: course.standard_capacity || 0,
      capacity_type: course.capacity_type || "",
      subject: "",
      subject_category: "",
      course_nature: course.course_nature || "",
      notes: "",
      subjects: new Set(),
      categories: new Set(),
    };
    if (course.subject) existing.subjects.add(course.subject);
    if (course.subject_category) existing.categories.add(course.subject_category);
    map.set(course.product_id, existing);
  }
  return [...map.values()].map((product) => {
    const subjects = [...product.subjects];
    const categories = [...product.categories];
    delete product.subjects;
    delete product.categories;
    product.subject = subjects.length === 1 ? subjects[0] : product.subject || "";
    product.subject_category = categories.length === 1 ? categories[0] : product.subject_category || "";
    return product;
  });
}

function labelText(...values) {
  return values.map((value) => String(value || "").trim()).filter(Boolean).join(" ");
}

function inferProject(name) {
  const text = String(name || "");
  if (text.includes("考研")) return "考研";
  if (text.includes("专升本")) return "专升本";
  return "四六级";
}

function inferProductLine(productName, className = "", project = "") {
  const text = labelText(className, productName);
  const resolvedProject = project || inferProject(productName || className);
  if (resolvedProject !== "考研") return resolvedProject;
  if (text.includes("复试")) return "考研复试";
  if (text.includes("无忧")) return "考研无忧";
  if (text.includes("个性化")) return "考研个性化";
  if (text.includes("营") || text.includes("集训")) return "考研集训营";
  return "考研其他";
}

function inferSubProduct(productLine, productName, className = "") {
  const text = labelText(className, productName);
  const classText = String(className || "");
  if (productLine === "考研复试") return classText.includes("直通车") ? "考研复试小班" : "考研复试大班";
  if (productLine === "考研无忧") {
    const rules = [
      ["无忧秋", "无忧秋"],
      ["无忧寒", "无忧寒"],
      ["无忧春", "无忧春"],
      ["无忧暑", "无忧暑"],
      ["秋", "无忧秋"],
      ["寒", "无忧寒"],
      ["春", "无忧春"],
      ["暑", "无忧暑"],
    ];
    return rules.find(([keyword]) => text.includes(keyword))?.[1] || "无忧";
  }
  if (productLine === "考研集训营") {
    const rules = [
      ["全年", "全年营"],
      ["半年", "半年营"],
      ["寒暑", "寒暑营"],
      ["暑假", "暑假营"],
      ["暑期", "暑假营"],
      ["冲刺", "冲刺营"],
    ];
    return rules.find(([keyword]) => text.includes(keyword))?.[1] || "集训营";
  }
  if (productLine === "考研个性化") return "考研个性化";
  if (productLine === "考研其他") {
    const rules = [
      ["在职", "考研在职班"],
      ["呆滞", "考研呆滞班"],
      ["企业", "考研企培班"],
      ["合作", "考研企培班"],
      ["体验", "考研活动"],
      ["大咖", "考研大咖班"],
      ["专项", "考研专项班"],
    ];
    return rules.find(([keyword]) => text.includes(keyword))?.[1] || "";
  }
  return productLine || "";
}

function inferCapacityType(standardCapacity) {
  const value = Number(standardCapacity || 0);
  if (value <= 0) return "";
  return value <= 2 ? "VIP" : "班课";
}

function productLineForName(name) {
  return inferProductLine(name);
}

function productLineOrder(line) {
  return productLines().indexOf(line) === -1
    ? 99
    : productLines().indexOf(line);
}

function productLines() {
  return ["考研复试", "考研集训营", "考研无忧", "考研个性化", "考研其他", "专升本", "四六级"];
}

function productTagValues(productRows, field) {
  return [...new Set(productRows.map((product) => product[field]).filter(Boolean))]
    .sort((a, b) => String(a).localeCompare(String(b), "zh-CN"));
}

function productMatchesTagFilters(product, filters) {
  return productTagFilterFields.every(({ field }) => !filters[field] || product[field] === filters[field]);
}

function productMatchesKeyword(product, keyword) {
  const text = String(keyword || "").trim().toLowerCase();
  if (!text) return true;
  return [
    product.id,
    product.name,
    product.project,
    product.product_line,
    product.sub_product,
    product.product_system,
    product.subject_category,
    product.subject,
    product.course_nature,
    product.capacity_type,
    product.notes,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
    .includes(text);
}

function productTagFilterControls(actionName, filters, sourceProducts, visibleCount, totalCount, clearAction, compact = false, itemLabel = "产品") {
  return `
    <div class="filter-bar tag-filter-bar ${compact ? "compact" : ""}">
      ${productTagFilterFields
        .map(
          ({ field, label, placeholder }) => `
            <label><span>${html(label)}</span><select data-action="${html(actionName)}" data-field="${html(field)}">${selectOptions(productTagValues(sourceProducts, field), filters[field], placeholder)}</select></label>
          `,
        )
        .join("")}
      <div class="filter-actions">
        <span>显示 ${visibleCount} / ${totalCount} 个${html(itemLabel)}</span>
        <button type="button" class="small" data-action="${html(clearAction)}">清空筛选</button>
      </div>
    </div>
  `;
}

function productCoursePageProducts() {
  return products().filter((product) => productMatchesTagFilters(product, selected.productCourseProductFilters));
}

function teacherChoices() {
  const map = new Map();
  for (const teacher of state.teachers || []) {
    const id = teacher.id || teacher.employee_id;
    if (id) {
      map.set(id, {
        id,
        name: teacher.name || id,
        project: teacher.project || "",
        primary_subject: teacher.primary_subject || "",
        teacher_type: teacher.employment_type || teacher.teacher_type || "",
        employment_status: teacher.employment_status || "",
      });
    }
  }
  for (const teacher of state.lookups?.teachers || []) {
    if (teacher.id && !map.has(teacher.id)) {
      map.set(teacher.id, {
        id: teacher.id,
        name: teacher.name || teacher.id,
        project: teacher.project || "",
        primary_subject: teacher.primary_subject || "",
        teacher_type: teacher.employment_type || teacher.teacher_type || "",
        employment_status: teacher.employment_status || "",
      });
    }
  }
  return [...map.values()].sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN") || a.id.localeCompare(b.id));
}

function teacherById(teacherId) {
  return teacherChoices().find((teacher) => teacher.id === teacherId) || null;
}

function teacherDetailLabel(teacher) {
  return [teacher.id, teacher.primary_subject, teacher.employment_type || teacher.teacher_type, teacher.project, teacher.employment_status].filter(Boolean).join(" / ");
}

function teacherNameMatches(name) {
  const keyword = String(name || "").trim();
  if (!keyword) return [];
  return teacherChoices().filter((teacher) => teacher.name === keyword);
}

function teacherNameOptions() {
  const seen = new Set();
  return teacherChoices().filter((teacher) => {
    if (!teacher.name || seen.has(teacher.name)) return false;
    seen.add(teacher.name);
    return true;
  });
}

function schedulePeriods() {
  return [
    { id: "AM", name: "上午" },
    { id: "PM", name: "下午" },
    { id: "EVENING", name: "晚上" },
  ];
}

function weekdays() {
  return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
}

function seasonWindowSelectOptions() {
  return [
    { value: "WINDOW_WINTER", label: "寒假" },
    { value: "WINDOW_SPRING", label: "春季" },
    { value: "WINDOW_SUMMER", label: "暑假" },
    { value: "WINDOW_AUTUMN", label: "秋季" },
  ];
}

function seasonWindowName(seasonWindowId) {
  return seasonWindowSelectOptions().find((item) => item.value === seasonWindowId)?.label || "";
}

function seasonWindowIdFromName(windowName) {
  return seasonWindowSelectOptions().find((item) => item.label === windowName)?.value || "";
}

function ruleScopeTypes() {
  return [
    { id: "keywords", name: "产品名称包含" },
    { id: "product_ids", name: "指定产品" },
    { id: "all", name: "全部产品" },
  ];
}

function ruleScopeSelectOptions() {
  return ruleScopeTypes().map((item) => ({ value: item.id, label: item.name }));
}

function productName(productId) {
  return products().find((product) => product.id === productId)?.name || productId || "";
}

function productById(productId) {
  return products().find((product) => product.id === productId) || null;
}

function productPickerLabel(productId) {
  const product = productById(productId);
  if (!product) return productId || "";
  const tags = [product.project, product.product_line, product.sub_product, product.subject].filter(Boolean).join(" / ");
  return `${product.name || product.id}（${product.id}${tags ? ` / ${tags}` : ""}）`;
}

function productCompactLabel(productId) {
  const product = productById(productId);
  if (!product) return productId || "";
  return `${product.name || product.id}（${product.id}）`;
}

function productIdFromPickerValue(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return products().find((product) => {
    const label = productPickerLabel(product.id);
    const compactLabel = productCompactLabel(product.id);
    return text === product.id || text === product.name || text === label || text === compactLabel;
  })?.id || "";
}

function productSearchText(product) {
  return [
    product.id,
    product.name,
    product.project,
    product.product_line,
    product.sub_product,
    product.product_system,
    product.course_nature,
    product.subject_category,
    product.subject,
    productPickerLabel(product.id),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function productIdFromSearchValue(value, context = {}) {
  const exact = productIdFromPickerValue(value);
  if (exact) return exact;
  const tokens = String(value || "")
    .trim()
    .toLowerCase()
    .split(/[\s/|,，;；()（）]+/)
    .filter(Boolean);
  if (!tokens.length) return "";
  let matches = products().filter((product) => {
    const haystack = productSearchText(product);
    return tokens.every((token) => haystack.includes(token));
  });
  for (const field of ["subject", "course_nature", "product_system", "product_line"]) {
    if (matches.length <= 1 || !context[field]) continue;
    const narrowed = matches.filter((product) => product[field] === context[field]);
    if (narrowed.length) matches = narrowed;
  }
  return matches.length === 1 ? matches[0].id : "";
}

function productPickerDatalist() {
  return `
    <datalist id="classProductChoices">
      ${products().map((product) => `<option value="${html(productPickerLabel(product.id))}"></option>`).join("")}
    </datalist>
  `;
}

function classProductPicker(cls) {
  return `<input data-action="class-product-picker" data-id="${html(cls.id)}" value="${html(productCompactLabel(cls.product_id))}" list="classProductChoices" placeholder="输入产品关键字或产品ID后选择">`;
}

function safeDomId(value) {
  return String(value || "").replace(/[^\w-]/g, "_");
}

function areaShortName(area) {
  if (!area) return "";
  return area.short_name || area.name || area.campus || area.id || "";
}

function areaRegionTag(area) {
  return area?.region_tag || "";
}

function teachingAreaOptionName(area) {
  const region = areaRegionTag(area);
  return [areaShortName(area), region].filter(Boolean).join(" · ") || area.id || "";
}

function teachingAreaOptions() {
  return state.teaching_areas.map((area) => ({ id: area.id, name: teachingAreaOptionName(area) }));
}

function teachingAreaPickerLabel(areaId) {
  const area = state.teaching_areas.find((item) => item.id === areaId);
  if (!area) return areaId || "";
  return areaShortName(area) || area.id;
}

function teachingAreaPickerOptionLabel(area) {
  const label = teachingAreaPickerLabel(area.id);
  const detail = [areaRegionTag(area), area.id].filter(Boolean).join(" / ");
  return detail ? `${label}（${detail}）` : label;
}

function teachingAreaSearchText(areaId) {
  const area = state.teaching_areas.find((item) => item.id === areaId);
  if (!area) return areaId || "";
  return [
    area.id,
    area.short_name,
    area.region_tag,
    area.address,
    area.longitude,
    area.latitude,
    area.name,
    area.campus,
    teachingAreaPickerOptionLabel(area),
  ].filter(Boolean).join(" ");
}

function teachingAreaIdFromPickerValue(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return state.teaching_areas.find((area) => {
    const label = teachingAreaPickerLabel(area.id);
    const optionLabel = teachingAreaPickerOptionLabel(area);
    return text === area.id || text === area.short_name || text === area.region_tag || text === area.name || text === area.campus || text === label || text === optionLabel;
  })?.id || "";
}

function roomPickerLabel(roomId) {
  const room = state.rooms.find((item) => item.id === roomId);
  if (!room) return roomId || "";
  const areaLabel = room.teaching_area_name || areaName(room.teaching_area_id);
  const detail = [room.id, areaLabel, room.capacity ? `${room.capacity}人` : ""].filter(Boolean).join(" / ");
  return `${room.name || room.id}${detail ? `（${detail}）` : ""}`;
}

function roomIdFromPickerValue(value, cls) {
  const text = String(value || "").trim();
  if (!text) return "";
  const candidates = new Set(classRoomOptions(cls).map((room) => room.id));
  return state.rooms.find((room) => {
    if (!candidates.has(room.id)) return false;
    const label = roomPickerLabel(room.id);
    return text === room.id || text === room.name || text === label;
  })?.id || "";
}

function classWindowRoomIdFromPickerValue(value, item) {
  const text = String(value || "").trim();
  if (!text) return "";
  const candidates = new Set(classWindowRoomOptions(item).map((room) => room.id));
  return state.rooms.find((room) => {
    if (!candidates.has(room.id)) return false;
    const label = roomPickerLabel(room.id);
    return text === room.id || text === room.name || text === label || text === roomName(room.id);
  })?.id || "";
}

function teachingAreaPickerDatalist() {
  return `
    <datalist id="classTeachingAreaChoices">
      ${state.teaching_areas.map((area) => `<option value="${html(teachingAreaPickerOptionLabel(area))}"></option>`).join("")}
    </datalist>
  `;
}

function classRoomPickerDatalist(cls, listId) {
  return `
    <datalist id="${html(listId)}">
      ${classRoomOptions(cls).map((room) => `<option value="${html(roomPickerLabel(room.id))}"></option>`).join("")}
    </datalist>
  `;
}

function pickerToken(label, action, classId, value) {
  return `
    <span class="picker-token" title="${html(label)}">
      <span>${html(label)}</span>
      <button type="button" data-action="${html(action)}" data-id="${html(classId)}" data-value="${html(value)}" aria-label="移除">x</button>
    </span>
  `;
}

function classRoomRequirementToggle(cls) {
  return `
    <label class="inline-check room-required-toggle">
      <input type="checkbox" data-entity="class" data-id="${html(cls.id)}" data-field="preferred_room_is_required" ${cls.preferred_room_is_required ? "checked" : ""}>
      默认教室必选
    </label>
  `;
}

function classScheduleLockedToggle(cls) {
  return `
    <label class="inline-check room-required-toggle">
      <input type="checkbox" data-entity="class" data-id="${html(cls.id)}" data-field="is_schedule_locked" ${cls.is_schedule_locked ? "checked" : ""}>
      手动锁定排课结果
    </label>
  `;
}

function classTeachingAreaPicker(cls) {
  const selectedAreas = arrayValues(cls.preferred_teaching_area_ids);
  return `
    <div class="token-picker">
      <input data-action="class-area-picker" data-id="${html(cls.id)}" value="" list="classTeachingAreaChoices" placeholder="搜索教学区简称 / 区域 / 校区">
      <div class="token-list">
        ${selectedAreas.length
          ? selectedAreas.map((areaId) => pickerToken(teachingAreaPickerLabel(areaId), "remove-class-area", cls.id, areaId)).join("")
          : `<span class="token-empty">未指定</span>`}
      </div>
    </div>
  `;
}

function classRoomPicker(cls) {
  const listId = `classRoomChoices-${safeDomId(cls.id)}`;
  const selectedRooms = arrayValues(cls.preferred_room_ids);
  return `
    <div class="token-picker">
      <input data-action="class-room-picker" data-id="${html(cls.id)}" value="" list="${html(listId)}" placeholder="搜索教室名称 / 教学区简称">
      <div class="token-list">
        ${selectedRooms.length
          ? selectedRooms.map((roomId) => pickerToken(roomPickerLabel(roomId), "remove-class-room", cls.id, roomId)).join("")
          : `<span class="token-empty">未指定</span>`}
      </div>
      ${classRoomPickerDatalist(cls, listId)}
    </div>
  `;
}

function classWindowTeachingAreaPicker(item, index) {
  const selectedAreas = arrayValues(item.preferred_teaching_area_ids);
  return `
    <div class="token-picker class-window-resource-picker">
      <input data-action="class-window-area-picker" data-index="${index}" value="" list="classTeachingAreaChoices" placeholder="搜索教学区名称">
      <div class="token-list class-window-token-list">
        ${selectedAreas.length
          ? selectedAreas.map((areaId) => pickerToken(teachingAreaPickerLabel(areaId), "remove-class-window-area", index, areaId)).join("")
          : `<span class="token-empty">未指定教学区</span>`}
      </div>
    </div>
  `;
}

function classWindowRoomPicker(item, index) {
  const listId = `classWindowRoomChoices-${index}-${safeDomId(item.class_window_id || item.class_id || "new")}`;
  const selectedRooms = arrayValues(item.preferred_room_ids);
  return `
    <div class="token-picker class-window-resource-picker">
      <input data-action="class-window-room-picker" data-index="${index}" value="" list="${html(listId)}" placeholder="搜索教室名称">
      <div class="token-list class-window-token-list">
        ${selectedRooms.length
          ? selectedRooms.map((roomId) => pickerToken(roomPickerLabel(roomId), "remove-class-window-room", index, roomId)).join("")
          : `<span class="token-empty">未指定教室</span>`}
      </div>
      <datalist id="${html(listId)}">
        ${classWindowRoomOptions(item).map((room) => `<option value="${html(roomPickerLabel(room.id))}"></option>`).join("")}
      </datalist>
    </div>
  `;
}

function productSubjectCategory(productId, subject) {
  const product = productById(productId);
  if (product?.subject_category) return product.subject_category;
  const categories = [
    ...new Set(
      productCourses(productId)
        .filter(({ course }) => !subject || course.subject === subject)
        .map(({ course }) => course.subject_category)
        .filter(Boolean),
    ),
  ];
  return categories.length === 1 ? categories[0] : "";
}

function examSeasonOptions(project) {
  const normalizedProject = String(project || "").trim();
  if (normalizedProject === "四六级") return ["202512", "202606", "202612", "202706", "202712", "202806", "202812"];
  if (normalizedProject === "考研" || normalizedProject === "专升本") return ["26考研", "27考研", "28考研", "29考研", "30考研"];
  return ["26考研", "27考研", "28考研", "29考研", "30考研"];
}

function classExamSeasonOptions(cls) {
  const options = examSeasonOptions(cls?.project || productById(cls?.product_id)?.project || "");
  const current = String(cls?.exam_season || "");
  return current && !options.includes(current) ? [current, ...options] : options;
}

function autoProductTags(product) {
  const project = inferProject(product?.name || "");
  const productLine = inferProductLine(product?.name || "", "", project);
  const standardCapacity = Number(product?.standard_capacity || 0);
  return {
    project,
    product_line: productLine,
    sub_product: inferSubProduct(productLine, product?.name || ""),
    capacity_type: inferCapacityType(standardCapacity),
  };
}

function autoClassTags(cls) {
  const product = productById(cls.product_id);
  const standardCapacity = Number(product?.standard_capacity || 0);
  return {
    project: product?.project || "",
    product_line: product?.product_line || "",
    sub_product: product?.sub_product || "",
    product_system: product?.product_system || "",
    course_nature: product?.course_nature || "",
    subject: product?.subject || cls.subject || "",
    subject_category: product?.subject_category || productSubjectCategory(cls.product_id, cls.subject),
    standard_capacity: standardCapacity,
    capacity_type: product?.capacity_type || inferCapacityType(standardCapacity),
  };
}

function areaName(areaId) {
  const area = state.teaching_areas.find((item) => item.id === areaId);
  if (!area) return areaId || "";
  return areaShortName(area) || areaId || "";
}

function roomName(roomId) {
  const room = state.rooms.find((item) => item.id === roomId);
  if (!room) return roomId || "";
  const areaLabel = room.teaching_area_name || areaName(room.teaching_area_id);
  return `${room.name || room.id}${areaLabel ? ` / ${areaLabel}` : ""}`;
}

function courseLabel(course) {
  return [course.subject, course.window_name || course.quarter, course.stage, course.course_module, course.course_group].filter(Boolean).join(" / ");
}

function teacherCourseLabel(assignment) {
  return [assignment.subject, assignment.stage, assignment.course_group].filter(Boolean).join(" / ");
}

function compareTeacherAssignmentRows(a, b) {
  const left = a.assignment || {};
  const right = b.assignment || {};
  const leftStage = String(left.stage || "");
  const rightStage = String(right.stage || "");
  const leftKnownStage = stageSortParts(leftStage).rank !== Number.POSITIVE_INFINITY;
  const rightKnownStage = stageSortParts(rightStage).rank !== Number.POSITIVE_INFINITY;
  if (leftKnownStage || rightKnownStage) {
    if (leftKnownStage !== rightKnownStage) return leftKnownStage ? -1 : 1;
    return compareStageValues(leftStage, rightStage)
      || String(left.subject || "").localeCompare(String(right.subject || ""), "zh-CN")
      || String(left.course_group || "").localeCompare(String(right.course_group || ""), "zh-CN");
  }
  return compareSeasonWindowValues(leftStage, rightStage)
    || String(left.subject || "").localeCompare(String(right.subject || ""), "zh-CN")
    || String(left.course_group || "").localeCompare(String(right.course_group || ""), "zh-CN");
}

function teacherAssignmentKey(item, productId = "") {
  return [item.product_id || productId || "", item.subject || "", item.stage || "", item.course_group || ""].join("||");
}

function teacherAssignmentKeyParts(item, productId = "") {
  return {
    product_id: item.product_id || productId || "",
    subject: item.subject || "",
    stage: item.stage || "",
    course_group: item.course_group || "",
  };
}

function teacherAssignmentKeyFromParts(productId, subject, stage, courseGroup) {
  return [productId || "", subject || "", stage || "", courseGroup || ""].join("||");
}

function stageRankForCourses(courses) {
  const ranks = new Map();
  for (const stage of sortStageValues(courses.map((course) => course.stage))) {
    if (!ranks.has(stage)) ranks.set(stage, ranks.size);
  }
  return ranks;
}

function chooseCurrentTeacherAssignment(current, key, assignment) {
  if (!current.has(key) || !assignment.course_module) current.set(key, assignment);
}

function resolveSyncedTeacherAssignment(course, productId, current, courses) {
  const parts = teacherAssignmentKeyParts(course, productId);
  const candidates = [
    teacherAssignmentKeyFromParts(parts.product_id, parts.subject, parts.stage, parts.course_group),
    teacherAssignmentKeyFromParts("", parts.subject, parts.stage, parts.course_group),
    teacherAssignmentKeyFromParts(parts.product_id, "", parts.stage, parts.course_group),
    teacherAssignmentKeyFromParts("", "", parts.stage, parts.course_group),
  ];
  for (const candidate of candidates) {
    if (current.has(candidate)) return current.get(candidate);
  }

  const ranks = stageRankForCourses(courses);
  const currentRank = ranks.has(parts.stage) ? ranks.get(parts.stage) : 10000;
  const fallback = [];
  for (const [candidateKey, assignment] of current.entries()) {
    const [candidateProduct, candidateSubject, candidateStage, candidateGroup] = candidateKey.split("||");
    if (candidateGroup !== parts.course_group) continue;
    if (candidateProduct && candidateProduct !== parts.product_id) continue;
    if (candidateSubject && candidateSubject !== parts.subject) continue;
    if (!candidateStage || candidateStage === parts.stage) continue;
    const candidateRank = ranks.has(candidateStage) ? ranks.get(candidateStage) : 10000;
    if (candidateRank >= currentRank) continue;
    fallback.push([candidateRank, assignment]);
  }
  fallback.sort((left, right) => left[0] - right[0]);
  return fallback[0]?.[1] || {};
}

function resolveExactTeacherAssignment(course, productId, current) {
  const parts = teacherAssignmentKeyParts(course, productId);
  const candidates = [
    teacherAssignmentKeyFromParts(parts.product_id, parts.subject, parts.stage, parts.course_group),
    teacherAssignmentKeyFromParts("", parts.subject, parts.stage, parts.course_group),
    teacherAssignmentKeyFromParts(parts.product_id, "", parts.stage, parts.course_group),
    teacherAssignmentKeyFromParts("", "", parts.stage, parts.course_group),
  ];
  for (const candidate of candidates) {
    if (current.has(candidate)) return current.get(candidate);
  }
  return {};
}

function selectOptions(items, selectedValue = "", placeholder = "请选择") {
  const options = [`<option value="">${html(placeholder)}</option>`];
  for (const item of items) {
    const value = typeof item === "string" ? item : item.id;
    const label = typeof item === "string" ? item : item.label || `${item.name || item.id} (${item.id})`;
    options.push(`<option value="${html(value)}" ${value === selectedValue ? "selected" : ""}>${html(label)}</option>`);
  }
  return options.join("");
}

function selectLabeledOptions(items, selectedValue = "", placeholder = "请选择") {
  const options = [`<option value="">${html(placeholder)}</option>`];
  for (const item of items) {
    options.push(`<option value="${html(item.value)}" ${item.value === selectedValue ? "selected" : ""}>${html(item.label)}</option>`);
  }
  return options.join("");
}

function multiOptions(items, selectedValues = []) {
  const selectedSet = new Set(arrayValues(selectedValues));
  return items
    .map((item) => {
      const value = typeof item === "string" ? item : item.id;
      const label = typeof item === "string" ? item : `${item.name || item.id} (${item.id})`;
      return `<option value="${html(value)}" ${selectedSet.has(value) ? "selected" : ""}>${html(label)}</option>`;
    })
    .join("");
}

function arrayValues(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (typeof value === "string") return value.split("|").map((item) => item.trim()).filter(Boolean);
  return [];
}

function uniqueList(values) {
  return [...new Set(arrayValues(values))];
}

function listText(value) {
  return arrayValues(value).join("|");
}

function normalizeScheduleMode(value, inheritFromClassId = "", actualScheduledClassId = "", classId = "") {
  const text = String(value || "").trim();
  const compact = text.replaceAll(" ", "").toLowerCase();
  const inheritedClass = String(inheritFromClassId || "").trim();
  const actualClass = String(actualScheduledClassId || "").trim();
  const currentClassId = String(classId || "").trim();
  if (text.includes("合班") || text.includes("主班")) return "合班主班";
  if (text.includes("本班") || text.includes("独立")) return "独立排课";
  if (currentClassId) {
    if (actualClass && actualClass !== currentClassId) return "共享课表";
    if (actualClass === currentClassId) return "独立排课";
    if (inheritedClass && inheritedClass !== currentClassId) return "共享课表";
    if (inheritedClass === currentClassId) return "独立排课";
  }
  if (compact === "shared" || compact === "inherit" || compact === "inherited" || text.includes("共享") || text.includes("继承")) return "共享课表";
  if (inheritedClass) return "共享课表";
  if (actualClass && currentClassId && actualClass !== currentClassId) return "共享课表";
  return text || "独立排课";
}

function assignmentScheduleModeValue(assignment) {
  if (String(assignment.class_schedule_mode || "").trim() || String(assignment.actual_scheduled_class_id || "").trim()) {
    return assignment.class_schedule_mode || "";
  }
  return assignment.schedule_mode || assignment.assignment_mode || "";
}

function assignmentScheduleMode(assignment, cls = currentClass()) {
  return normalizeScheduleMode(
    assignmentScheduleModeValue(assignment),
    assignment.inherit_from_class_id,
    assignment.actual_scheduled_class_id,
    cls?.id || assignment.class_id || "",
  );
}

function assignmentReferenceClassId(assignment, cls = currentClass()) {
  const mode = assignmentScheduleMode(assignment, cls);
  return mode === "共享课表" ? (assignment.actual_scheduled_class_id || assignment.inherit_from_class_id || "") : "";
}

function scheduleModeDisplayName(mode) {
  if (mode === "共享课表") return "共享实际排课班级";
  if (mode === "合班主班") return "合班实际排课班级";
  return "本班实际排课";
}

function teacherAssignmentIsShared(assignment) {
  return assignmentScheduleMode(assignment) === "共享课表";
}

function teacherAssignmentMissingSource(assignment) {
  return teacherAssignmentIsShared(assignment) && !String(assignmentReferenceClassId(assignment) || "").trim();
}

function emptyProductTagFilters() {
  return Object.fromEntries(productTagFilterFields.map(({ field }) => [field, ""]));
}

function checkboxOptions(items, selectedValues = [], actionName) {
  const selectedSet = new Set(arrayValues(selectedValues));
  return items
    .map((item) => {
      const value = typeof item === "string" ? item : item.id;
      const label = typeof item === "string" ? item : `${item.name || item.id} (${item.id})`;
      return `
        <label class="checkbox-option">
          <input type="checkbox" data-action="${html(actionName)}" value="${html(value)}" ${selectedSet.has(value) ? "checked" : ""}>
          <span>${html(label)}</span>
        </label>
      `;
    })
    .join("");
}

function listCheckboxOptions(listName, index, field, items, selectedValues = []) {
  const selectedSet = new Set(arrayValues(selectedValues));
  return `
    <div class="inline-options" role="group">
      ${items
        .map((item) => {
          const value = typeof item === "string" ? item : item.id;
          const label = typeof item === "string" ? item : item.name || item.id;
          return `
            <label>
              <input type="checkbox" data-list-checkbox="true" data-list="${html(listName)}" data-index="${index}" data-field="${html(field)}" value="${html(value)}" ${selectedSet.has(value) ? "checked" : ""}>
              <span>${html(label)}</span>
            </label>
          `;
        })
        .join("")}
    </div>
  `;
}

function entityCheckboxOptions(entityName, id, field, items, selectedValues = []) {
  const selectedSet = new Set(arrayValues(selectedValues));
  return `
    <div class="inline-options" role="group">
      ${items
        .map((item) => {
          const value = typeof item === "string" ? item : item.id;
          const label = typeof item === "string" ? item : item.name || item.id;
          return `
            <label>
              <input type="checkbox" data-entity-checkbox="true" data-entity="${html(entityName)}" data-id="${html(id)}" data-field="${html(field)}" value="${html(value)}" ${selectedSet.has(value) ? "checked" : ""}>
              <span>${html(label)}</span>
            </label>
          `;
        })
        .join("")}
    </div>
  `;
}

function selectedOptions(select) {
  return [...select.selectedOptions].map((option) => option.value).filter(Boolean);
}

function stageSortParts(value) {
  const text = String(value || "").trim();
  const numbered = text.match(/^(导学|专项)(\d+)$/);
  const base = numbered ? numbered[1] : text;
  return {
    rank: stageOrderIndex.has(base) ? stageOrderIndex.get(base) : Number.POSITIVE_INFINITY,
    subRank: numbered ? Number(numbered[2]) : 0,
    text,
  };
}

function compareStageValues(a, b) {
  const left = stageSortParts(a);
  const right = stageSortParts(b);
  if (left.rank !== right.rank) return left.rank - right.rank;
  if (left.subRank !== right.subRank) return left.subRank - right.subRank;
  return left.text.localeCompare(right.text, "zh-CN");
}

function sortStageValues(values) {
  return [...values].filter(Boolean).sort(compareStageValues);
}

function seasonWindowSortParts(value) {
  const text = String(value || "").trim();
  const year = Number(text.match(/(\d{4})/)?.[1] || 0);
  const season = seasonWindowOrder.find((name) => text.includes(name)) || "";
  return {
    year,
    rank: season ? seasonWindowOrderIndex.get(season) : Number.POSITIVE_INFINITY,
    text,
  };
}

function compareSeasonWindowValues(a, b) {
  const left = seasonWindowSortParts(a);
  const right = seasonWindowSortParts(b);
  if (left.year !== right.year) return left.year - right.year;
  if (left.rank !== right.rank) return left.rank - right.rank;
  return left.text.localeCompare(right.text, "zh-CN");
}

function compareProductCourseRows(a, b) {
  const left = a.course || {};
  const right = b.course || {};
  const leftWindow = left.window_name || left.quarter || "";
  const rightWindow = right.window_name || right.quarter || "";
  return compareSeasonWindowValues(leftWindow, rightWindow)
    || compareStageValues(left.stage, right.stage)
    || Number(left.stage_priority || 0) - Number(right.stage_priority || 0)
    || String(left.course_group || "").localeCompare(String(right.course_group || ""), "zh-CN")
    || Number(left.module_priority_in_group || left.module_priority || 0) - Number(right.module_priority_in_group || right.module_priority || 0)
    || String(left.course_module || "").localeCompare(String(right.course_module || ""), "zh-CN")
    || String(left.course_name || "").localeCompare(String(right.course_name || ""), "zh-CN");
}

function setByIndex(listName, index, field, value) {
  state[listName][Number(index)][field] = value;
}

function setClassField(classId, field, value) {
  const cls = state.classes.find((item) => item.id === classId);
  if (cls) cls[field] = value;
}

function currentClass() {
  return state.classes.find((item) => item.id === selected.classId) || state.classes[0] || null;
}

function currentArea() {
  return state.teaching_areas.find((item) => item.id === selected.areaId) || state.teaching_areas[0] || null;
}

function productCourses(productId) {
  return state.product_courses
    .map((course, index) => ({ course, index }))
    .filter(({ course }) => course.product_id === productId)
    .sort(compareProductCourseRows);
}

function productCourseSummary(productId) {
  const rows = productCourses(productId);
  return {
    count: rows.length,
    hours: rows.reduce((sum, { course }) => sum + Number(course.total_hours || 0), 0),
  };
}

function productSubjects(productId) {
  const rows = productId ? productCourses(productId) : state.product_courses.map((course, index) => ({ course, index }));
  return [...new Set(rows.map(({ course }) => course.subject).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
}

function productStages(productId, subject = "") {
  return [
    ...new Set(
      productCourses(productId)
        .filter(({ course }) => !subject || course.subject === subject)
        .map(({ course }) => course.stage)
        .filter(Boolean),
    ),
  ].sort(compareStageValues);
}

function classStageOptions(cls) {
  return productStages(cls.product_id, cls.subject);
}

function pruneClassStages(cls, defaultAll = false) {
  const allowedValues = classStageOptions(cls);
  const allowed = new Set(allowedValues);
  const selectedStages = new Set(arrayValues(cls.stages));
  cls.stages = allowedValues.filter((stage) => allowed.has(stage) && selectedStages.has(stage));
  if (defaultAll && allowedValues.length && !cls.stages.length) cls.stages = [...allowedValues];
  cls.selected_stages = [...cls.stages];
}

function classStageCheckboxOptions(cls) {
  const stages = classStageOptions(cls);
  if (!stages.length) return `<span class="muted">该产品暂无阶段</span>`;
  return `<div class="class-stage-options">${entityCheckboxOptions("class", cls.id, "stages", stages, cls.stages)}</div>`;
}

function applyClassProduct(cls, productId) {
  cls.product_id = productId;
  const subjects = productSubjects(cls.product_id);
  if (cls.subject && !subjects.includes(cls.subject)) cls.subject = subjects[0] || "";
  applyClassAutoTags(cls, true);
  pruneClassStages(cls, true);
  syncClassTeachers(cls);
}

function addClassTeachingArea(cls, areaId) {
  cls.preferred_teaching_area_ids = uniqueList([...arrayValues(cls.preferred_teaching_area_ids), areaId]);
  pruneClassRoomSelection(cls);
}

function removeClassTeachingArea(cls, areaId) {
  cls.preferred_teaching_area_ids = arrayValues(cls.preferred_teaching_area_ids).filter((id) => id !== areaId);
  pruneClassRoomSelection(cls);
}

function addClassRoom(cls, roomId) {
  cls.preferred_room_ids = uniqueList([...arrayValues(cls.preferred_room_ids), roomId]);
}

function removeClassRoom(cls, roomId) {
  cls.preferred_room_ids = arrayValues(cls.preferred_room_ids).filter((id) => id !== roomId);
}

function addClassWindowTeachingArea(item, areaId) {
  item.preferred_teaching_area_ids = uniqueList([...arrayValues(item.preferred_teaching_area_ids), areaId]);
  pruneClassWindowRoomSelection(item);
}

function removeClassWindowTeachingArea(item, areaId) {
  item.preferred_teaching_area_ids = arrayValues(item.preferred_teaching_area_ids).filter((id) => id !== areaId);
  pruneClassWindowRoomSelection(item);
}

function addClassWindowRoom(item, roomId) {
  item.preferred_room_ids = uniqueList([...arrayValues(item.preferred_room_ids), roomId]);
}

function removeClassWindowRoom(item, roomId) {
  item.preferred_room_ids = arrayValues(item.preferred_room_ids).filter((id) => id !== roomId);
}

function applyClassAutoTags(cls, force = false) {
  const tags = autoClassTags(cls);
  for (const field of ["project", "product_line", "sub_product", "capacity_type", "subject"]) {
    if (force || !cls[field]) cls[field] = tags[field];
  }
  for (const field of ["product_system", "course_nature", "subject_category"]) {
    if (force || !cls[field]) cls[field] = tags[field] || cls[field] || "";
  }
  if (force || !Number(cls.standard_capacity || 0)) cls.standard_capacity = tags.standard_capacity || 0;
  cls.capacity_type = tags.capacity_type || inferCapacityType(cls.standard_capacity);
  if (!cls.suite_code) cls.suite_code = inferSuiteCodeFromClassName(cls.name);
}

function applyProductAutoTags(productId, force = false) {
  const product = productById(productId);
  if (!product) return;
  const tags = autoProductTags(product);
  const row = state.products.find((item) => item.id === productId);
  if (!row) return;
  for (const field of ["project", "product_line", "sub_product"]) {
    if (force || !row[field]) row[field] = tags[field];
  }
  row.capacity_type = inferCapacityType(row.standard_capacity);
}

function classProductCourses(cls) {
  const stageOptions = classStageOptions(cls);
  const selectedStages = new Set(arrayValues(cls.stages));
  return productCourses(cls.product_id).filter(({ course }) => {
    if (cls.subject && course.subject !== cls.subject) return false;
    if (stageOptions.length && !selectedStages.has(course.stage)) return false;
    return true;
  });
}

function classRoomOptions(cls) {
  const areaIds = new Set(arrayValues(cls.preferred_teaching_area_ids));
  const rooms = areaIds.size
    ? state.rooms.filter((room) => areaIds.has(room.teaching_area_id))
    : state.rooms;
  return rooms.map((room) => ({ id: room.id, name: roomName(room.id) }));
}

function classWindowRoomOptions(item) {
  const areaIds = new Set(arrayValues(item.preferred_teaching_area_ids));
  const rooms = areaIds.size
    ? state.rooms.filter((room) => areaIds.has(room.teaching_area_id))
    : state.rooms;
  return rooms.map((room) => ({ id: room.id, name: roomName(room.id) }));
}

function pruneClassRoomSelection(cls) {
  const allowed = new Set(classRoomOptions(cls).map((room) => room.id));
  cls.preferred_room_ids = arrayValues(cls.preferred_room_ids).filter((roomId) => allowed.has(roomId));
}

function pruneClassWindowRoomSelection(item) {
  const areaIds = new Set(arrayValues(item.preferred_teaching_area_ids));
  if (!areaIds.size) return;
  item.preferred_room_ids = arrayValues(item.preferred_room_ids).filter((roomId) => {
    const room = state.rooms.find((candidate) => candidate.id === roomId);
    return room && areaIds.has(room.teaching_area_id);
  });
}

function emptyCourseFilters() {
  return {
    keyword: "",
    quarter: "",
    stage: "",
    course_module: "",
    course_name: "",
    course_group: "",
  };
}

function courseFilterFields() {
  return ["quarter", "stage", "course_module", "course_name", "course_group"];
}

function uniqueCourseValues(rows, field) {
  const values = [
    ...new Set(
      rows
        .map(({ course }) => (field === "quarter" ? course.window_name || course.quarter : course[field]))
        .filter(Boolean),
    ),
  ];
  if (field === "stage") return sortStageValues(values);
  if (field === "quarter") return values.sort(compareSeasonWindowValues);
  return values.sort((a, b) => String(a).localeCompare(String(b), "zh-CN"));
}

function courseNameTagOptions() {
  const options = [...(state.lookups?.course_name_tags || [])];
  const seen = new Set(options.map((tag) => tag.course_code || `${tag.course_name}|${tag.subject}|${tag.course_module}`));
  for (const course of state.product_courses || []) {
    const courseCode = course.course_code || "";
    const courseName = course.course_name || "";
    if (!courseCode && !courseName) continue;
    const key = courseCode || `${courseName}|${course.subject}|${course.course_module}`;
    if (seen.has(key)) continue;
    seen.add(key);
    options.push({
      course_code: courseCode,
      course_name: courseName,
      subject: course.subject || "",
      stage: course.stage || "",
      course_module: course.course_module || "",
      course_group: course.course_group || "",
      status: "产品课程当前使用",
    });
  }
  return options.sort((a, b) => courseNameTagLabel(a).localeCompare(courseNameTagLabel(b), "zh-CN"));
}

function courseNameTagLabel(tag) {
  const extra = [tag.course_code, tag.subject, tag.course_module, tag.stage].filter(Boolean).join(" / ");
  return `${tag.course_name || tag.course_code}${extra ? `（${extra}）` : ""}`;
}

function courseNameTagFromPickerValue(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  return courseNameTagOptions().find((tag) =>
    text === tag.course_code ||
    text === tag.course_name ||
    text === courseNameTagLabel(tag)
  ) || null;
}

function normalizeCourseFilters(rows) {
  for (const field of courseFilterFields()) {
    const values = new Set(uniqueCourseValues(rows, field));
    if (selected.courseFilters[field] && !values.has(selected.courseFilters[field])) {
      selected.courseFilters[field] = "";
    }
  }
}

function courseMatchesFilters(course) {
  const filters = selected.courseFilters;
  for (const field of courseFilterFields()) {
    const value = field === "quarter" ? course.window_name || course.quarter : course[field];
    if (filters[field] && value !== filters[field]) return false;
  }
  const keyword = filters.keyword.trim().toLowerCase();
  if (!keyword) return true;
  return [
    course.product_id,
    course.product_name,
    course.project,
    course.product_line,
    course.sub_product,
    course.product_system,
    course.course_nature,
    course.exam_season,
    course.capacity_type,
    course.subject_category,
    course.subject,
    course.window_name || course.quarter,
    course.stage,
    course.stage_priority,
    course.course_group,
    course.course_module,
    course.module_priority,
    course.course_code,
    course.course_name,
    course.total_hours,
    course.notes,
  ]
    .filter((value) => value !== undefined && value !== null)
    .join(" ")
    .toLowerCase()
    .includes(keyword);
}

function applyProductCourseFilters() {
  const rows = [...content.querySelectorAll("[data-course-row]")];
  let visibleCount = 0;
  for (const row of rows) {
    const course = state.product_courses[Number(row.dataset.courseIndex)];
    const visible = course ? courseMatchesFilters(course) : false;
    row.hidden = !visible;
    if (visible) visibleCount += 1;
  }
  const count = content.querySelector("[data-course-filter-count]");
  if (count) count.textContent = `显示 ${visibleCount} / ${rows.length} 门课程`;
}

function courseFilterControls(rows) {
  return `
    <div class="filter-bar">
      <label><span>关键词</span><input data-action="course-filter" data-field="keyword" value="${html(selected.courseFilters.keyword)}" placeholder="窗口期 / 阶段 / 模块 / 分组 / 课程"></label>
      <label><span>排课窗口期</span><select data-action="course-filter" data-field="quarter">${selectOptions(uniqueCourseValues(rows, "quarter"), selected.courseFilters.quarter, "全部窗口期")}</select></label>
      <label><span>阶段</span><select data-action="course-filter" data-field="stage">${selectOptions(uniqueCourseValues(rows, "stage"), selected.courseFilters.stage, "全部阶段")}</select></label>
      <label><span>模块</span><select data-action="course-filter" data-field="course_module">${selectOptions(uniqueCourseValues(rows, "course_module"), selected.courseFilters.course_module, "全部模块")}</select></label>
      <label><span>课程名称</span><select data-action="course-filter" data-field="course_name">${selectOptions(uniqueCourseValues(rows, "course_name"), selected.courseFilters.course_name, "全部课程名称")}</select></label>
      <label><span>课程分组</span><select data-action="course-filter" data-field="course_group">${selectOptions(uniqueCourseValues(rows, "course_group"), selected.courseFilters.course_group, "全部分组")}</select></label>
      <div class="filter-actions">
        <span data-course-filter-count>显示 ${rows.length} / ${rows.length} 门课程</span>
        <button type="button" class="small" data-action="clear-course-filters">清空筛选</button>
      </div>
    </div>
  `;
}

function setProductField(productId, field, value) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) return;
  product[field] = value;
  if (field === "project") {
    product.product_line = inferProductLine(product.name, "", value);
    product.sub_product = inferSubProduct(product.product_line, product.name);
  }
  if (field === "product_line") {
    product.sub_product = inferSubProduct(value, product.name);
  }
  if (field === "standard_capacity") {
    product.capacity_type = inferCapacityType(value);
  }
}

function syncProductName(productId, name) {
  const product = state.products.find((item) => item.id === productId);
  if (product) product.name = name;
  for (const { course } of productCourses(productId)) course.product_name = name;
}

function syncProductId(oldId, newId) {
  const product = state.products.find((item) => item.id === oldId);
  if (product) product.id = newId;
  for (const course of state.product_courses) {
    if (course.product_id === oldId) course.product_id = newId;
  }
  for (const rule of state.product_schedule_rules) {
    if (rule.product_id === oldId) rule.product_id = newId;
    rule.product_ids = arrayValues(rule.product_ids).map((id) => (id === oldId ? newId : id));
  }
  for (const cls of state.classes) {
    if (cls.product_id === oldId) cls.product_id = newId;
  }
}

function deleteProductAtIndex(index) {
  const product = state.products[index];
  if (!product) return;
  const courseCount = productCourses(product.id).length;
  const linkedClasses = state.classes.filter((cls) => cls.product_id === product.id);
  const title = `${product.name || product.id}（${product.id}）`;
  const message = courseCount || linkedClasses.length
    ? `确认删除 ${title} 吗？\n\n该产品当前关联 ${courseCount} 门课程、${linkedClasses.length} 个班级。\n确认后会同时删除该产品下的课程，并清空关联班级的所属产品和产品继承标签。`
    : `确认删除 ${title} 吗？`;

  if (!confirm(message)) {
    showStatus("已取消删除产品。", "warning");
    return;
  }

  state.products.splice(index, 1);
  state.product_courses = state.product_courses.filter((course) => course.product_id !== product.id);
  for (const rule of state.product_schedule_rules || []) {
    if (rule.product_id === product.id) {
      rule.product_id = "";
      rule.product_name = "";
    }
    rule.product_ids = arrayValues(rule.product_ids).filter((id) => id !== product.id);
  }
  for (const cls of linkedClasses) {
    cls.product_id = "";
    cls.project = "";
    cls.product_line = "";
    cls.sub_product = "";
    cls.product_system = "";
    cls.course_nature = "";
    cls.subject_category = "";
    cls.stages = [];
    cls.standard_capacity = 0;
    cls.capacity_type = "";
  }
  if (selected.productId === product.id) selected.productId = products()[0]?.id || "";
  showStatus(`已删除产品 ${title}。`, "ok");
}

function deleteClassById(classId) {
  const index = state.classes.findIndex((cls) => cls.id === classId);
  const cls = state.classes[index];
  if (!cls) return;
  const assignmentCount = cls.teacher_assignments?.length || 0;
  const title = `${cls.name || cls.id}（${cls.id}）`;
  const message = assignmentCount
    ? `确认删除 ${title} 吗？\n\n该班级当前有 ${assignmentCount} 条老师安排，删除班级会一起删除这些安排。`
    : `确认删除 ${title} 吗？`;

  if (!confirm(message)) {
    showStatus("已取消删除班级。", "warning");
    return;
  }

  state.classes.splice(index, 1);
  if (selected.classId === classId) selected.classId = state.classes[0]?.id || "";
  showStatus(`已删除班级 ${title}。`, "ok");
}

function checkedValues(actionName) {
  return [...content.querySelectorAll(`input[data-action="${actionName}"]:checked`)].map((item) => item.value);
}

function workflowTabFor(tab) {
  if (tab === "overview") return "overview";
  if (tab === "timeData") return "timeData";
  if (["rooms", "areaLinks", "teachers", "teacherUnavailable"].includes(tab)) return "rooms";
  if (["productMeta", "businessMappings", "products"].includes(tab)) return "productMeta";
  if (["classMeta", "classWindows", "classes", "classConflicts"].includes(tab)) return "classMeta";
  if (["rules", "lockedLessons"].includes(tab)) return "rules";
  if (tab === "launch") return "launch";
  if (["batchSchedules", "publish"].includes(tab)) return "launch";
  return tab;
}

function resetPageScroll() {
  const scroller = document.scrollingElement || document.documentElement;
  scroller.scrollTop = 0;
  scroller.scrollLeft = 0;
  window.scrollTo(0, 0);
}

function switchTab(tab) {
  if (!tabs[tab]) return;
  activeTab = tab;
  render();
  resetPageScroll();
}

function render() {
  if (!state) return;
  const activeWorkflowTab = workflowTabFor(activeTab);
  document.querySelectorAll("[data-tab]").forEach((button) => {
    const activeTarget = button.closest(".workflow-rail") ? activeWorkflowTab : activeTab;
    button.classList.toggle("active", button.dataset.tab === activeTarget);
  });
  pageTitle.textContent = tabs[activeTab][0];
  pageSubtitle.textContent = tabs[activeTab][1];
  if (activeTab === "overview") renderOverview();
  if (activeTab === "timeData") renderTimeData();
  if (activeTab === "rooms") renderRooms();
  if (activeTab === "teachers") renderTeachers();
  if (activeTab === "teacherUnavailable") renderTeacherUnavailable();
  if (activeTab === "productMeta") renderProductMeta();
  if (activeTab === "products") renderProducts();
  if (activeTab === "rules") renderRules();
  if (activeTab === "classMeta") renderClassMeta();
  if (activeTab === "classWindows") renderClassWindows();
  if (activeTab === "classes") renderClasses();
  if (activeTab === "classConflicts") renderClassConflicts();
  if (activeTab === "lockedLessons") renderLockedLessons();
  if (activeTab === "areaLinks") renderAreaLinks();
  if (activeTab === "businessMappings") renderBusinessMappings();
  if (activeTab === "batchSchedules") renderBatchSchedules();
  if (activeTab === "launch") renderLaunch();
  if (activeTab === "publish") renderPublish();
}

function captureClassMetaPosition() {
  const tableWrap = content.querySelector(".class-meta-table");
  const pageScroller = document.scrollingElement || document.documentElement;
  return {
    pageTop: pageScroller.scrollTop,
    pageLeft: pageScroller.scrollLeft,
    tableTop: tableWrap?.scrollTop || 0,
    tableLeft: tableWrap?.scrollLeft || 0,
  };
}

function restoreClassMetaPosition(position) {
  if (!position) return;
  const tableWrap = content.querySelector(".class-meta-table");
  const pageScroller = document.scrollingElement || document.documentElement;
  if (tableWrap) {
    tableWrap.scrollTop = position.tableTop;
    tableWrap.scrollLeft = position.tableLeft;
  }
  pageScroller.scrollTop = position.pageTop;
  pageScroller.scrollLeft = position.pageLeft;
}

function renderClassMetaPreservingPosition() {
  const position = captureClassMetaPosition();
  renderClassMeta();
  restoreClassMetaPosition(position);
  requestAnimationFrame(() => restoreClassMetaPosition(position));
}

function renderActiveClassView(options = {}) {
  if (activeTab === "classMeta") {
    if (options.preservePosition) {
      renderClassMetaPreservingPosition();
    } else {
      renderClassMeta();
    }
  } else {
    renderClasses();
  }
}

function section(title, subtitle, body, actions = "") {
  const hasHeader = title || subtitle || actions;
  return `
    <section class="section">
      ${
        hasHeader
          ? `<div class="section-header">
              <div>
                ${title ? `<h2>${html(title)}</h2>` : ""}
                ${subtitle ? `<p>${html(subtitle)}</p>` : ""}
              </div>
              <div>${actions}</div>
            </div>`
          : ""
      }
      <div class="section-body">${body}</div>
    </section>
  `;
}

function displayValue(value) {
  if (Array.isArray(value)) return value.join("|");
  if (typeof value === "boolean") return value ? "是" : "否";
  if (value === null || value === undefined) return "";
  return String(value);
}

function compactCell(value) {
  const text = displayValue(value);
  return `<span title="${html(text)}">${html(text)}</span>`;
}

function rowSearchText(row) {
  return Object.values(row || {})
    .map(displayValue)
    .join(" ")
    .toLowerCase();
}

function filteredRows(rows, keyword) {
  const text = String(keyword || "").trim().toLowerCase();
  if (!text) return rows;
  const tokens = text.split(/\s+/).filter(Boolean);
  return rows.filter((row) => tokens.every((token) => rowSearchText(row).includes(token)));
}

function limitDisplayedRows(rows, limit) {
  return rows.length > limit ? rows.slice(0, limit) : rows;
}

function displayLimitNote(itemLabel, visibleCount, matchedCount, totalCount = matchedCount) {
  const totalText = totalCount === matchedCount ? "" : `，全量 ${totalCount} 条`;
  if (visibleCount < matchedCount) {
    return `当前渲染前 ${visibleCount} / ${matchedCount} 条${itemLabel}${totalText}；继续搜索或筛选可定位更多记录。`;
  }
  return `当前显示 ${visibleCount} / ${matchedCount} 条${itemLabel}${totalText}。`;
}

function dataPreviewTable(rows, columns, options = {}) {
  const limit = options.limit || 200;
  const visibleRows = rows.slice(0, limit);
  if (!visibleRows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  const columnGroups = options.columnGroups || [];
  const columnMeta = tableColumnMeta(columns.length, columnGroups);
  const tableClasses = [
    options.className || "data-preview-table",
    columnGroups.length ? "segmented-table preview-segmented-table" : "",
  ].filter(Boolean).join(" ");
  return `
    <div class="table-wrap ${html(tableClasses)}">
      <table>
        ${colgroupHtml(options.colWidths)}
        <thead>
          ${columnGroupRow(columnGroups)}
          <tr>${columns.map((column, columnIndex) => `<th class="${html(columnMeta[columnIndex])}">${html(column.label)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${visibleRows
            .map(
              (row) => `
                <tr>
                  ${columns
                    .map((column, columnIndex) => {
                      const value = column.format ? column.format(row) : row[column.field];
                      return `<td class="${html(columnMeta[columnIndex])}">${compactCell(value)}</td>`;
                    })
                    .join("")}
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
    ${
      rows.length > visibleRows.length
        ? `<div class="table-note">已显示前 ${visibleRows.length} 条，继续缩小搜索条件可定位更多记录。</div>`
        : ""
    }
  `;
}

function colgroupHtml(widths = []) {
  if (!widths?.length) return "";
  return `<colgroup>${widths.map((width) => `<col style="width: ${html(width)}">`).join("")}</colgroup>`;
}

function columnGroupRow(groups = []) {
  if (!groups?.length) return "";
  return `
    <tr class="column-group-row">
      ${groups.map((group) => `<th colspan="${Number(group.span || 1)}">${html(group.label)}</th>`).join("")}
    </tr>
  `;
}

function tableColumnMeta(columnCount, groups = []) {
  const classes = Array.from({ length: columnCount }, () => "");
  if (!groups?.length) return classes;
  let columnIndex = 0;
  groups.forEach((group, groupIndex) => {
    const span = Number(group.span || 1);
    for (let offset = 0; offset < span && columnIndex < columnCount; offset += 1) {
      classes[columnIndex] = `group-${(groupIndex % 6) + 1}${offset === span - 1 ? " group-end" : ""}`;
      columnIndex += 1;
    }
  });
  return classes;
}

function editableTextCell(listName, index, field, value, placeholder = "") {
  return `<input data-list="${html(listName)}" data-index="${index}" data-field="${html(field)}" value="${html(displayValue(value))}" placeholder="${html(placeholder)}">`;
}

function editableNumberCell(listName, index, field, value) {
  return `<input type="number" data-list="${html(listName)}" data-index="${index}" data-field="${html(field)}" value="${html(value || "")}">`;
}

function editableDateCell(listName, index, field, value) {
  return `<input type="date" data-list="${html(listName)}" data-index="${index}" data-field="${html(field)}" value="${html(value || "")}">`;
}

function editableCheckboxCell(listName, index, field, value, label = "启用") {
  return `<label class="inline-check"><input type="checkbox" data-list="${html(listName)}" data-index="${index}" data-field="${html(field)}" ${value ? "checked" : ""}>${html(label)}</label>`;
}

const defaultLessonTemplates = [
  { period: "AM", suffix: "1", name: "上午一", order: 1, start_time: "08:00", end_time: "10:00" },
  { period: "AM", suffix: "2", name: "上午二", order: 2, start_time: "10:20", end_time: "12:20" },
  { period: "PM", suffix: "1", name: "下午一", order: 1, start_time: "14:00", end_time: "16:00" },
  { period: "PM", suffix: "2", name: "下午二", order: 2, start_time: "16:20", end_time: "18:20" },
  { period: "EVENING", suffix: "1", name: "晚上", order: 1, start_time: "19:00", end_time: "21:00" },
];

const seasonWindowDefaults = {
  寒假: { season_window_id: "WINDOW_WINTER", startMonth: 1, endMonth: 2, blockedWeekdays: ["周日"] },
  春季: { season_window_id: "WINDOW_SPRING", startMonth: 3, endMonth: 6, blockedWeekdays: ["周一"] },
  暑假: { season_window_id: "WINDOW_SUMMER", startMonth: 7, endMonth: 8, blockedWeekdays: ["周日"] },
  秋季: { season_window_id: "WINDOW_AUTUMN", startMonth: 9, endMonth: 12, blockedWeekdays: ["周一"] },
};

function pad2(value) {
  return String(value).padStart(2, "0");
}

function parseDateValue(value) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateValue(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function lastDayOfMonth(year, month) {
  return new Date(year, month, 0).getDate();
}

function weekdayNameFromDate(date) {
  return ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][date.getDay()];
}

function dateRangeContains(dateText, startText, endText) {
  if (!dateText || !startText) return false;
  const end = endText || startText;
  return dateText >= startText && dateText <= end;
}

function blackoutReasonsForDate(dateText) {
  return (state.global_blackout_dates || [])
    .filter((item) => item.is_active !== false && dateRangeContains(dateText, item.start_date, item.end_date))
    .map((item) => item.name || item.id || "全局停课")
    .filter(Boolean);
}

function normalizeSeasonName(value) {
  const text = String(value || "").trim();
  return seasonWindowOrder.find((season) => text.includes(season)) || "";
}

function seasonDefaultsForWindow(window) {
  const seasonName = normalizeSeasonName(window.season_name || window.schedule_window_name || window.schedule_window_id);
  return seasonWindowDefaults[seasonName] || {};
}

function scheduleWindowSlotCount(scheduleWindowId) {
  return (state.time_slots || []).filter((slot) => slot.schedule_window_id === scheduleWindowId).length;
}

function nextScheduleWindowDraft() {
  const sorted = (state.schedule_windows || [])
    .slice()
    .sort((a, b) => Number(a.window_order || 0) - Number(b.window_order || 0));
  const last = sorted[sorted.length - 1] || null;
  const currentSeason = normalizeSeasonName(last?.season_name || last?.schedule_window_id) || "寒假";
  const currentIndex = seasonWindowOrder.indexOf(currentSeason);
  const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % seasonWindowOrder.length : 0;
  const seasonName = seasonWindowOrder[nextIndex];
  const year = Number(last?.window_year || new Date().getFullYear()) + (nextIndex === 0 && currentIndex >= 0 ? 1 : 0);
  const defaults = seasonWindowDefaults[seasonName];
  const startDate = `${year}-${pad2(defaults.startMonth)}-01`;
  const endDate = `${year}-${pad2(defaults.endMonth)}-${pad2(lastDayOfMonth(year, defaults.endMonth))}`;
  return {
    schedule_window_id: `${year}${seasonName}`,
    schedule_window_name: `${year}${seasonName}`,
    window_year: year,
    window_order: Number(`${year}${pad2(defaults.startMonth)}`),
    season_window_id: defaults.season_window_id,
    season_name: seasonName,
    start_date: startDate,
    end_date: endDate,
    default_allowed_periods: ["AM", "PM", "EVENING"],
    default_allowed_weekdays: weekdays(),
    is_active: true,
    notes: `${seasonName}排课窗口；课节明细可在本页批量生成`,
  };
}

function addScheduleWindow() {
  state.schedule_windows = state.schedule_windows || [];
  let draft = nextScheduleWindowDraft();
  if (state.schedule_windows.some((item) => item.schedule_window_id === draft.schedule_window_id)) {
    draft = {
      ...draft,
      schedule_window_id: `${draft.schedule_window_id}_${Date.now()}`,
      notes: `${draft.notes}；请核对窗口ID`,
    };
  }
  state.schedule_windows.push(draft);
  selected.timeSlotSearch = draft.schedule_window_id;
  showStatus(`已新增年度窗口：${draft.schedule_window_id}，可点击该行“生成课节”。`, "ok");
  renderTimeData();
}

function buildTimeSlotForWindow(window, date, template) {
  const dateText = formatDateValue(date);
  const weekday = weekdayNameFromDate(date);
  const defaults = seasonDefaultsForWindow(window);
  const allowedWeekdays = arrayValues(window.default_allowed_weekdays);
  const weekdayBlocked = (defaults.blockedWeekdays || []).includes(weekday);
  const notAllowedByWindow = allowedWeekdays.length && !allowedWeekdays.includes(weekday);
  const blackoutReasons = blackoutReasonsForDate(dateText);
  const reasons = [
    weekdayBlocked ? `${window.season_name || "该"}窗口${weekday}默认不可排` : "",
    notAllowedByWindow ? "不在该窗口默认可排星期内" : "",
    ...blackoutReasons,
  ].filter(Boolean);
  const isUsable = reasons.length === 0;
  return {
    id: `${dateText}-${template.period}-${template.suffix}`,
    date: dateText,
    calendar_year: date.getFullYear(),
    schedule_window_id: window.schedule_window_id,
    window_order: Number(window.window_order || 0),
    weekday,
    season_window_id: window.season_window_id || defaults.season_window_id || "",
    season_name: window.season_name || normalizeSeasonName(window.schedule_window_id),
    period: template.period,
    half_day_id: `${dateText}-${template.period}`,
    name: template.name,
    order: template.order,
    start_time: template.start_time,
    end_time: template.end_time,
    duration_hours: 2,
    is_usable: isUsable,
    availability_source: isUsable ? "默认可用" : (blackoutReasons.length ? "全局停课/默认规则" : "默认不可用"),
    unavailable_reason: reasons.join("；"),
    data_source: "后台按年度窗口批量生成",
  };
}

function generateTimeSlotsForWindow(windowIndex) {
  const window = state.schedule_windows?.[Number(windowIndex)];
  if (!window?.schedule_window_id) {
    showStatus("请先选择有效年度窗口。", "warning");
    return { added: 0, skipped: 0 };
  }
  const startDate = parseDateValue(window.start_date);
  const endDate = parseDateValue(window.end_date);
  if (!startDate || !endDate || startDate > endDate) {
    showStatus("窗口日期范围无效，请先核对开始和结束日期。", "error");
    return { added: 0, skipped: 0 };
  }
  state.time_slots = state.time_slots || [];
  const existingIds = new Set(state.time_slots.map((slot) => slot.id).filter(Boolean));
  const allowedPeriods = arrayValues(window.default_allowed_periods);
  const templates = defaultLessonTemplates.filter((template) => !allowedPeriods.length || allowedPeriods.includes(template.period));
  let added = 0;
  let skipped = 0;
  const cursor = new Date(startDate);
  while (cursor <= endDate) {
    for (const template of templates) {
      const slot = buildTimeSlotForWindow(window, cursor, template);
      if (existingIds.has(slot.id)) {
        skipped += 1;
        continue;
      }
      state.time_slots.push(slot);
      existingIds.add(slot.id);
      added += 1;
    }
    cursor.setDate(cursor.getDate() + 1);
  }
  state.time_slots.sort((left, right) => String(left.id).localeCompare(String(right.id), "zh-CN"));
  selected.timeSlotSearch = window.schedule_window_id;
  return { added, skipped, windowId: window.schedule_window_id };
}

function generateTimeSlotsForSingleWindow(windowIndex) {
  const result = generateTimeSlotsForWindow(windowIndex);
  showStatus(`已为 ${result.windowId || "该窗口"} 新增 ${result.added} 条课节明细，跳过 ${result.skipped} 条已存在课节。`, result.added ? "ok" : "warning");
  renderTimeData();
}

function generateTimeSlotsForAllWindows() {
  let added = 0;
  let skipped = 0;
  for (let index = 0; index < (state.schedule_windows || []).length; index += 1) {
    const result = generateTimeSlotsForWindow(index);
    added += result.added;
    skipped += result.skipped;
  }
  selected.timeSlotSearch = "";
  showStatus(`已补齐全部年度窗口课节：新增 ${added} 条，跳过 ${skipped} 条已存在课节。`, added ? "ok" : "warning");
  renderTimeData();
}

function renderTimeData() {
  const windows = state.schedule_windows || [];
  const timeSlots = state.time_slots || [];
  const blackoutRows = state.global_blackout_dates || [];
  const rows = filteredRows(timeSlots, selected.timeSlotSearch);
  const usableCount = timeSlots.filter((slot) => slot.is_usable !== false).length;
  const unusableCount = timeSlots.length - usableCount;
  const activeBlackouts = blackoutRows.filter((item) => item.is_active !== false).length;
  const slotDates = timeSlots.map((slot) => slot.date).filter(Boolean).sort();
  const slotRangeLabel = slotDates.length
    ? `${slotDates[0]} 至 ${slotDates[slotDates.length - 1]} 的课节`
    : "按年度窗口生成的课节";
  const windowStats = [
    ["年度窗口", windows.length, "按年份+季节生成的排课窗口", ""],
    ["课节明细", timeSlots.length, slotRangeLabel, ""],
    ["可用课节", usableCount, "默认可参与排课的课节", ""],
    ["不可用课节", unusableCount, "周一/周日规则、节假日或人工停课", unusableCount ? "warning" : ""],
    ["全局停课", activeBlackouts, "影响所有产品和课节池", activeBlackouts ? "warning" : ""],
  ];
  const slotColumns = [
    { label: "课节ID", field: "id" },
    { label: "日期", field: "date" },
    { label: "周几", field: "weekday" },
    { label: "年度窗口", field: "schedule_window_id" },
    { label: "时段", field: "period" },
    { label: "半天组", field: "half_day_id" },
    { label: "开始", field: "start_time" },
    { label: "结束", field: "end_time" },
    { label: "可用", field: "is_usable" },
    { label: "不可用说明", field: "unavailable_reason" },
  ];

  content.innerHTML = section(
    "",
    "",
    `
      <div class="resource-hero time-data-hero">
        <div>
          <span>GLOBAL TIME</span>
          <h2>先确认年度窗口和课节池</h2>
          <p>产品规则使用季节窗口；班级实际可排范围使用这里的年度窗口和课节明细。</p>
        </div>
        <div class="resource-health ${unusableCount ? "warning" : "ok"}">
          <span>课节状态</span>
          <strong>${html(unusableCount ? `${unusableCount} 个课节不可用` : "课节池可用")}</strong>
          <em>不可用原因会进入后续排课过滤。</em>
        </div>
      </div>
      <div class="resource-stat-grid">
        ${windowStats
          .map(
            ([label, value, note, tone]) => `
              <article class="resource-stat-card ${html(tone)}">
                <span>${html(label)}</span>
                <strong>${html(value)}</strong>
                <em>${html(note)}</em>
              </article>
            `,
          )
          .join("")}
      </div>
      ${section(
        "年度排课窗口",
        "先维护年度窗口，再按窗口批量生成课节明细；重复生成只补缺失课节，不覆盖已有手工修改。",
        `
          <div class="time-window-actions">
            <div>
              <strong>窗口 -> 课节</strong>
              <span>新增窗口后先核对日期、季节和默认时段，再生成课节池。</span>
            </div>
            <div class="button-row">
              <button type="button" data-action="add-schedule-window">新增年度窗口</button>
              <button type="button" data-action="generate-all-time-slots">补齐所有窗口课节</button>
            </div>
          </div>
          ${scheduleWindowTable()}
        `,
      )}
      ${section(
        "全局停课日期",
        "所有产品、班级和老师都不可排的日期填在这里；产品自己的星期、时段限制仍到“产品窗口规则”维护。",
        `
          <div class="form-row">
            <div class="muted">可填写单日，也可填写连续日期范围；后续人工指定某天不可排，也在这里补充原因。</div>
            <button type="button" data-action="add-blackout">新增停课日期</button>
          </div>
          ${blackoutTable()}
        `,
      )}
      ${section(
        "课节明细核对",
        "按日期、窗口、周几、时段或不可用说明搜索；大量明细只预览匹配结果前 200 条。",
        `
          <div class="form-row">
            <label><span>搜索课节</span><input data-action="time-slot-search" value="${html(selected.timeSlotSearch)}" placeholder="日期 / 周几 / 窗口 / 不可用说明"></label>
            <div class="muted">显示 ${rows.length} / ${timeSlots.length} 条匹配课节</div>
          </div>
          ${dataPreviewTable(rows, slotColumns, {
            className: "time-slot-preview-table",
            colWidths: ["170px", "112px", "72px", "132px", "76px", "150px", "78px", "78px", "76px", "320px"],
            columnGroups: [
              { label: "课节", span: 1 },
              { label: "日期窗口", span: 3 },
              { label: "时段", span: 4 },
              { label: "可用状态", span: 2 },
            ],
          })}
        `,
      )}
    `,
  );
}

function scheduleWindowTable() {
  const rows = state.schedule_windows || [];
  if (!rows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap segmented-table schedule-window-table">
      <table>
        ${colgroupHtml(["280px", "190px", "230px", "240px", "310px", "82px", "90px", "280px", "90px"])}
        <thead>
          ${columnGroupRow([
            { label: "窗口", span: 1 },
            { label: "排序", span: 1 },
            { label: "季节与日期", span: 2 },
            { label: "默认规则", span: 1 },
            { label: "状态", span: 2 },
            { label: "备注操作", span: 2 },
          ])}
          <tr><th>窗口</th><th>年份/顺序</th><th>季节窗口</th><th>日期范围</th><th>默认星期/时段</th><th>课节</th><th>启用</th><th>备注</th><th>操作</th></tr>
        </thead>
        <tbody>
          ${rows.map((item, index) => `
            <tr>
              <td>
                <div class="field-line">
                  ${editableTextCell("schedule_windows", index, "schedule_window_id", item.schedule_window_id, "窗口ID")}
                  ${editableTextCell("schedule_windows", index, "schedule_window_name", item.schedule_window_name, "窗口名称")}
                </div>
              </td>
              <td>
                <div class="field-line narrow-fields">
                  ${editableNumberCell("schedule_windows", index, "window_year", item.window_year)}
                  ${editableNumberCell("schedule_windows", index, "window_order", item.window_order)}
                </div>
              </td>
              <td>
                <div class="field-line">
                  ${editableTextCell("schedule_windows", index, "season_window_id", item.season_window_id)}
                  ${editableTextCell("schedule_windows", index, "season_name", item.season_name)}
                </div>
              </td>
              <td>
                <div class="field-line">
                  ${editableDateCell("schedule_windows", index, "start_date", item.start_date)}
                  ${editableDateCell("schedule_windows", index, "end_date", item.end_date)}
                </div>
              </td>
              <td>
                <div class="field-line">
                  ${editableTextCell("schedule_windows", index, "default_allowed_weekdays", listText(item.default_allowed_weekdays), "周一|周二")}
                  ${editableTextCell("schedule_windows", index, "default_allowed_periods", listText(item.default_allowed_periods), "AM|PM")}
                </div>
              </td>
              <td><span class="window-slot-count">${html(`${scheduleWindowSlotCount(item.schedule_window_id)} 条`)}</span></td>
              <td>${editableCheckboxCell("schedule_windows", index, "is_active", item.is_active)}</td>
              <td>${editableTextCell("schedule_windows", index, "notes", item.notes)}</td>
              <td><button type="button" class="small" data-action="generate-window-time-slots" data-index="${index}">生成课节</button></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderTeacherUnavailable() {
  const sourceRows = state.teacher_unavailability || [];
  const rows = filteredRows(sourceRows, selected.teacherUnavailableSearch);
  const activeCount = sourceRows.filter((item) => item.is_active !== false).length;
  const pendingCount = sourceRows.filter((item) => item.unavailable_type === "待确认" || item.is_active === false).length;
  const stats = [
    ["不可排记录", sourceRows.length, "兼职限制、请假和临时不可排明细", ""],
    ["已启用", activeCount, "会进入排课过滤", ""],
    ["待确认", pendingCount, "需人工补日期/星期/时段后启用", pendingCount ? "warning" : ""],
    ["当前筛选", rows.length, selected.teacherUnavailableSearch ? "符合搜索条件" : "未输入搜索条件", ""],
  ];
  content.innerHTML = section(
    "",
    "",
    `
      <div class="resource-hero teacher-unavailable-hero">
        <div>
          <span>TEACHER TIME</span>
          <h2>只记录例外时间，不重复教师属性</h2>
          <p>项目、用工类型和主科目从教师基础信息关联；这里只维护不可排类型、日期/星期/时段和原因。</p>
        </div>
        <div class="resource-health ${pendingCount ? "warning" : "ok"}">
          <span>时间限制状态</span>
          <strong>${html(pendingCount ? `${pendingCount} 条待确认` : "不可排记录可用")}</strong>
          <em>全职老师请假也可以作为一条不可排记录填写。</em>
        </div>
      </div>
      <div class="resource-stat-grid">
        ${stats.map(([label, value, note, tone]) => `
          <article class="resource-stat-card ${html(tone)}">
            <span>${html(label)}</span>
            <strong>${html(value)}</strong>
            <em>${html(note)}</em>
          </article>
        `).join("")}
      </div>
      <div class="form-row">
        <label><span>搜索</span><input data-action="teacher-unavailable-search" value="${html(selected.teacherUnavailableSearch)}" placeholder="老师 / ID / 原因 / 日期 / 窗口"></label>
        <button type="button" data-action="add-teacher-unavailable">新增不可排记录</button>
      </div>
      ${teacherUnavailableTable(rows)}
    `,
  );
}

function teacherUnavailableTable(rows) {
  if (!rows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap segmented-table teacher-unavailable-table">
      <table>
        ${colgroupHtml(["180px", "260px", "150px", "230px", "360px", "90px", "220px", "260px", "80px"])}
        <thead>
          ${columnGroupRow([
            { label: "记录", span: 1 },
            { label: "教师", span: 1 },
            { label: "不可排规则", span: 3 },
            { label: "状态", span: 1 },
            { label: "说明", span: 2 },
            { label: "操作", span: 1 },
          ])}
          <tr><th>记录</th><th>教师</th><th>类型</th><th>日期范围</th><th>星期/时段/窗口</th><th>启用</th><th>原因</th><th>备注</th><th></th></tr>
        </thead>
        <tbody>
          ${rows.map((item) => {
            const index = (state.teacher_unavailability || []).indexOf(item);
            return `
              <tr>
                <td>${editableTextCell("teacher_unavailability", index, "unavailable_id", item.unavailable_id, "自动ID")}</td>
                <td>
                  <div class="field-line">
                    ${editableTextCell("teacher_unavailability", index, "employee_id", item.employee_id, "员工ID")}
                    ${editableTextCell("teacher_unavailability", index, "teacher_name", item.teacher_name, "姓名")}
                  </div>
                </td>
                <td>${editableTextCell("teacher_unavailability", index, "unavailable_type", item.unavailable_type || "待确认", "请假/兼职限制")}</td>
                <td>
                  <div class="field-line">
                    ${editableDateCell("teacher_unavailability", index, "start_date", item.start_date)}
                    ${editableDateCell("teacher_unavailability", index, "end_date", item.end_date)}
                  </div>
                </td>
                <td>
                  <div class="field-line">
                    ${editableTextCell("teacher_unavailability", index, "weekdays", listText(item.weekdays), "周二|周四")}
                    ${editableTextCell("teacher_unavailability", index, "periods", listText(item.periods), "AM|PM")}
                    ${editableTextCell("teacher_unavailability", index, "schedule_window_ids", listText(item.schedule_window_ids), "2026暑假")}
                  </div>
                </td>
                <td>${editableCheckboxCell("teacher_unavailability", index, "is_active", item.is_active)}</td>
                <td>${editableTextCell("teacher_unavailability", index, "reason", item.reason)}</td>
                <td>${editableTextCell("teacher_unavailability", index, "notes", item.notes)}</td>
                <td><button type="button" class="small danger" data-action="delete-teacher-unavailable" data-index="${index}">删除</button></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function scheduleWindowOptions() {
  return (state.schedule_windows || []).map((window) => ({
    id: window.schedule_window_id,
    name: window.schedule_window_name || window.schedule_window_id,
  }));
}

function scheduleWindowById(scheduleWindowId) {
  return (state.schedule_windows || []).find((window) => window.schedule_window_id === scheduleWindowId) || null;
}

function classWindowIsIncluded(item) {
  const value = String(item?.is_class_window_included ?? "").trim();
  return item?.is_class_window_included !== false && value !== "否" && value.toLowerCase() !== "false";
}

function classActualScheduleWindowIds(cls) {
  const classId = cls?.id || "";
  const rows = (state.class_window_boundaries || [])
    .filter((item) => item.class_id === classId && classWindowIsIncluded(item))
    .sort((left, right) => {
      const leftYear = Number(left.window_year || 0);
      const rightYear = Number(right.window_year || 0);
      if (leftYear !== rightYear) return leftYear - rightYear;
      const leftOrder = Number(left.window_order || 0);
      const rightOrder = Number(right.window_order || 0);
      if (leftOrder !== rightOrder) return leftOrder - rightOrder;
      return String(left.schedule_window_id || "").localeCompare(String(right.schedule_window_id || ""), "zh-CN");
    });
  const windowIds = rows.map((item) => item.schedule_window_id || item.schedule_window_name).filter(Boolean);
  return windowIds.length ? uniqueList(windowIds) : arrayValues(cls?.actual_schedule_window_ids);
}

function classById(classId) {
  return (state.classes || []).find((cls) => cls.id === classId) || null;
}

function laterDate(left, right) {
  if (!left) return right || "";
  if (!right) return left || "";
  return left > right ? left : right;
}

function earlierDate(left, right) {
  if (!left) return right || "";
  if (!right) return left || "";
  return left < right ? left : right;
}

function defaultPeriodFromWindow(window, fallback = "") {
  return arrayValues(window?.default_allowed_periods)[0] || fallback || "";
}

function applyClassWindowClassDefaults(item, { overwriteDates = false, overwriteResources = false } = {}) {
  const cls = classById(item.class_id);
  if (!cls) return;
  item.class_name = cls.name || item.class_id;
  item.product_id = cls.product_id || item.product_id || "";
  if (overwriteResources || !arrayValues(item.preferred_teaching_area_ids).length) {
    item.preferred_teaching_area_ids = arrayValues(cls.preferred_teaching_area_ids);
  }
  if (overwriteResources || !arrayValues(item.preferred_room_ids).length) {
    item.preferred_room_ids = arrayValues(cls.preferred_room_ids);
  }
  if (overwriteResources || item.preferred_room_is_required === undefined) {
    item.preferred_room_is_required = Boolean(cls.preferred_room_is_required);
  }
  if (overwriteDates) {
    const window = scheduleWindowById(item.schedule_window_id);
    item.earliest_date = laterDate(cls.first_lesson_date || cls.start_date, window?.start_date || "");
    item.latest_date = earlierDate(cls.end_date, window?.end_date || "");
    item.earliest_period = cls.first_lesson_period || cls.start_period || defaultPeriodFromWindow(window);
    item.latest_period = cls.end_period || defaultPeriodFromWindow(window, item.earliest_period);
  }
  ensureClassWindowId(item);
}

function applyClassWindowScheduleDefaults(item, { overwriteDates = false } = {}) {
  const window = scheduleWindowById(item.schedule_window_id);
  if (!window) return;
  item.schedule_window_name = window.schedule_window_name || window.schedule_window_id;
  item.window_year = Number(window.window_year || 0);
  item.window_order = Number(window.window_order || 0);
  item.season_window_id = window.season_window_id || "";
  item.season_name = window.season_name || "";
  if (!item.window_sequence) item.window_sequence = 1;
  if (overwriteDates) {
    const cls = classById(item.class_id);
    item.earliest_date = laterDate(cls?.first_lesson_date || cls?.start_date || "", window.start_date || "");
    item.latest_date = earlierDate(cls?.end_date || "", window.end_date || "");
    item.earliest_period = cls?.first_lesson_period || cls?.start_period || defaultPeriodFromWindow(window);
    item.latest_period = cls?.end_period || defaultPeriodFromWindow(window, item.earliest_period);
  }
  ensureClassWindowId(item);
}

function ensureClassWindowId(item) {
  if (item.class_id && item.schedule_window_id) {
    item.class_window_id = `${item.class_id}_${item.schedule_window_id}`;
  } else if (!item.class_window_id) {
    item.class_window_id = uniqueDraftId("CLASS_WINDOW", (state.class_window_boundaries || []).map((row) => row.class_window_id));
  }
}

function addClassWindow() {
  const cls = currentClass() || state.classes?.[0] || null;
  const window = (state.schedule_windows || []).find((item) => item.is_active !== false) || state.schedule_windows?.[0] || null;
  const item = {
    class_window_id: "",
    class_id: cls?.id || "",
    class_name: cls?.name || "",
    product_id: cls?.product_id || "",
    schedule_window_id: window?.schedule_window_id || "",
    window_year: Number(window?.window_year || 0),
    window_order: Number(window?.window_order || 0),
    season_window_id: window?.season_window_id || "",
    season_name: window?.season_name || "",
    window_sequence: 1,
    schedule_window_name: window?.schedule_window_name || window?.schedule_window_id || "",
    earliest_date: laterDate(cls?.first_lesson_date || cls?.start_date || "", window?.start_date || ""),
    earliest_period: cls?.first_lesson_period || cls?.start_period || defaultPeriodFromWindow(window),
    latest_date: earlierDate(cls?.end_date || "", window?.end_date || ""),
    latest_period: cls?.end_period || defaultPeriodFromWindow(window),
    preferred_teaching_area_ids: arrayValues(cls?.preferred_teaching_area_ids),
    preferred_room_ids: arrayValues(cls?.preferred_room_ids),
    preferred_room_is_required: Boolean(cls?.preferred_room_is_required),
    is_class_window_included: true,
    notes: "手动新增；请核对班级、年度窗口、日期时段和场地。",
  };
  ensureClassWindowId(item);
  state.class_window_boundaries.push(item);
  selected.classWindowSearch = item.class_id || "";
  showStatus("已新增班级排课窗口，请核对日期、时段和场地后保存。", "ok");
  renderClassWindows();
}

function classWindowSearchText(item) {
  return [
    item.class_window_id,
    item.class_id,
    item.class_name,
    classById(item.class_id)?.name,
    item.product_id,
    productName(item.product_id),
    item.schedule_window_id,
    item.schedule_window_name,
    item.season_name,
    item.window_year,
    item.window_sequence,
    item.earliest_date,
    item.earliest_period,
    item.latest_date,
    item.latest_period,
    arrayValues(item.preferred_teaching_area_ids).map((areaId) => teachingAreaSearchText(areaId)).join(" "),
    arrayValues(item.preferred_room_ids).map(roomName).join(" "),
    item.notes,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function classWindowMatchesSearch(item, keyword) {
  const tokens = String(keyword || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const text = classWindowSearchText(item);
  return tokens.every((token) => text.includes(token));
}

function renderClassWindows() {
  const sourceRows = state.class_window_boundaries || [];
  const matchedRows = sourceRows.filter((item) => classWindowMatchesSearch(item, selected.classWindowSearch));
  const rows = limitDisplayedRows(matchedRows, visibleRowLimits.classWindows);
  const includedCount = sourceRows.filter(classWindowIsIncluded).length;
  const distinctClasses = new Set(sourceRows.map((item) => item.class_id).filter(Boolean)).size;
  const withRoomCount = sourceRows.filter((item) => arrayValues(item.preferred_room_ids).length).length;
  const stats = [
    ["匹配窗口", matchedRows.length, "搜索后的窗口记录", ""],
    ["窗口记录", sourceRows.length, "班级 x 年度窗口", ""],
    ["覆盖班级", distinctClasses, "已有排课窗口的班级", ""],
    ["纳入排课", includedCount, "会进入自动排课范围", ""],
    ["指定教室", withRoomCount, "窗口独立教室限制", ""],
  ];
  content.innerHTML = section(
    "",
    "",
    `
      <div class="resource-hero class-window-hero">
        <div>
          <span>CLASS SCHEDULE WINDOW</span>
          <h2>班级排课窗口</h2>
          <p>维护班级在每个年度窗口内的最早/最晚可排日期、时段和窗口独立场地；产品规则仍按季节窗口匹配。</p>
        </div>
        <div class="resource-health ok">
          <span>班级排课窗口</span>
          <strong>${html(`${includedCount} 条纳入排课`)}</strong>
          <em>跨两个秋季、寒暑假异地上课，都在这里区分。</em>
        </div>
      </div>
      <div class="resource-stat-grid">
        ${stats.map(([label, value, note, tone]) => `
          <article class="resource-stat-card ${html(tone)}">
            <span>${html(label)}</span>
            <strong>${html(value)}</strong>
            <em>${html(note)}</em>
          </article>
        `).join("")}
      </div>
      <div class="form-row">
        <label><span>搜索窗口</span><input data-action="class-window-search" value="${html(selected.classWindowSearch)}" placeholder="班级 / 产品 / 年度窗口 / 教室"></label>
        <button type="button" data-action="add-class-window">新增班级排课窗口</button>
        <div class="muted">${html(displayLimitNote("窗口记录", rows.length, matchedRows.length, sourceRows.length))}</div>
      </div>
      ${classWindowTable(rows)}
      ${teachingAreaPickerDatalist()}
    `,
  );
}

function classWindowTable(rows) {
  if (!rows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  const classSelectOptions = classOptions();
  const windowSelectOptions = scheduleWindowOptions();
  const periodOptions = ["AM", "PM", "EVENING"];
  return `
    <div class="table-wrap segmented-table class-window-edit-table">
      <table>
        ${colgroupHtml(["300px", "260px", "78px", "210px", "210px", "300px", "350px", "132px", "122px", "250px", "78px"])}
        <thead>
          ${columnGroupRow([
            { label: "班级窗口", span: 3 },
            { label: "日期边界", span: 2 },
            { label: "窗口资源", span: 2 },
            { label: "控制", span: 2 },
            { label: "备注操作", span: 2 },
          ])}
          <tr>
            <th>班级</th><th>年度窗口</th><th>同季序号</th><th>可排开始</th><th>可排结束</th><th>窗口教学区</th><th>窗口教室</th><th>指定教室必选</th><th>纳入自动排课</th><th>备注</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((item) => {
            const index = (state.class_window_boundaries || []).indexOf(item);
            return `
              <tr>
                <td>
                  <div class="class-window-main">
                    <select data-list="class_window_boundaries" data-index="${index}" data-field="class_id">${selectOptions(classSelectOptions, item.class_id, "选择班级")}</select>
                  </div>
                </td>
                <td>
                  <div class="class-window-main">
                    <select data-list="class_window_boundaries" data-index="${index}" data-field="schedule_window_id">${selectOptions(windowSelectOptions, item.schedule_window_id, "选择年度窗口")}</select>
                    <span>${html([item.schedule_window_name || item.schedule_window_id, item.season_name].filter(Boolean).join(" · "))}</span>
                  </div>
                </td>
                <td>${editableNumberCell("class_window_boundaries", index, "window_sequence", item.window_sequence)}</td>
                <td>
                  <div class="field-line">
                    ${editableDateCell("class_window_boundaries", index, "earliest_date", item.earliest_date)}
                    <select data-list="class_window_boundaries" data-index="${index}" data-field="earliest_period">${selectOptions(periodOptions, item.earliest_period, "时段")}</select>
                  </div>
                </td>
                <td>
                  <div class="field-line">
                    ${editableDateCell("class_window_boundaries", index, "latest_date", item.latest_date)}
                    <select data-list="class_window_boundaries" data-index="${index}" data-field="latest_period">${selectOptions(periodOptions, item.latest_period, "时段")}</select>
                  </div>
                </td>
                <td>${classWindowTeachingAreaPicker(item, index)}</td>
                <td>${classWindowRoomPicker(item, index)}</td>
                <td>${editableCheckboxCell("class_window_boundaries", index, "preferred_room_is_required", item.preferred_room_is_required, "必选")}</td>
                <td>${editableCheckboxCell("class_window_boundaries", index, "is_class_window_included", item.is_class_window_included !== false, "纳入")}</td>
                <td><textarea data-list="class_window_boundaries" data-index="${index}" data-field="notes">${html(item.notes)}</textarea></td>
                <td><button type="button" class="small danger" data-action="delete-class-window" data-index="${index}">删除</button></td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderLockedLessons() {
  const sourceRows = state.locked_scheduled_lessons || [];
  const rows = filteredRows(sourceRows, selected.lockedLessonSearch);
  const lockedCount = sourceRows.filter((item) => item.is_locked !== false).length;
  const distinctClasses = new Set(sourceRows.map((item) => item.class_id).filter(Boolean)).size;
  const columns = [
    { label: "锁定ID", field: "id" },
    { label: "班级", format: (row) => `${row.class_name || ""} / ${row.class_id || ""}` },
    { label: "日期", field: "date" },
    { label: "时段", field: "period" },
    { label: "时间", format: (row) => [row.start_time, row.end_time].filter(Boolean).join("-") },
    { label: "教师", format: (row) => `${row.teacher_name || ""} / ${row.teacher_id || ""}` },
    { label: "教室", format: (row) => `${row.room_name || ""} / ${row.room_id || ""}` },
    { label: "课程", format: (row) => [row.subject, row.stage, row.course_group, row.course_name].filter(Boolean).join(" / ") },
    { label: "锁定", field: "is_locked" },
    { label: "备注", field: "notes" },
  ];
  content.innerHTML = section(
    "",
    "",
    `
      <div class="resource-hero locked-lessons-hero">
        <div>
          <span>LOCKED LESSONS</span>
          <h2>固定课表只做占用和审计</h2>
          <p>这些课次不参与自动移动，但会占用老师、教室和班级时间。</p>
        </div>
        <div class="resource-health ${lockedCount ? "ok" : "neutral"}">
          <span>锁定课表</span>
          <strong>${html(`${lockedCount} 条已锁定`)}</strong>
          <em>覆盖 ${html(distinctClasses)} 个班级。</em>
        </div>
      </div>
      <div class="resource-stat-grid">
        ${[
          ["锁定课次", sourceRows.length, "当前固定课表明细", ""],
          ["已锁定", lockedCount, "不参与自动调整", ""],
          ["覆盖班级", distinctClasses, "固定课表关联班级数", ""],
          ["当前筛选", rows.length, selected.lockedLessonSearch ? "符合搜索条件" : "未输入搜索条件", ""],
        ].map(([label, value, note, tone]) => `
          <article class="resource-stat-card ${html(tone)}">
            <span>${html(label)}</span>
            <strong>${html(value)}</strong>
            <em>${html(note)}</em>
          </article>
        `).join("")}
      </div>
      <div class="form-row">
        <label><span>搜索课表</span><input data-action="locked-lesson-search" value="${html(selected.lockedLessonSearch)}" placeholder="班级 / 日期 / 老师 / 教室 / 课程"></label>
        <div class="muted">显示 ${rows.length} / ${sourceRows.length} 条</div>
      </div>
      ${dataPreviewTable(rows, columns, {
        limit: 240,
        className: "locked-lesson-table",
        colWidths: ["170px", "260px", "110px", "76px", "130px", "220px", "220px", "360px", "76px", "300px"],
        columnGroups: [
          { label: "锁定项", span: 2 },
          { label: "时间", span: 3 },
          { label: "资源", span: 2 },
          { label: "课程", span: 1 },
          { label: "状态备注", span: 2 },
        ],
      })}
    `,
  );
}

function erpStandardProducts() {
  return state.erp_standard_products || [];
}

function erpProductByKey(key) {
  return erpStandardProducts().find((product) => product.erp_product_key === key) || null;
}

function erpProductLabel(product) {
  if (!product) return "";
  const tags = [
    product.school_version_name || "无版本",
    product.subject,
    product.school_class_type,
    product.lesson_count ? `${product.lesson_count}次` : "",
  ].filter(Boolean).join(" / ");
  return `${product.course_code} ${product.course_product_name_inner}${tags ? `（${tags}）` : ""}`;
}

function erpProductOptions(selectedValue = "") {
  const rows = [...erpStandardProducts()].sort((left, right) => {
    const leftKey = `${left.management_project}|${left.project_name}|${left.course_code}|${left.school_version_name}`;
    const rightKey = `${right.management_project}|${right.project_name}|${right.course_code}|${right.school_version_name}`;
    return leftKey.localeCompare(rightKey, "zh-CN");
  });
  return selectLabeledOptions(
    rows.map((product) => ({ value: product.erp_product_key, label: erpProductLabel(product) })),
    selectedValue,
    "选择ERP标准课程产品",
  );
}

function syncBusinessMappingLocalFields(mapping) {
  const product = productById(mapping.local_product_id || mapping.canonical_product_id);
  if (!product) return;
  mapping.local_product_id = product.id;
  mapping.local_product_name = product.name;
  mapping.local_product_line = product.product_line || "";
  mapping.local_sub_product = product.sub_product || "";
  mapping.local_product_system = product.product_system || "";
  mapping.local_course_nature = product.course_nature || "";
  mapping.local_subject = product.subject || "";
}

function applyBusinessMappingErpProduct(mapping) {
  const erpProduct = erpProductByKey(mapping.erp_product_key);
  if (!erpProduct) {
    mapping.erp_course_code = "";
    mapping.erp_course_name = "";
    mapping.erp_version_code = "";
    mapping.erp_version_name = "";
    mapping.business_product_id = "";
    mapping.business_product_name = "";
    mapping.match_status = "未匹配";
    mapping.match_confidence = "";
    return;
  }
  mapping.erp_course_code = erpProduct.course_code || "";
  mapping.erp_course_name = erpProduct.course_product_name_inner || "";
  mapping.erp_version_code = erpProduct.school_version_code || "";
  mapping.erp_version_name = erpProduct.school_version_name || "";
  mapping.erp_product_system = erpProduct.product_system || "";
  mapping.erp_product_category = erpProduct.product_category || "";
  mapping.erp_project_name = erpProduct.project_name || "";
  mapping.erp_subject = erpProduct.subject || "";
  mapping.erp_class_type = erpProduct.school_class_type || "";
  mapping.erp_duration_minutes = erpProduct.duration_minutes || "";
  mapping.erp_lesson_count = erpProduct.lesson_count || "";
  mapping.erp_single_lesson_minutes = erpProduct.single_lesson_minutes || "";
  mapping.erp_class_form = erpProduct.class_form || "";
  mapping.erp_teaching_method = erpProduct.teaching_method || "";
  mapping.business_product_id = erpProduct.course_code || "";
  mapping.business_product_name = erpProduct.course_product_name_inner || "";
  if (!mapping.match_status || mapping.match_status === "未匹配") mapping.match_status = "待确认";
  if (!mapping.match_confidence) mapping.match_confidence = "中";
  if (!mapping.match_source) mapping.match_source = "后台手动选择ERP标准产品";
}

function ensureBusinessProductMappingRows() {
  state.business_product_mappings = state.business_product_mappings || [];
  const existing = new Set(
    state.business_product_mappings
      .map((mapping) => mapping.local_product_id || mapping.canonical_product_id)
      .filter(Boolean),
  );
  let added = 0;
  for (const product of products()) {
    if (existing.has(product.id)) continue;
    state.business_product_mappings.push({
      local_product_id: product.id,
      local_product_name: product.name,
      local_product_line: product.product_line || "",
      local_sub_product: product.sub_product || "",
      local_product_system: product.product_system || "",
      local_course_nature: product.course_nature || "",
      local_subject: product.subject || "",
      erp_product_key: "",
      erp_course_code: "",
      erp_course_name: "",
      erp_version_code: "",
      erp_version_name: "",
      match_status: "未匹配",
      match_confidence: "",
      match_source: "后台补齐本地产品对应行",
      business_product_id: "",
      business_product_name: "",
      class_name_keywords: [],
      notes: "请关联ERP标准课程产品。",
    });
    added += 1;
  }
  showStatus(added ? `已补齐 ${added} 个本地产品对应行。` : "本地产品对应行已齐全。", added ? "ok" : "warning");
  renderBusinessMappings();
}

function businessMappingSearchText(mapping) {
  return [
    mapping.local_product_id,
    mapping.local_product_name,
    mapping.local_product_line,
    mapping.local_sub_product,
    mapping.local_product_system,
    mapping.local_course_nature,
    mapping.local_subject,
    mapping.erp_course_code,
    mapping.erp_course_name,
    mapping.erp_version_code,
    mapping.erp_version_name,
    mapping.erp_project_name,
    mapping.erp_subject,
    mapping.business_product_id,
    mapping.business_product_name,
    mapping.canonical_product_id,
    listText(mapping.class_name_keywords),
    mapping.match_status,
    mapping.match_confidence,
    mapping.notes,
  ].filter(Boolean).join(" ").toLowerCase();
}

function businessMappingEntries() {
  const keyword = selected.businessMappingSearch.trim().toLowerCase();
  const tokens = keyword.split(/\s+/).filter(Boolean);
  return (state.business_product_mappings || [])
    .map((mapping, index) => ({ mapping, index }))
    .filter(({ mapping }) => !selected.businessMappingStatusFilter || mapping.match_status === selected.businessMappingStatusFilter)
    .filter(({ mapping }) => !tokens.length || tokens.every((token) => businessMappingSearchText(mapping).includes(token)));
}

function businessMappingEditTable(entries) {
  if (!entries.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap segmented-table business-mapping-edit-table">
      <table>
        ${colgroupHtml(["360px", "520px", "270px", "190px", "300px"])}
        <thead>
          ${columnGroupRow([
            { label: "本地产品", span: 1 },
            { label: "ERP 对应", span: 2 },
            { label: "状态", span: 1 },
            { label: "备注", span: 1 },
          ])}
          <tr>
            <th>本地产品</th>
            <th>ERP标准课程产品</th>
            <th>ERP版本与课时</th>
            <th>匹配状态</th>
            <th>备注</th>
          </tr>
        </thead>
        <tbody>
          ${entries.map(({ mapping, index }) => `
            <tr class="${mapping.match_status === "已匹配" ? "matched" : "needs-review"}">
              <td>
                <strong>${html(mapping.local_product_name || productName(mapping.local_product_id))}</strong>
                <span>${html(mapping.local_product_id || mapping.canonical_product_id)}</span>
                <small>${html([mapping.local_product_line, mapping.local_sub_product, mapping.local_course_nature, mapping.local_subject].filter(Boolean).join(" / "))}</small>
              </td>
              <td>
                <select data-list="business_product_mappings" data-index="${index}" data-field="erp_product_key">${erpProductOptions(mapping.erp_product_key)}</select>
                <span class="field-caption">${html(mapping.erp_course_code ? `${mapping.erp_course_code} · ${mapping.erp_course_name}` : "未关联ERP标准课程产品")}</span>
              </td>
              <td>
                <span>${html([mapping.erp_version_name, mapping.erp_class_type].filter(Boolean).join(" / ") || "未选择")}</span>
                <em>${html(mapping.erp_lesson_count ? `${mapping.erp_duration_minutes || "-"} 分钟 / ${mapping.erp_lesson_count} 次 / 单次 ${mapping.erp_single_lesson_minutes || "-"} 分钟` : "")}</em>
                <small>${html([mapping.erp_class_form, mapping.erp_teaching_method].filter(Boolean).join(" / "))}</small>
              </td>
              <td>
                <div class="field-line narrow-fields">
                  <select data-list="business_product_mappings" data-index="${index}" data-field="match_status">${selectOptions(["已匹配", "待确认", "未匹配", "不适用"], mapping.match_status || "待确认", "状态")}</select>
                  <select data-list="business_product_mappings" data-index="${index}" data-field="match_confidence">${selectOptions(["高", "中", "低"], mapping.match_confidence || "", "置信度")}</select>
                </div>
                <span class="field-caption">${html(mapping.match_source || "")}</span>
              </td>
              <td><textarea data-list="business_product_mappings" data-index="${index}" data-field="notes">${html(mapping.notes || "")}</textarea></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderBusinessMappings() {
  const mappingEntries = businessMappingEntries();
  const erpRows = filteredRows(erpStandardProducts(), selected.businessMappingSearch);
  const mappings = state.business_product_mappings || [];
  const matched = mappings.filter((mapping) => mapping.match_status === "已匹配").length;
  const needsReview = mappings.filter((mapping) => mapping.match_status !== "已匹配").length;
  const erpColumns = [
    { label: "课程编码", field: "course_code" },
    { label: "课程产品名称", field: "course_product_name_inner" },
    { label: "版本", field: "school_version_name" },
    { label: "版本编码", field: "school_version_code" },
    { label: "产品体系", field: "product_system" },
    { label: "品类", field: "product_category" },
    { label: "所属项目", field: "project_name" },
    { label: "科目", field: "subject" },
    { label: "班容", field: "school_class_type" },
    { label: "课次", field: "lesson_count" },
    { label: "单次分钟", field: "single_lesson_minutes" },
    { label: "授课方式", field: "teaching_method" },
    { label: "启用", field: "is_enabled" },
  ];
  content.innerHTML = section(
    "",
    "",
    `
      <div class="resource-hero business-mapping-hero">
        <div>
          <span>ERP PRODUCT MAP</span>
          <h2>本地产品和 ERP 标准课程产品对应</h2>
          <p>这里维护排课系统里的本地产品，对应 ERP 标准课程产品的课程编码和版本编码。排课、导入和对账时优先看这张对应关系。</p>
        </div>
        <div class="resource-health ${needsReview ? "warning" : "ok"}">
          <span>对应完成度</span>
          <strong>${html(`${matched}/${mappings.length}`)}</strong>
          <em>${needsReview ? `${needsReview} 条需要人工确认` : "全部本地产品已确认"}</em>
        </div>
      </div>
      <div class="resource-stat-grid">
        ${[
          ["本地产品", products().length, "来自产品管理表", ""],
          ["对应行", mappings.length, "一行对应一个本地产品", ""],
          ["已匹配", matched, "可用于导入/对账", "ok"],
          ["待确认", needsReview, "需要人工核对", needsReview ? "warning" : ""],
        ].map(([label, value, note, tone]) => `
          <article class="resource-stat-card ${html(tone)}">
            <span>${html(label)}</span>
            <strong>${html(value)}</strong>
            <em>${html(note)}</em>
          </article>
        `).join("")}
      </div>
      <div class="form-row business-mapping-toolbar">
        <label><span>搜索</span><input data-action="business-mapping-search" value="${html(selected.businessMappingSearch)}" placeholder="本地产品 / ERP编码 / ERP名称 / 版本 / 科目"></label>
        <label><span>状态</span><select data-action="business-mapping-status-filter">${selectOptions(["已匹配", "待确认", "未匹配", "不适用"], selected.businessMappingStatusFilter, "全部")}</select></label>
        <button type="button" data-action="refresh-business-product-mappings">补齐产品</button>
        <div class="muted">当前显示 ${mappingEntries.length} / ${mappings.length} 条对应关系，ERP清单 ${erpRows.length} / ${erpStandardProducts().length} 条。</div>
      </div>
      ${section("本地产品 ↔ ERP标准课程产品", "", businessMappingEditTable(mappingEntries))}
      <details class="reference-panel">
        <summary>ERP标准课程产品清单 <span>${html(`${erpRows.length} / ${erpStandardProducts().length}`)}</span></summary>
        ${dataPreviewTable(erpRows, erpColumns, {
          limit: 240,
          className: "erp-standard-product-table",
          colWidths: ["130px", "320px", "180px", "150px", "130px", "120px", "130px", "120px", "110px", "86px", "96px", "120px", "76px"],
          columnGroups: [
            { label: "课程产品", span: 2 },
            { label: "版本", span: 2 },
            { label: "分类", span: 4 },
            { label: "班型课时", span: 3 },
            { label: "授课状态", span: 2 },
          ],
        })}
      </details>
    `,
  );
}

function renderOverview() {
  const scheduleWindowCount = (state.schedule_windows || []).length;
  const timeSlotCount = (state.time_slots || []).length;
  const productCount = products().length;
  const teacherCount = teacherChoices().length;
  const activeTeacherCount = (state.teachers || []).filter((teacher) => teacher.employment_status === "在职").length;
  const activeRoomCount = state.rooms.filter((room) => room.is_active).length;
  const classCount = state.classes.length;
  const teacherUnavailableCount = (state.teacher_unavailability || []).length;
  const classWindowBoundaryCount = (state.class_window_boundaries || []).length;
  const businessMappingCount = (state.business_product_mappings || []).length;
  const businessMappingNeedsReview = (state.business_product_mappings || []).filter((mapping) => mapping.match_status !== "已匹配").length;
  const areaLinkCount = (state.teaching_area_links || []).length;
  const stats = [
    ["年度窗口", scheduleWindowCount],
    ["课节", timeSlotCount],
    ["全局停课", (state.global_blackout_dates || []).filter((item) => item.is_active !== false).length],
    ["教学区", state.teaching_areas.length],
    ["通勤关系", areaLinkCount],
    ["可用教室", activeRoomCount],
    ["教师", teacherCount],
    ["产品", productCount],
    ["ERP产品对应", businessMappingCount],
    ["课程课时", state.product_courses.length],
    ["班级", classCount],
    ["班级排课窗口", classWindowBoundaryCount],
  ];
  const warnings = buildWarnings();
  const areasWithoutRooms = state.teaching_areas.filter((item) => !Number(item.active_room_count || 0)).length;
  const roomsWithoutArea = state.rooms.filter((room) => !room.teaching_area_id).length;
  const teachersMissingCore = (state.teachers || []).filter((teacher) => !String(teacher.id || teacher.employee_id || "").trim() || !teacher.name || !teacher.primary_subject).length;
  const productsMissingCore = products().filter(
    (product) => !product.project || !product.product_line || !product.sub_product || !product.subject_category || !product.subject || !product.course_nature,
  ).length;
  const productIdsWithCourses = new Set((state.product_courses || []).map((course) => course.product_id).filter(Boolean));
  const productsWithoutCourses = products().filter((product) => !productIdsWithCourses.has(product.id)).length;
  const coursesMissingHours = state.product_courses.filter((course) => !Number(course.total_hours)).length;
  const classesMissingScope = state.classes.filter((cls) => !cls.product_id || !cls.suite_code || !cls.subject || !cls.exam_season || !cls.start_date || !cls.end_date).length;
  const classesMissingTeachers = state.classes.filter((cls) => !cls.teacher_assignments?.length).length;
  const rulesCount = (state.product_schedule_rules || []).length;
  const rulesMissingWindow = (state.product_schedule_rules || []).filter((rule) => {
    return !(rule.season_window_id || rule.window_name)
      || !arrayValues(rule.allowed_periods).length
      || !arrayValues(rule.allowed_weekdays).length
      || !Number(rule.block_hours || rule.block_hours_override || 0);
  }).length;
  const blackoutCount = (state.global_blackout_dates || []).filter((item) => item.is_active !== false).length;
  const activeConflictGroups = (state.class_conflict_groups || []).filter(conflictGroupIsActive).length;
  const lockedLessonCount = (state.locked_scheduled_lessons || []).filter((lesson) => lesson.is_locked !== false).length;
  const productIssueCount = productsMissingCore + productsWithoutCourses + coursesMissingHours + rulesMissingWindow + businessMappingNeedsReview;
  const layerCards = [
    {
      index: "01",
      title: "全局时间",
      detail: `年度窗口 ${scheduleWindowCount} 个，课节 ${timeSlotCount} 个；全局停课 ${blackoutCount} 项。`,
      status: scheduleWindowCount && timeSlotCount ? "已生成" : "待生成",
      tone: scheduleWindowCount && timeSlotCount ? "ok" : "warning",
      tab: "timeData",
    },
    {
      index: "02",
      title: "基础资源",
      detail: `可用教室 ${activeRoomCount} 间，在职教师 ${activeTeacherCount} 人；教师不可排 ${teacherUnavailableCount} 条，通勤关系 ${areaLinkCount} 条。`,
      status: areasWithoutRooms + roomsWithoutArea + teachersMissingCore ? "需处理" : "可用",
      tone: areasWithoutRooms + roomsWithoutArea + teachersMissingCore ? "warning" : "ok",
      tab: "rooms",
    },
    {
      index: "03",
      title: "产品规则",
      detail: `产品 ${productCount} 个，课程 ${state.product_courses.length} 门，ERP产品对应 ${businessMappingCount} 条，窗口规则 ${rulesCount} 条；${productIssueCount} 项待补/确认。`,
      status: productIssueCount ? "需补齐" : "已就绪",
      tone: productIssueCount ? "warning" : "ok",
      tab: "productMeta",
    },
    {
      index: "04",
      title: "班级需求",
      detail: `班级 ${classCount} 个，班级排课窗口 ${classWindowBoundaryCount} 条；${classesMissingTeachers} 个未同步老师安排。`,
      status: classesMissingScope + classesMissingTeachers ? "需补齐" : "可排",
      tone: classesMissingScope + classesMissingTeachers ? "warning" : "ok",
      tab: "classWindows",
    },
    {
      index: "05",
      title: "控制边界",
      detail: `锁定课 ${lockedLessonCount} 条，互斥组 ${activeConflictGroups} 个。`,
      status: lockedLessonCount || activeConflictGroups ? "已维护" : "待确认",
      tone: "neutral",
      tab: "lockedLessons",
    },
    {
      index: "06",
      title: "运行交付",
      detail: preflightResult ? `最近上传前校验：${preflightResult.passed ? "通过" : "未通过"}。` : "先校验，再完整排课；课表变更后可局部更新或全量重算。",
      status: preflightResult?.passed ? "可运行" : "待校验",
      tone: preflightResult?.passed ? "ok" : "neutral",
      tab: "launch",
    },
  ];
  const gateCards = [
    ["窗口", "产品用季节窗口规则；班级按实际开结课日期生成年度窗口。"],
    ["资源", "教学区、教室、教师必须可用；面授场地以班级排课窗口为准。"],
    ["规则", "白天 4 小时课次固定同半天、同老师；停课日统一剔除。"],
    ["交付", "无硬冲突、无漏排、可对齐 ERP 后再发布只读页面。"],
  ];
  content.innerHTML = `
    <section class="overview-hero">
      <div>
        <span>AI Scheduling Console</span>
        <h2>按新数据框架看排课准备度</h2>
        <p>先确认年度时间和基础资源，再维护产品季节规则、班级实际边界和交付控制。每张卡都能跳到对应页面处理缺口。</p>
      </div>
      <div class="overview-actions">
        <button type="button" class="primary" data-action="switch-tab" data-tab="launch">排课运行维护</button>
        <button type="button" data-action="switch-tab" data-tab="rules">补产品规则</button>
      </div>
    </section>
    ${section(
      "当前数据规模",
      "只保留影响排课判断的关键数量。",
      `<div class="stats">${stats.map(([label, value]) => `<div class="stat"><span>${html(label)}</span><strong>${value}</strong></div>`).join("")}</div>`,
    )}
    ${section(
      "数据框架",
      "点击卡片进入对应页面处理。",
      `<div class="readiness-grid">
        ${layerCards.map((card) => `
          <button type="button" class="readiness-card ${html(card.tone)}" data-action="switch-tab" data-tab="${html(card.tab)}">
            <span>${html(card.index)}</span>
            <strong>${html(card.title)}</strong>
            <em>${html(card.status)}</em>
            <p>${html(card.detail)}</p>
          </button>
        `).join("")}
      </div>`,
    )}
    ${section(
      "交付门禁",
      "完整排课前只看这些硬条件。",
      `<div class="gate-summary-grid">
        ${gateCards.map(([title, detail]) => `
          <div class="gate-summary-card">
            <strong>${html(title)}</strong>
            <span>${html(detail)}</span>
          </div>
        `).join("")}
      </div>`,
    )}
    ${section(
      "待关注事项",
      "这些提示不会阻止保存，但建议在完整排课前处理。",
      warnings.length
        ? `<div class="pill-row">${warnings.map((warning) => `<span class="pill warning-text">${html(warning)}</span>`).join("")}</div>`
        : `<div class="pill-row"><span class="pill">当前未发现明显缺口</span></div>`,
    )}
  `;
}

function renderLaunch() {
  const pipeline = pipelineJob;
  const batch = batchScheduleJob;
  const statusLabel = (job) => job ? {
    queued: "等待中",
    running: "运行中",
    succeeded: "已完成",
    failed: "失败",
  }[job.status] || job.status : "未运行";
  const toneFor = (job) => {
    if (!job) return "neutral";
    if (job.status === "succeeded") return "ok";
    if (job.status === "failed") return "warning";
    if (job.status === "running" || job.status === "queued") return "running";
    return "neutral";
  };
  const missingTeacherRows = preflightResult?.missing_teacher_rows || [];
  const missingTeacherPreview = missingTeacherRows.length
    ? `
      <div class="table-wrap compact-result-table">
        <table>
          <thead><tr><th>班级</th><th>产品</th><th>科目</th><th>阶段</th><th>课程组</th></tr></thead>
          <tbody>
            ${missingTeacherRows.slice(0, 6).map((row) => `
              <tr>
                <td>${html(row.class_name || row.class_id || "")}</td>
                <td>${html(row.product_name || row.product_id || "")}</td>
                <td>${html(row.subject || "")}</td>
                <td>${html(row.stage || "")}</td>
                <td>${html(row.course_group || "")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
        ${missingTeacherRows.length > 6 ? `<div class="field-caption">仅展示前 6 条，完整清单请下载补录 CSV。</div>` : ""}
      </div>
    `
    : "";
  const pipelineLinks = pipeline
    ? [
        pipeline.report_url ? `<a href="${html(pipeline.report_url)}" target="_blank" rel="noreferrer">导入报告</a>` : "",
        pipeline.schedule_csv_url ? `<a href="${html(pipeline.schedule_csv_url)}" target="_blank" rel="noreferrer">CSV 明细</a>` : "",
        pipeline.schedule_html_url ? `<a href="${html(pipeline.schedule_html_url)}" target="_blank" rel="noreferrer">HTML 甘特图</a>` : "",
        ...(pipeline.generated_file_urls || []).map((item) => `<a href="${html(item.url)}" target="_blank" rel="noreferrer">${html(item.name)}</a>`),
      ].filter(Boolean)
    : [];
  const batchLinks = batch
    ? [
        batch.report_url ? `<a href="${html(batch.report_url)}" target="_blank" rel="noreferrer">运行报告</a>` : "",
        batch.schedule_csv_url ? `<a href="${html(batch.schedule_csv_url)}" target="_blank" rel="noreferrer">CSV 明细</a>` : "",
        batch.schedule_html_url ? `<a href="${html(batch.schedule_html_url)}" target="_blank" rel="noreferrer">结果总表 HTML</a>` : "",
      ].filter(Boolean)
    : [];
  const templateLinks = templateResult
    ? [
        templateResult.xlsx_url ? `<a href="${html(templateResult.xlsx_url)}" target="_blank" rel="noreferrer">Excel 模板</a>` : "",
        templateResult.zip_url ? `<a href="${html(templateResult.zip_url)}" target="_blank" rel="noreferrer">CSV 模板包</a>` : "",
        templateResult.report_url ? `<a href="${html(templateResult.report_url)}" target="_blank" rel="noreferrer">模板报告</a>` : "",
      ].filter(Boolean)
    : [];
  const preflightLinks = preflightResult
    ? [
        preflightResult.report_url ? `<a href="${html(preflightResult.report_url)}" target="_blank" rel="noreferrer">校验报告</a>` : "",
        ...(preflightResult.generated_file_urls || []).map((item) => `<a href="${html(item.url)}" target="_blank" rel="noreferrer">${html(item.name)}</a>`),
      ].filter(Boolean)
    : [];
  const pipelinePanel = pipeline
    ? `
      <div class="job-panel ${html(pipeline.status)}">
        <div class="job-row"><span>任务ID</span><strong>${html(pipeline.job_id)}</strong></div>
        <div class="job-row"><span>状态</span><strong>${html(statusLabel(pipeline))}</strong></div>
        <div class="job-row"><span>进度</span><strong>${html(pipeline.progress || "")}</strong></div>
        ${pipeline.error ? `<pre class="error-log">${html(pipeline.error)}</pre>` : ""}
        ${pipelineLinks.length ? `<div class="link-row">${pipelineLinks.join("")}</div>` : ""}
      </div>
    `
    : `<div class="empty-state small"><strong>还没有完整排课任务</strong><span>上传排课数据后在这里查看进度和结果。</span></div>`;
  const batchPanel = batch
    ? `
      <div class="job-panel ${html(batch.status)}">
        <div class="job-row"><span>任务ID</span><strong>${html(batch.job_id)}</strong></div>
        <div class="job-row"><span>状态</span><strong>${html(statusLabel(batch))}</strong></div>
        <div class="job-row"><span>进度</span><strong>${html(batch.progress || "")}</strong></div>
        ${batch.error ? `<pre class="error-log">${html(batch.error)}</pre>` : ""}
        ${batchLinks.length ? `<div class="link-row">${batchLinks.join("")}</div>` : ""}
      </div>
    `
    : `<div class="empty-state small"><strong>还没有课表维护任务</strong><span>小范围修改用快速更新；发布前用全量重算。</span></div>`;
  const preflightStatus = preflightResult
    ? (preflightResult.passed ? "校验通过" : "校验未通过")
    : "未校验";
  const hasResult = pipeline?.status === "succeeded" || batch?.status === "succeeded";
  const operationSteps = [
    ["01", "填写模板", "可下载", "先下载基础数据模板，或用原始导出生成一份预填模板。", "neutral"],
    ["02", "校验数据", preflightStatus, "上传填写后的模板或 CSV，只看能不能排；不会覆盖现有课表。", preflightResult?.passed ? "ok" : preflightResult ? "warning" : "neutral"],
    ["03", "生成课表", statusLabel(pipeline), "第一次出正式结果，或需要从头重排时使用。", toneFor(pipeline)],
    ["04", "维护课表", statusLabel(batch), "已有结果后，只改套班、班级或子产品时使用；窗口和场地以班级排课窗口为准。", toneFor(batch)],
    ["05", "查看结果", hasResult ? "可查看" : "待生成", "看总表、报告和 CSV；确认后再进入只读发布。", hasResult ? "ok" : "neutral"],
  ];

  content.innerHTML = `
    ${section(
      "排课运行维护",
      "新用户按 1 → 2 → 3 → 5 操作；已有课表只改一部分时用 4。",
      `<div class="operation-flow compact">
        ${operationSteps.map(([index, title, status, detail, tone]) => `
          <article class="operation-step-card ${html(tone)}">
            <span>${html(index)}</span>
            <strong>${html(title)}</strong>
            <em>${html(status)}</em>
            <p>${html(detail)}</p>
          </article>
        `).join("")}
      </div>`,
    )}

    ${section(
      "1. 填写/导入模板",
      "功能：下载基础数据模板；如果手上是 ERP 或业务导出文件，也可以先生成一份预填模板再补充。",
      `
        <div class="template-entry-grid">
          <a class="template-entry-card primary-card" href="${html(dataTemplatePage.url)}" target="_blank" rel="noreferrer">
            <strong>${html(dataTemplatePage.title)}</strong>
            <span>${html(dataTemplatePage.detail)}</span>
          </a>
          <div class="template-entry-card">
            <strong>生成预填模板</strong>
            <span>上传原始导出文件，系统生成 Excel 模板、CSV 模板包和模板报告。</span>
            <div class="upload-panel compact-upload">
              <input type="file" data-action="template-source-files" accept=".xlsx,.xlsm,.csv,text/csv" multiple>
              <button type="button" data-action="generate-template">生成</button>
            </div>
            ${templateLinks.length ? `<div class="link-row">${templateLinks.join("")}</div>` : ""}
          </div>
        </div>
      `,
    )}

    ${section(
      "2. 校验数据",
      "功能：排课前检查字段、产品映射、班级需求和硬冲突。只生成校验报告，不改数据、不生成课表。",
      `
        <div class="upload-panel">
          <input type="file" data-action="preflight-files" accept=".xlsx,.xlsm,.csv,text/csv" multiple>
          <button type="button" data-action="run-preflight">执行校验</button>
        </div>
        ${preflightResult
          ? `
          <div class="job-panel ${preflightResult.passed ? "succeeded" : "failed"}">
            <div class="job-row"><span>结果</span><strong>${preflightResult.passed ? "通过" : "未通过"}</strong></div>
            ${preflightResult.error ? `<pre class="error-log">${html(preflightResult.error)}</pre>` : ""}
            ${missingTeacherPreview}
            ${preflightLinks.length ? `<div class="link-row">${preflightLinks.join("")}</div>` : ""}
          </div>
        `
          : `<div class="launch-inline-note"><strong>状态</strong><span>未校验。先上传准备好的正式表或 CSV 包。</span></div>`}
      `,
    )}

    ${section(
      "3. 生成课表",
      "功能：用通过校验的数据生成一版完整课表。会先备份当前数据，再写出结果总表、报告和明细。",
      `
        <div class="upload-panel">
          <input type="file" data-action="pipeline-files" accept=".xlsx,.xlsm,.csv,text/csv" multiple>
          <button type="button" class="primary" data-action="run-pipeline">运行完整排课</button>
        </div>
        ${pipelinePanel}
      `,
    )}

    ${section(
      "4. 更新课表",
      "功能：已有正式结果后做小范围调整。填套班、班级或子产品就是局部更新；范围为空时执行全量重算。系统按产品窗口规则、班级排课窗口、资源和锁定课判断；暑假面授窗口也以班级排课窗口为准。",
      `
        <div class="batch-run-controls">
          <label>
            <span>套班编码</span>
            <input data-action="batch-suite-codes" value="${html(selected.batchSuiteCodes)}" placeholder="例如 2727, 2778">
          </label>
          <label>
            <span>班级编码</span>
            <input data-action="batch-class-ids" value="${html(selected.batchClassIds)}" placeholder="例如 KYYY2727">
          </label>
          <label>
            <span>子产品</span>
            <input data-action="batch-sub-products" value="${html(selected.batchSubProducts)}" placeholder="例如 无忧暑、半年营">
          </label>
          <div class="button-row batch-run-buttons">
            <button type="button" class="primary" data-action="run-batch-fast">快速更新当前范围</button>
            <button type="button" data-action="run-batch-full">全量重算</button>
          </div>
        </div>
        ${batchPanel}
      `,
    )}

    ${section(
      "5. 查看结果",
      "功能：排课成功后统一查看结果。先看排课报告是否有硬问题，再打开总表和 CSV 做人工核对。",
      `
        <div class="batch-result-links">
          <a href="${html(batchSchedulePage.url)}" target="_blank" rel="noreferrer">
            <strong>${html(batchSchedulePage.title)}</strong>
            <span>${html(batchSchedulePage.detail)}</span>
          </a>
          <a href="/outputs/batch_schedule_maintenance_report.md" target="_blank" rel="noreferrer">
            <strong>排课报告</strong>
            <span>查看覆盖、冲突、缺口和生成过程摘要。</span>
          </a>
          <a href="/outputs/batch_schedule_maintenance.csv" target="_blank" rel="noreferrer">
            <strong>CSV 明细</strong>
            <span>用于导入核对、二次分析或和 ERP 结果对齐。</span>
          </a>
        </div>
      `,
    )}
  `;
}

function renderBatchSchedules() {
  renderLaunch();
}

function renderPublish() {
  const gates = [
    ["不撞车", "老师、班级、教室、互斥组和锁定课表没有硬冲突。"],
    ["不漏课", "需求缺口班级数为 0，缺口课时为 0。"],
    ["能进系统", "ERP 字段、产品映射和导入数量已核对。"],
    ["只读分享", "分享页只查看，不开放保存、导入和重排。"],
  ];
  const publishLinks = [
    ["线上只读分享页", "给同事查看最终课表", "https://production.xdf-schedule-maintenance.pages.dev/schedule"],
    ["本地只读验证", "发布前在本机先确认展示效果", "http://127.0.0.1:8780/schedule"],
  ];
  const resultLinks = [
    ["课表总表", "查看本轮排课结果", "/outputs/batch_schedule_maintenance.html"],
    ["排课报告", "查看覆盖、冲突和缺口结论", "/outputs/batch_schedule_maintenance_report.md"],
    ["CSV 明细", "用于 ERP 对齐或二次核对", "/outputs/batch_schedule_maintenance.csv"],
  ];
  const reuseLinks = [
    ["方法复用专题页", "给同事理解这套工作方法", "/share/ai-scheduling-project/method-reuse.html"],
    ["复用步骤清单", "按步骤复制到下一轮项目", "/docs/ai-scheduling-reuse-playbook.md"],
    ["项目 SOP", "完整操作和验收流程", "/docs/ai-scheduling-sop.md"],
  ];
  content.innerHTML = `
    ${section(
      "只读发布与复用资料",
      "功能：把已经核对过的课表安全地给同事查看，并沉淀后续可复用资料。",
      `<div class="gate-summary-grid">
        ${gates.map(([title, detail]) => `
          <div class="gate-summary-card">
            <strong>${html(title)}</strong>
            <span>${html(detail)}</span>
          </div>
        `).join("")}
      </div>`,
    )}
    ${section(
      "只读分享入口",
      "功能：只给别人看课表结果。不要把本地管理后台或可保存页面发出去。",
      `<div class="publish-link-grid">
        ${publishLinks.map(([label, detail, url]) => `
          <a href="${html(url)}" target="_blank" rel="noreferrer">
            <strong>${html(label)}</strong>
            <em>${html(detail)}</em>
            <span>${html(url)}</span>
          </a>
        `).join("")}
      </div>`,
    )}
    ${section(
      "发布前核对资料",
      "功能：发布前自己核对用。看报告确认没有硬问题，再看总表和 CSV 明细。",
      `<div class="publish-link-grid compact">
        ${resultLinks.map(([label, detail, url]) => `
          <a href="${html(url)}" target="_blank" rel="noreferrer">
            <strong>${html(label)}</strong>
            <em>${html(detail)}</em>
            <span>${html(url)}</span>
          </a>
        `).join("")}
      </div>`,
    )}
    ${section(
      "项目复用资料",
      "功能：给下一轮排课或其他团队复用流程，不是日常排课必须操作。",
      `<div class="publish-link-grid compact">
        ${reuseLinks.map(([label, detail, url]) => `
          <a href="${html(url)}" target="_blank" rel="noreferrer">
            <strong>${html(label)}</strong>
            <em>${html(detail)}</em>
            <span>${html(url)}</span>
          </a>
        `).join("")}
      </div>`,
    )}
  `;
}

function buildWarnings() {
  const warnings = [];
  const productIds = new Set(products().map((product) => product.id));
  for (const product of products()) {
    for (const [field, label] of [
      ["project", "项目"],
      ["product_line", "产品线"],
      ["sub_product", "子产品"],
      ["product_system", "产品体系"],
      ["standard_capacity", "标准人数"],
      ["capacity_type", "班容类型"],
      ["subject_category", "科目类型"],
      ["subject", "科目"],
      ["course_nature", "课程性质"],
    ]) {
      if (!product[field]) warnings.push(`${product.name || product.id} 未填写${label}`);
    }
  }
  for (const teacher of state.teachers || []) {
    if (!teacher.id && !teacher.employee_id) warnings.push("教师基础信息中存在未填写员工ID的记录");
    if ((teacher.id || teacher.employee_id) && !teacher.name) warnings.push(`教师 ${teacher.id || teacher.employee_id} 未填写姓名`);
    if ((teacher.id || teacher.employee_id) && teacher.employment_status && teacher.employment_status !== "在职") {
      warnings.push(`教师 ${teacher.name || teacher.id || teacher.employee_id} 当前状态为 ${teacher.employment_status}`);
    }
  }
  for (const cls of state.classes) {
    if (!cls.product_id) warnings.push(`${cls.name || cls.id} 未选择产品`);
    if (cls.product_id && !productIds.has(cls.product_id)) warnings.push(`${cls.name || cls.id} 的产品不存在`);
    if (!cls.exam_season) warnings.push(`${cls.name || cls.id} 未填写考季`);
    if (!cls.suite_code) warnings.push(`${cls.name || cls.id} 未填写套班编码`);
    if (!cls.subject) warnings.push(`${cls.name || cls.id} 未填写科目`);
    if (cls.subject && cls.product_id && !productSubjects(cls.product_id).includes(cls.subject)) {
      warnings.push(`${cls.name || cls.id} 的科目 ${cls.subject} 不在所属产品课程中`);
    }
    const allowedStages = new Set(productStages(cls.product_id, cls.subject));
    for (const stage of arrayValues(cls.stages)) {
      if (!allowedStages.has(stage)) warnings.push(`${cls.name || cls.id} 的阶段 ${stage} 不在所属产品/科目课程中`);
    }
    if (!cls.teacher_assignments?.length) warnings.push(`${cls.name || cls.id} 未填写老师安排`);
    for (const assignment of cls.teacher_assignments || []) {
      if (assignment.teacher_id && !teacherById(assignment.teacher_id)) {
        warnings.push(`${cls.name || cls.id}/${courseLabel(assignment)} 的老师 ${assignment.teacher_id} 不在教师基础信息中`);
      }
    }
  }
  return warnings.slice(0, 20);
}

function renderRooms() {
  const area = currentArea();
  if (!selected.areaId && area) selected.areaId = area.id;
  const areaKeyword = selected.areaSearch.trim().toLowerCase();
  const search = selected.roomSearch.trim().toLowerCase();
  const areaIds = new Set((state.teaching_areas || []).map((item) => item.id).filter(Boolean));
  const activeRooms = (state.rooms || []).filter((room) => room.is_active);
  const activeCapacity = activeRooms.reduce((sum, room) => sum + Number(room.capacity || 0), 0);
  const roomsWithoutAreaCount = (state.rooms || []).filter((room) => !room.teaching_area_id || !areaIds.has(room.teaching_area_id)).length;
  const inactiveAreaCount = (state.teaching_areas || []).filter((item) => !item.is_active || Number(item.active_room_count || 0) === 0).length;
  const missingAreaNameCount = (state.teaching_areas || []).filter((item) => !String(item.name || item.short_name || "").trim()).length;
  const visibleAreas = state.teaching_areas.filter((item) => !areaKeyword || teachingAreaSearchText(item.id).toLowerCase().includes(areaKeyword));
  const areaRooms = state.rooms
    .map((room, index) => ({ room, index }))
    .filter(({ room }) => !area || room.teaching_area_id === area.id)
    .filter(({ room }) => !search || `${room.id} ${room.name} ${room.room_type} ${teachingAreaSearchText(room.teaching_area_id)}`.toLowerCase().includes(search));
  const roomResourceIssueCount = roomsWithoutAreaCount + inactiveAreaCount + missingAreaNameCount;
  const roomResourceHealth = roomResourceIssueCount
    ? {
        tone: "warning",
        title: `${roomResourceIssueCount} 项资源需确认`,
        desc: "处理无可用教室、未挂教学区和命名缺口。",
      }
    : {
        tone: "ok",
        title: "场地资源可进入排课",
        desc: "教学区、教室和容量可用于排课。",
      };
  const roomStats = [
    ["教学区", state.teaching_areas.length, "进入排课资源池的教学区", ""],
    ["当前筛选", visibleAreas.length, areaKeyword ? "符合搜索条件的教学区" : "未输入搜索条件", ""],
    ["可用教室", activeRooms.length, "会参与排课容量计算", ""],
    ["可用容量", activeCapacity, "按可用教室座位数汇总", ""],
    ["无可用教室", inactiveAreaCount, "需要补教室或确认不参与排课", inactiveAreaCount ? "warning" : ""],
    ["未挂教学区", roomsWithoutAreaCount, "教室缺少所属教学区会被排除", roomsWithoutAreaCount ? "warning" : ""],
  ];

  const list = `
    <div class="list-panel">
      <div class="list-tools">
        <button type="button" data-action="add-area">新增教学区</button>
        <input data-action="area-search" value="${html(selected.areaSearch)}" placeholder="搜索简称 / 区域 / 校区 / ID">
      </div>
      <div class="record-list">
        ${visibleAreas
          .map(
            (item) => `
              <button type="button" class="record-item ${item.id === selected.areaId ? "active" : ""}" data-action="select-area" data-id="${html(item.id)}">
                <strong>${html(areaShortName(item) || item.id)}</strong>
              </button>
            `,
          )
          .join("") || `<div class="empty-inline">没有匹配的教学区。</div>`}
      </div>
    </div>
  `;

  const detail = area
    ? `
      <div class="form-grid three">
        <label><span>教学区 ID</span><input data-entity="area" data-id="${html(area.id)}" data-field="id" value="${html(area.id)}"></label>
        <label><span>教学区名称</span><input data-entity="area" data-id="${html(area.id)}" data-field="name" value="${html(area.name)}"></label>
        <label><span>教学区简称</span><input data-entity="area" data-id="${html(area.id)}" data-field="short_name" value="${html(area.short_name)}" placeholder="页面显示和筛选用"></label>
        <label><span>区域标签</span><input data-entity="area" data-id="${html(area.id)}" data-field="region_tag" value="${html(area.region_tag || "")}" placeholder="例如：蜀山 / 经开 / 集训营基地"></label>
        <label class="wide"><span>校区地址</span><input data-entity="area" data-id="${html(area.id)}" data-field="address" value="${html(area.address || "")}" placeholder="用于地图定位和跨区距离判断"></label>
        <label><span>经度</span><input data-entity="area" data-id="${html(area.id)}" data-field="longitude" value="${html(area.longitude || "")}" placeholder="高德坐标 lng"></label>
        <label><span>纬度</span><input data-entity="area" data-id="${html(area.id)}" data-field="latitude" value="${html(area.latitude || "")}" placeholder="高德坐标 lat"></label>
        <label><span>校区</span><input data-entity="area" data-id="${html(area.id)}" data-field="campus" value="${html(area.campus)}"></label>
        <label><span>排课容量</span><input disabled value="${html(area.scheduling_capacity || 0)}"></label>
        <label><span>可用教室</span><input disabled value="${html(area.active_room_count || 0)}"></label>
        <label><span>容量状态</span><input disabled value="${html(area.capacity_check || (area.is_active ? "OK" : "请补可用教室"))}"></label>
        <label class="wide"><span>备注</span><textarea data-entity="area" data-id="${html(area.id)}" data-field="notes">${html(area.notes)}</textarea></label>
      </div>
      <div class="form-row">
        <label><span>搜索当前教学区教室</span><input data-action="room-search" value="${html(selected.roomSearch)}" placeholder="教室名称 / 类型 / ID"></label>
        <button type="button" data-action="add-room">新增教室</button>
      </div>
      ${roomTable(areaRooms)}
    `
    : document.querySelector("#emptyStateTemplate").innerHTML;

  content.innerHTML = section(
    "",
    "",
    `
      <div class="room-resource-hero">
        <div>
          <span>ROOM RESOURCE</span>
          <h2>先确认哪些场地真正可排</h2>
          <p>核对教学区可用性、教室归属和容量；异常会影响班级可排空间。</p>
        </div>
        <div class="room-resource-health ${html(roomResourceHealth.tone)}">
          <span>场地健康度</span>
          <strong>${html(roomResourceHealth.title)}</strong>
          <em>${html(roomResourceHealth.desc)}</em>
        </div>
      </div>
      <div class="room-resource-stat-grid">
        ${roomStats
          .map(
            ([label, value, note, tone]) => `
              <article class="room-resource-stat-card ${html(tone)}">
                <span>${html(label)}</span>
                <strong>${html(value)}</strong>
                <em>${html(note)}</em>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="split">${list}<div>${detail}</div></div>
    `,
  );
}

function roomTable(rows) {
  if (!rows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap segmented-table room-edit-table">
      <table>
        ${colgroupHtml(["300px", "280px", "90px", "130px", "90px", "300px", "80px"])}
        <thead>
          ${columnGroupRow([
            { label: "教室", span: 1 },
            { label: "归属", span: 1 },
            { label: "容量类型", span: 2 },
            { label: "状态", span: 1 },
            { label: "备注操作", span: 2 },
          ])}
          <tr>
            <th>教室</th><th>所属教学区</th><th>容量</th><th>类型</th><th>可用</th><th>备注</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              ({ room, index }) => `
                <tr>
                  <td>
                    <div class="field-line">
                      <input data-list="rooms" data-index="${index}" data-field="id" value="${html(room.id)}" placeholder="教室 ID">
                      <input data-list="rooms" data-index="${index}" data-field="name" value="${html(room.name)}" placeholder="教室名称">
                    </div>
                  </td>
                  <td><select data-list="rooms" data-index="${index}" data-field="teaching_area_id">${selectOptions(
                    teachingAreaOptions(),
                    room.teaching_area_id,
                  )}</select></td>
                  <td><input type="number" data-list="rooms" data-index="${index}" data-field="capacity" value="${html(room.capacity)}"></td>
                  <td><input data-list="rooms" data-index="${index}" data-field="room_type" value="${html(room.room_type)}"></td>
                  <td><label class="inline-check"><input type="checkbox" data-list="rooms" data-index="${index}" data-field="is_active" ${room.is_active ? "checked" : ""}>可用</label></td>
                  <td><input data-list="rooms" data-index="${index}" data-field="notes" value="${html(room.notes)}"></td>
                  <td><button type="button" class="small danger" data-action="delete-room" data-index="${index}">删除</button></td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderTeachers() {
  for (const teacher of state.teachers || []) applyTeacherSubjectType(teacher);
  const teacherRows = state.teachers || [];
  const keyword = selected.teacherSearch.trim().toLowerCase();
  const rows = teacherRows
    .map((teacher, index) => ({ teacher, index }))
    .filter(({ teacher }) => {
      if (!keyword) return true;
      return [
        teacher.id,
        teacher.employee_id,
        teacher.name,
        teacher.gender,
        teacher.project,
        teacher.teacher_role,
        teacher.identity,
        teacher.employment_type,
        teacher.teacher_type,
        teacher.primary_subject,
        teacher.subject_type,
        teacher.contract_status,
        teacher.employment_status,
        teacher.notes,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  const teacherIdCounts = new Map();
  for (const teacher of teacherRows) {
    const id = String(teacher.id || teacher.employee_id || "").trim();
    if (!id) continue;
    teacherIdCounts.set(id, (teacherIdCounts.get(id) || 0) + 1);
  }
  const duplicateIdCount = [...teacherIdCounts.values()].filter((count) => count > 1).reduce((sum, count) => sum + count - 1, 0);
  const missingIdCount = teacherRows.filter((teacher) => !String(teacher.id || teacher.employee_id || "").trim()).length;
  const missingNameCount = teacherRows.filter((teacher) => !String(teacher.name || "").trim()).length;
  const missingSubjectCount = teacherRows.filter((teacher) => !String(teacher.primary_subject || "").trim()).length;
  const activeTeacherCount = teacherRows.filter((teacher) => teacher.employment_status === "在职").length;
  const resourceIssueCount = missingIdCount + missingNameCount + missingSubjectCount + duplicateIdCount;
  const resourceHealth = resourceIssueCount
    ? {
        tone: "warning",
        title: `${resourceIssueCount} 项需要补齐`,
        desc: "补员工ID、姓名和主教学科目。",
      }
    : {
        tone: "ok",
        title: "教师底表可继续使用",
        desc: "基础身份和主科目完整。",
      };
  const teacherStats = [
    ["教师记录", teacherRows.length, "当前教师基础信息总量", ""],
    ["当前筛选", rows.length, keyword ? "符合搜索条件的教师" : "未输入搜索条件", ""],
    ["在职教师", activeTeacherCount, "可优先进入排课匹配", ""],
    ["缺员工ID", missingIdCount, "员工ID是排课唯一编号", missingIdCount ? "warning" : ""],
    ["缺姓名/主科", missingNameCount + missingSubjectCount, "影响班级老师匹配和科目判断", missingNameCount + missingSubjectCount ? "warning" : ""],
    ["重复ID", duplicateIdCount, "同一员工ID只能对应一名老师", duplicateIdCount ? "warning" : ""],
  ];

  content.innerHTML = section(
    "",
    "",
    `
      <div class="teacher-resource-hero">
        <div>
          <span>TEACHER RESOURCE</span>
          <h2>先把老师资源整理成可排对象</h2>
          <p>维护员工ID、姓名、主科、用工类型和在职状态；任课关系在“班级老师安排”页处理。</p>
        </div>
        <div class="teacher-resource-health ${html(resourceHealth.tone)}">
          <span>资源健康度</span>
          <strong>${html(resourceHealth.title)}</strong>
          <em>${html(resourceHealth.desc)}</em>
        </div>
      </div>
      <div class="teacher-resource-stat-grid">
        ${teacherStats
          .map(
            ([label, value, note, tone]) => `
              <article class="teacher-resource-stat-card ${html(tone)}">
                <span>${html(label)}</span>
                <strong>${html(value)}</strong>
                <em>${html(note)}</em>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="form-row">
        <label><span>搜索教师</span><input data-action="teacher-search" value="${html(selected.teacherSearch)}" placeholder="员工ID / 姓名 / 科目 / 状态"></label>
        <button type="button" data-action="add-teacher">新增教师</button>
      </div>
      ${teacherBaseTable(rows)}
    `,
  );
}

function teacherBaseTable(rows) {
  if (!rows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap segmented-table teachers-table">
      <table>
        ${colgroupHtml(["110px", "140px", "90px", "130px", "120px", "120px", "140px", "110px", "110px", "110px", "280px", "80px"])}
        <thead>
          ${columnGroupRow([
            { label: "身份", span: 3 },
            { label: "归属用工", span: 3 },
            { label: "教学能力", span: 2 },
            { label: "状态", span: 2 },
            { label: "备注操作", span: 2 },
          ])}
          <tr>
            <th>员工ID</th><th>教师姓名</th><th>性别</th><th>归属项目</th><th>教师角色</th><th>用工类型</th><th>主教学科目</th><th>科目类型</th><th>合同状态</th><th>在职状态</th><th>备注</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              ({ teacher, index }) => `
                <tr>
                  <td><input data-list="teachers" data-index="${index}" data-field="id" value="${html(teacher.id || teacher.employee_id)}" placeholder="员工ID"></td>
                  <td><input data-list="teachers" data-index="${index}" data-field="name" value="${html(teacher.name)}" placeholder="教师姓名"></td>
                  <td><select data-list="teachers" data-index="${index}" data-field="gender">${selectOptions(["男", "女", "其他"], teacher.gender, "未填")}</select></td>
                  <td><input data-list="teachers" data-index="${index}" data-field="project" value="${html(teacher.project)}" placeholder="如 考研"></td>
                  <td><select data-list="teachers" data-index="${index}" data-field="teacher_role">${selectOptions(["管理者", "教师"], teacher.teacher_role || teacher.identity, "未填")}</select></td>
                  <td><select data-list="teachers" data-index="${index}" data-field="employment_type">${selectOptions(["全职", "兼职", "外聘", "内部"], teacher.employment_type || teacher.teacher_type, "未填")}</select></td>
                  <td><input data-list="teachers" data-index="${index}" data-field="primary_subject" value="${html(teacher.primary_subject)}" placeholder="如 英语"></td>
                  <td><select data-list="teachers" data-index="${index}" data-field="subject_type">${selectOptions(["公共课", "专业课"], teacher.subject_type, "未填")}</select></td>
                  <td><select data-list="teachers" data-index="${index}" data-field="contract_status">${selectOptions(["已签约", "未签约", "待续签", "已终止"], teacher.contract_status, "未填")}</select></td>
                  <td><select data-list="teachers" data-index="${index}" data-field="employment_status">${selectOptions(["在职", "离职", "停用", "待入职"], teacher.employment_status, "未填")}</select></td>
                  <td><input data-list="teachers" data-index="${index}" data-field="notes" value="${html(teacher.notes)}"></td>
                  <td><button type="button" class="small danger" data-action="delete-teacher" data-index="${index}">删除</button></td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderProductMeta() {
  const keyword = selected.productSearch.trim().toLowerCase();
  const productRows = products();
  const productRowsById = new Map(productRows.map((product) => [product.id, product]));
  const courseProductIds = new Set((state.product_courses || []).map((course) => course.product_id).filter(Boolean));
  const classProductIds = new Set((state.classes || []).map((cls) => cls.product_id).filter(Boolean));
  const rows = (state.products || [])
    .map((product, index) => ({ product, index }))
    .map(({ product, index }) => ({ product: productRowsById.get(product.id) || product, index }))
    .filter(({ product }) => productMatchesKeyword(product, keyword))
    .filter(({ product }) => productMatchesTagFilters(product, selected.productMetaFilters));
  const missingCoreTagCount = productRows.filter(
    (product) => !product.project || !product.product_line || !product.sub_product || !product.subject_category || !product.subject || !product.course_nature,
  ).length;
  const missingCapacityCount = productRows.filter((product) => !Number(product.standard_capacity || 0)).length;
  const withoutCourseCount = productRows.filter((product) => !courseProductIds.has(product.id)).length;
  const usedByClassCount = productRows.filter((product) => classProductIds.has(product.id)).length;
  const productIssueCount = missingCoreTagCount + missingCapacityCount + withoutCourseCount;
  const productHealth = productIssueCount
    ? {
        tone: "warning",
        title: `${productIssueCount} 项产品口径需确认`,
        desc: "补产品标签、标准人数和课程明细。",
      }
    : {
        tone: "ok",
        title: "产品口径可继续复用",
        desc: "标签、班容和课程连接完整。",
      };
  const productStats = [
    ["产品记录", productRows.length, "当前产品基础信息总量", ""],
    ["当前筛选", rows.length, keyword ? "符合搜索/标签条件的产品" : "未输入搜索条件", ""],
    ["被班级使用", usedByClassCount, "已有班级引用这些产品", ""],
    ["缺核心标签", missingCoreTagCount, "项目/产品线/子产品/科目等标签", missingCoreTagCount ? "warning" : ""],
    ["缺标准人数", missingCapacityCount, "影响班容类型和教室容量判断", missingCapacityCount ? "warning" : ""],
    ["未建课程", withoutCourseCount, "没有课程明细就无法生成排课需求", withoutCourseCount ? "warning" : ""],
  ];

  content.innerHTML = section(
    "",
    "",
    `
      <div class="resource-hero product-meta-hero">
        <div>
          <span>PRODUCT META</span>
          <h2>先统一产品口径，再让班级继承</h2>
          <p>统一产品标签和标准人数；班级继承这些字段，课程规则也按此对齐。</p>
        </div>
        <div class="resource-health ${html(productHealth.tone)}">
          <span>产品口径健康度</span>
          <strong>${html(productHealth.title)}</strong>
          <em>${html(productHealth.desc)}</em>
        </div>
      </div>
      <div class="resource-stat-grid">
        ${productStats
          .map(
            ([label, value, note, tone]) => `
              <article class="resource-stat-card ${html(tone)}">
                <span>${html(label)}</span>
                <strong>${html(value)}</strong>
                <em>${html(note)}</em>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="form-row">
        <label><span>搜索产品</span><input data-action="product-search" value="${html(selected.productSearch)}" placeholder="产品ID / 名称 / 标签"></label>
        <button type="button" data-action="download-products">下载产品表</button>
        <button type="button" data-action="import-products">导入产品表</button>
        <button type="button" data-action="add-product">新增产品</button>
        <input type="file" data-action="import-products-file" accept=".csv,text/csv" hidden>
      </div>
      ${productTagFilterControls("product-meta-tag-filter", selected.productMetaFilters, productRows, rows.length, productRows.length, "clear-product-meta-filters")}
      ${productMetaTable(rows)}
    `,
  );
}

function productMetaTable(rows) {
  if (!rows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap segmented-table products-table">
      <table>
        ${colgroupHtml(["360px", "110px", "140px", "130px", "130px", "250px", "220px", "90px", "110px", "110px", "130px", "130px", "260px", "120px"])}
        <thead>
          ${columnGroupRow([
            { label: "产品", span: 1 },
            { label: "产品标签", span: 4 },
            { label: "窗口阶段", span: 2 },
            { label: "班容", span: 2 },
            { label: "科目课程", span: 3 },
            { label: "备注操作", span: 2 },
          ])}
          <tr>
            <th>产品</th><th>项目</th><th>产品线</th><th>子产品</th><th>产品体系</th><th>季节窗口</th><th>适用阶段</th><th>标准人数</th><th>班容类型</th><th>科目类型</th><th>科目</th><th>课程性质</th><th>备注</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              ({ product, index }) => `
                <tr>
                  <td>
                    <div class="field-line wide-fields">
                      <input data-list="products" data-index="${index}" data-field="id" value="${html(product.id)}" placeholder="产品 ID">
                      <input data-list="products" data-index="${index}" data-field="name" value="${html(product.name)}" placeholder="产品名称">
                    </div>
                  </td>
                  <td><select data-list="products" data-index="${index}" data-field="project">${selectOptions(["考研", "专升本", "四六级"], product.project, "请选择")}</select></td>
                  <td><select data-list="products" data-index="${index}" data-field="product_line">${selectOptions(productLines(), product.product_line, "请选择")}</select></td>
                  <td><input data-list="products" data-index="${index}" data-field="sub_product" value="${html(product.sub_product)}"></td>
                  <td><input data-list="products" data-index="${index}" data-field="product_system" value="${html(product.product_system)}"></td>
                  <td><input data-list="products" data-index="${index}" data-field="season_window_ids" value="${html(listText(product.season_window_ids))}" placeholder="WINDOW_SUMMER|WINDOW_AUTUMN"></td>
                  <td><input data-list="products" data-index="${index}" data-field="applicable_stages" value="${html(listText(product.applicable_stages))}" placeholder="基础|强化"></td>
                  <td><input type="number" data-list="products" data-index="${index}" data-field="standard_capacity" value="${html(product.standard_capacity || "")}"></td>
                  <td><input value="${html(product.capacity_type)}" disabled></td>
                  <td><select data-list="products" data-index="${index}" data-field="subject_category">${selectOptions(["公共课", "专业课", "复试", "其他"], product.subject_category, "未填")}</select></td>
                  <td><input data-list="products" data-index="${index}" data-field="subject" value="${html(product.subject)}" placeholder="如 英语"></td>
                  <td><input data-list="products" data-index="${index}" data-field="course_nature" value="${html(product.course_nature)}"></td>
                  <td><input data-list="products" data-index="${index}" data-field="notes" value="${html(product.notes)}"></td>
                  <td>
                    <div class="field-line narrow-fields">
                      <button type="button" class="small" data-action="refresh-product-tags" data-index="${index}">刷新</button>
                      <button type="button" class="small danger" data-action="delete-product" data-index="${index}">删除</button>
                    </div>
                  </td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function productDetailHtml() {
  const productList = productCoursePageProducts();
  if (!selected.productId && productList[0]) selected.productId = productList[0].id;
  const rows = productCourses(selected.productId);
  normalizeCourseFilters(rows);
  const product = productList.find((item) => item.id === selected.productId);

  if (!product) {
    return document.querySelector("#emptyStateTemplate").innerHTML;
  }
  const summary = productCourseSummary(product.id);
  const contextItems = [
    product.subject || "未填科目",
    product.course_nature || "",
    `${summary.count} 门课程`,
    `${summary.hours} 小时`,
  ].filter(Boolean);

  return `
    <div class="product-course-context">
      <div>
        <strong>${html(product.name || product.id)}</strong>
        <span>${html(contextItems.join(" · "))}</span>
      </div>
    </div>
    <div class="form-row">
      <div class="muted">只维护课程结构、阶段顺序、课程组、模块顺序和总课时。</div>
      <button type="button" data-action="add-course">新增课程</button>
      <button type="button" data-action="sync-course-name-tags">按模块补齐课程名称标签</button>
    </div>
    <datalist id="courseNameTagChoices">
      ${courseNameTagOptions().map((tag) => `<option value="${html(courseNameTagLabel(tag))}"></option>`).join("")}
    </datalist>
    ${courseFilterControls(rows)}
    ${courseTable(rows)}
  `;
}

function updateProductListActive() {
  content.querySelectorAll("[data-product-list] .record-item").forEach((item) => {
    const active = item.dataset.id === selected.productId;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function refreshProductDetail() {
  const detail = content.querySelector("[data-product-detail]");
  if (!detail) {
    renderProducts();
    return;
  }
  detail.innerHTML = productDetailHtml();
  updateProductListActive();
  applyProductCourseFilters();
}

function renderProducts() {
  const allProducts = products();
  const productList = productCoursePageProducts();
  if (selected.productId && !productList.some((product) => product.id === selected.productId)) {
    selected.productId = productList[0]?.id || "";
  }
  if (!selected.productId && productList[0]) selected.productId = productList[0].id;
  const courseRows = state.product_courses || [];
  const missingWindowRows = courseRows.filter((course) => !String(course.window_name || course.quarter || "").trim()).length;
  const missingStageRows = courseRows.filter((course) => !String(course.stage || "").trim()).length;
  const missingHourRows = courseRows.filter((course) => !Number(course.total_hours)).length;
  const incompleteCourseRows = courseRows.filter((course) => {
    return !course.product_id
      || !course.course_name
      || !Number(course.total_hours)
      || !String(course.stage || "").trim();
  }).length;
  const selectedProduct = productById(selected.productId);
  const selectedCourseRows = productCourses(selected.productId);
  const selectedTotalHours = selectedCourseRows.reduce((sum, { course }) => sum + Number(course.total_hours || 0), 0);
  const healthTone = incompleteCourseRows ? "warning" : courseRows.length ? "ok" : "neutral";
  const healthText = courseRows.length
    ? incompleteCourseRows
      ? `${incompleteCourseRows} 门课程待补齐`
      : "课程字段已完整"
    : "还没有课程数据";
  const courseStats = [
    ["课程总数", `${courseRows.length} 门`, "窗口期、阶段、模块和课时明细"],
    ["待补窗口期", `${missingWindowRows} 门`, "按窗口期区分排课时填写"],
    ["待补阶段", `${missingStageRows} 门`, "影响班级阶段勾选和排序"],
    ["待补总课时", `${missingHourRows} 门`, "缺总课时会影响需求生成"],
  ];

  const list = `
    <div class="list-panel">
      <div class="list-tools">
        ${productTagFilterControls(
          "product-course-product-filter",
          selected.productCourseProductFilters,
          allProducts,
          productList.length,
          allProducts.length,
          "clear-product-course-product-filters",
          true,
        )}
      </div>
      <div class="record-list" data-product-list>
        ${productList
          .map((item) => {
            const summary = productCourseSummary(item.id);
            return `
              <button type="button" class="record-item ${item.id === selected.productId ? "active" : ""}" aria-pressed="${item.id === selected.productId ? "true" : "false"}" data-action="select-product" data-id="${html(item.id)}">
                <strong>${html(item.name)}</strong>
                <span>${html(`${summary.count} 门课程 · ${summary.hours} 小时`)}</span>
              </button>
            `;
          })
          .join("")}
      </div>
    </div>
  `;

  content.innerHTML = `
    <section class="product-course-hero">
      <div>
        <span>Course Foundation</span>
        <h2>产品课程课时</h2>
      </div>
      <div class="product-course-health ${html(healthTone)}">
        <span>课程健康度</span>
        <strong>${html(healthText)}</strong>
        <em>${selectedProduct ? `当前选中：${html(selectedProduct.name || selectedProduct.id)} · ${selectedCourseRows.length} 门课程 · ${selectedTotalHours} 小时` : "先选择一个产品，再维护课程明细。"}</em>
      </div>
    </section>

    <section class="product-course-stat-grid" aria-label="产品课程关键统计">
      ${courseStats.map(([label, value, detail]) => `
        <article class="product-course-stat-card ${["待补窗口期", "待补阶段", "待补总课时"].includes(label) && value !== "0 门" ? "warning" : ""}">
          <span>${html(label)}</span>
          <strong>${html(value)}</strong>
          <em>${html(detail)}</em>
        </article>
      `).join("")}
    </section>

    ${section(
      "产品课程",
      "维护排课窗口期、阶段、课程组、模块和课时。",
      `<div class="split">${list}<div data-product-detail>${productDetailHtml()}</div></div>`,
    )}
  `;
  const productListElement = content.querySelector("[data-product-list]");
  if (productListElement) {
    productListElement.scrollTop = selected.productListScrollTop;
  }
  applyProductCourseFilters();
}

function courseTable(rows) {
  if (!rows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap segmented-table product-course-table">
      <table>
        ${colgroupHtml(["120px", "110px", "90px", "150px", "170px", "90px", "260px", "150px", "90px", "240px", "80px"])}
        <thead>
          ${columnGroupRow([
            { label: "窗口阶段", span: 3 },
            { label: "课程组模块", span: 3 },
            { label: "课程信息", span: 3 },
            { label: "备注操作", span: 2 },
          ])}
          <tr>
            <th>排课窗口期</th><th>阶段</th><th>阶段优先级</th><th>课程组</th><th>模块</th><th>模块优先级</th><th>课程名称标签</th><th>课程编码</th><th>总课时</th><th>备注</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              ({ course, index }) => `
                <tr data-course-row data-course-index="${index}">
                  <td><input data-list="product_courses" data-index="${index}" data-field="window_name" value="${html(course.window_name || course.quarter)}"></td>
                  <td><input data-list="product_courses" data-index="${index}" data-field="stage" value="${html(course.stage)}"></td>
                  <td><input type="number" data-list="product_courses" data-index="${index}" data-field="stage_priority" value="${html(course.stage_priority || "")}" placeholder="小优先"></td>
                  <td><input data-list="product_courses" data-index="${index}" data-field="course_group" value="${html(course.course_group)}"></td>
                  <td><input data-list="product_courses" data-index="${index}" data-field="course_module" value="${html(course.course_module)}"></td>
                  <td><input type="number" data-list="product_courses" data-index="${index}" data-field="module_priority_in_group" value="${html(course.module_priority_in_group || course.module_priority || "")}" placeholder="小优先"></td>
                  <td><input data-action="course-name-picker" data-index="${index}" value="${html(course.course_name)}" list="courseNameTagChoices" placeholder="输入课程名称/编码搜索选择"></td>
                  <td><input data-list="product_courses" data-index="${index}" data-field="course_code" value="${html(course.course_code)}" placeholder="课程编码"></td>
                  <td><input type="number" data-list="product_courses" data-index="${index}" data-field="total_hours" value="${html(course.total_hours)}"></td>
                  <td><input data-list="product_courses" data-index="${index}" data-field="notes" value="${html(course.notes)}"></td>
                  <td><button type="button" class="small danger" data-action="delete-course" data-index="${index}">删除</button></td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderRules() {
  const rows = state.product_schedule_rules || [];
  const faceToFaceRules = rows.filter((rule) => rule.delivery_mode === "面授").length;
  const rulesMissingWindow = rows.filter((rule) => ruleMissingRequiredFields(rule)).length;
  const filteredRows = ruleRowsForDisplay(rows);
  const displayedRows = limitDisplayedRows(filteredRows, visibleRowLimits.rules);
  const ruleTone = rulesMissingWindow ? "warning" : rows.length ? "ok" : "neutral";
  const ruleStatus = rows.length
    ? rulesMissingWindow
      ? `${rulesMissingWindow} 条规则待补齐`
      : "产品窗口规则已填写"
    : "还没有产品窗口规则";
  const ruleStats = [
    ["匹配规则", `${filteredRows.length} 条`, "按搜索和筛选后的规则"],
    ["规则总数", `${rows.length} 条`, "产品 + 季节窗口维度"],
    ["面授规则", `${faceToFaceRules} 条`, "需要结合班级窗口场地"],
    ["待补规则", `${rulesMissingWindow} 条`, "缺窗口、星期、时段或单次课"],
  ];
  content.innerHTML = `
    <section class="rules-hero compact-rules-hero">
      <div>
        <span>Rule Engine</span>
        <h2>产品窗口规则</h2>
        <p>按产品和季节窗口维护授课形式、可排星期、可排时段和连续课时。具体年份和班级日期边界到“班级排课窗口”维护。</p>
      </div>
      <div class="rules-health-card ${html(ruleTone)}">
        <span>规则健康度</span>
        <strong>${html(ruleStatus)}</strong>
        <em>重点检查适用范围、季节窗口、星期、时段和单次课。</em>
      </div>
    </section>

    <section class="rules-stat-grid" aria-label="排课规则关键统计">
      ${ruleStats.map(([label, value, detail]) => `
        <article class="rules-stat-card ${label === "待补规则" && rulesMissingWindow ? "warning" : ""}">
          <span>${html(label)}</span>
          <strong>${html(value)}</strong>
          <em>${html(detail)}</em>
        </article>
      `).join("")}
    </section>

    ${section(
      "产品窗口规则",
      "一行代表一个产品在一个季节窗口内的可排规则。",
      `
        <div class="rules-toolbar">
          <label><span>搜索</span><input data-action="rule-search" value="${html(selected.ruleSearch)}" placeholder="产品 / 规则 / 备注"></label>
          <label><span>季节窗口</span><select data-action="rule-window-filter">${selectOptions(ruleWindowFilterOptions(rows), selected.ruleWindowFilter, "全部窗口")}</select></label>
          <label><span>授课形式</span><select data-action="rule-delivery-filter">${selectOptions(ruleDeliveryFilterOptions(rows), selected.ruleDeliveryFilter, "全部形式")}</select></label>
          <label><span>状态</span><select data-action="rule-issue-filter">${selectLabeledOptions([{ value: "missing", label: "待补齐" }, { value: "complete", label: "已完整" }], selected.ruleIssueFilter, "全部状态")}</select></label>
          <div class="rules-toolbar-actions">
            <button type="button" data-action="clear-rule-filters">清空筛选</button>
            <button type="button" data-action="load-rule-templates">载入模板</button>
            <button type="button" data-action="add-rule">新增规则</button>
          </div>
        </div>
        <div class="rules-table-note">
          <strong>填写口径</strong>
          <span>${html(displayLimitNote("规则", displayedRows.length, filteredRows.length, rows.length))} 白天 4 小时连续课固定同一半天，2 节课固定同一个老师；全局停课日期到“年度窗口与课节”维护。</span>
        </div>
        ${ruleTable(displayedRows)}
      `,
    )}
  `;
}

function ruleSeasonWindowId(rule) {
  return rule.season_window_id || seasonWindowIdFromName(rule.window_name);
}

function ruleSeasonWindowName(rule) {
  return rule.window_name || seasonWindowName(rule.season_window_id);
}

function ruleMissingRequiredFields(rule) {
  return !ruleSeasonWindowId(rule)
    || !arrayValues(rule.allowed_periods).length
    || !arrayValues(rule.allowed_weekdays).length
    || !Number(rule.block_hours || rule.block_hours_override || 0);
}

function ruleWindowFilterOptions(rows) {
  const names = [...new Set(rows.map((rule) => ruleSeasonWindowName(rule)).filter(Boolean))];
  return names.sort(compareSeasonWindowValues);
}

function ruleDeliveryFilterOptions(rows) {
  return [...new Set(rows.map((rule) => rule.delivery_mode).filter(Boolean))]
    .sort((left, right) => left.localeCompare(right, "zh-CN"));
}

function ruleSearchText(rule) {
  return [
    rule.rule_id,
    rule.rule_name,
    rule.product_id,
    productName(rule.product_id),
    ...arrayValues(rule.product_ids).map((id) => `${id} ${productName(id)}`),
    ...arrayValues(rule.product_name_keywords),
    ruleSeasonWindowName(rule),
    rule.delivery_mode,
    ...arrayValues(rule.allowed_weekdays),
    ...arrayValues(rule.allowed_periods),
    rule.notes,
  ].filter(Boolean).join(" ").toLowerCase();
}

function ruleRowsForDisplay(rows) {
  const keyword = selected.ruleSearch.trim().toLowerCase();
  return rows
    .map((rule, index) => ({ rule, index }))
    .filter(({ rule }) => !keyword || ruleSearchText(rule).includes(keyword))
    .filter(({ rule }) => !selected.ruleWindowFilter || ruleSeasonWindowName(rule) === selected.ruleWindowFilter)
    .filter(({ rule }) => !selected.ruleDeliveryFilter || rule.delivery_mode === selected.ruleDeliveryFilter)
    .filter(({ rule }) => {
      if (selected.ruleIssueFilter === "missing") return ruleMissingRequiredFields(rule);
      if (selected.ruleIssueFilter === "complete") return !ruleMissingRequiredFields(rule);
      return true;
    });
}

function ruleScopeType(rule) {
  if (rule.scope_type) return rule.scope_type;
  if (rule.product_id || arrayValues(rule.product_ids).length) return "product_ids";
  if (arrayValues(rule.product_name_keywords).length) return "keywords";
  return "product_ids";
}

function ruleScopeControl(rule, index) {
  const scopeType = ruleScopeType(rule);
  const selectedProductId = rule.product_id || arrayValues(rule.product_ids)[0] || "";
  if (scopeType === "all") {
    return `<div class="rule-scope-stack"><span class="field-caption">适用于全部产品</span></div>`;
  }
  if (scopeType === "keywords") {
    return `
      <div class="rule-scope-stack">
        <input data-list="product_schedule_rules" data-index="${index}" data-field="product_name_keywords" value="${html(listText(rule.product_name_keywords))}" placeholder="关键词|关键词">
      </div>
    `;
  }
  return `
    <div class="rule-scope-stack">
      <select data-list="product_schedule_rules" data-index="${index}" data-field="product_id">${selectOptions(products(), selectedProductId, "选择产品")}</select>
    </div>
  `;
}

function ruleGuideHtml() {
  const items = [
    ["季节窗口", "寒假 1-2 月，春季 3-6 月，暑假 7-8 月，秋季 9-12 月。"],
    ["常规正课", "无忧秋跨秋季、寒假、春季、暑假、秋季；无忧寒跨寒假到秋季；无忧暑/暑假营跨暑假和秋季。"],
    ["专项导学", "导学产品多为春季/暑假/秋季直播或面授，按产品和季节窗口单独维护授课形式。"],
    ["白天 4 小时", "同一半天排 2 节时，要固定同一个老师，不能拆成上午 1 节加下午 1 节。"],
  ];
  return `
    <div class="rule-guide">
      ${items.map(([title, detail]) => `<div><strong>${html(title)}</strong><span>${html(detail)}</span></div>`).join("")}
    </div>
  `;
}

function blackoutTable() {
  const rows = state.global_blackout_dates || [];
  if (!rows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap segmented-table blackout-table">
      <table>
        ${colgroupHtml(["320px", "260px", "90px", "360px", "80px"])}
        <thead>
          ${columnGroupRow([
            { label: "停课项", span: 1 },
            { label: "日期范围", span: 1 },
            { label: "状态", span: 1 },
            { label: "说明操作", span: 2 },
          ])}
          <tr><th>停课项</th><th>日期范围</th><th>启用</th><th>备注</th><th></th></tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (item, index) => `
                <tr>
                  <td>
                    <div class="field-line">
                      <input data-list="global_blackout_dates" data-index="${index}" data-field="id" value="${html(item.id)}" placeholder="ID">
                      <input data-list="global_blackout_dates" data-index="${index}" data-field="name" value="${html(item.name)}" placeholder="名称">
                    </div>
                  </td>
                  <td>
                    <div class="field-line">
                      <input type="date" data-list="global_blackout_dates" data-index="${index}" data-field="start_date" value="${html(item.start_date)}">
                      <input type="date" data-list="global_blackout_dates" data-index="${index}" data-field="end_date" value="${html(item.end_date)}">
                    </div>
                  </td>
                  <td><label class="inline-check"><input type="checkbox" data-list="global_blackout_dates" data-index="${index}" data-field="is_active" ${item.is_active ? "checked" : ""}>启用</label></td>
                  <td><input data-list="global_blackout_dates" data-index="${index}" data-field="notes" value="${html(item.notes)}"></td>
                  <td><button type="button" class="small danger" data-action="delete-blackout" data-index="${index}">删除</button></td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function ruleTable(rowEntries) {
  if (!rowEntries.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap rule-edit-table">
      <table>
        <colgroup>
          <col style="width: 82px">
          <col style="width: 220px">
          <col style="width: 126px">
          <col style="width: 300px">
          <col style="width: 128px">
          <col style="width: 104px">
          <col style="width: 430px">
          <col style="width: 188px">
          <col style="width: 92px">
          <col style="width: 84px">
          <col style="width: 98px">
          <col style="width: 88px">
          <col style="width: 88px">
          <col style="width: 88px">
          <col style="width: 102px">
          <col style="width: 104px">
          <col style="width: 98px">
          <col style="width: 280px">
          <col style="width: 76px">
        </colgroup>
        <thead>
          <tr class="column-group-row">
            <th colspan="2">规则</th>
            <th colspan="2">适用产品</th>
            <th colspan="2">窗口与授课</th>
            <th colspan="2">可排时间</th>
            <th colspan="6">课时限制</th>
            <th colspan="3">硬约束</th>
            <th colspan="2">备注操作</th>
          </tr>
          <tr>
            <th>状态</th>
            <th>规则名称</th>
            <th>匹配方式</th>
            <th>产品 / 关键词</th>
            <th>季节窗口</th>
            <th>授课形式</th>
            <th>可排星期</th>
            <th>可排时段</th>
            <th>单次小时</th>
            <th>单次节数</th>
            <th>每日小时</th>
            <th>每日次数</th>
            <th>周下限</th>
            <th>周上限</th>
            <th>同半天连续</th>
            <th>4小时同老师</th>
            <th>开课后生效</th>
            <th>备注</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${rowEntries
            .map(({ rule, index }) => {
              const missing = ruleMissingRequiredFields(rule);
              const ruleId = rule.rule_id ? `ID：${rule.rule_id}` : "";
              return `
                <tr class="${missing ? "missing" : "complete"}">
                  <td><span class="rule-status-pill ${missing ? "missing" : "complete"}">${html(missing ? "待补齐" : "已完整")}</span></td>
                  <td>
                    <input data-list="product_schedule_rules" data-index="${index}" data-field="rule_name" value="${html(rule.rule_name || rule.rule_id)}" placeholder="规则名称">
                    ${ruleId ? `<span class="field-caption">${html(ruleId)}</span>` : ""}
                  </td>
                  <td><select data-list="product_schedule_rules" data-index="${index}" data-field="scope_type">${selectLabeledOptions(ruleScopeSelectOptions(), ruleScopeType(rule), "匹配方式")}</select></td>
                  <td>${ruleScopeControl(rule, index)}</td>
                  <td><select data-list="product_schedule_rules" data-index="${index}" data-field="season_window_id">${selectLabeledOptions(seasonWindowSelectOptions(), ruleSeasonWindowId(rule), "季节")}</select></td>
                  <td><select data-list="product_schedule_rules" data-index="${index}" data-field="delivery_mode">${selectOptions(["面授", "直播", "混合"], rule.delivery_mode, "形式")}</select></td>
                  <td>${listCheckboxOptions("product_schedule_rules", index, "allowed_weekdays", weekdays(), rule.allowed_weekdays)}</td>
                  <td>${listCheckboxOptions("product_schedule_rules", index, "allowed_periods", schedulePeriods(), rule.allowed_periods)}</td>
                  <td><input type="number" step="0.5" data-list="product_schedule_rules" data-index="${index}" data-field="block_hours" value="${html(rule.block_hours || rule.block_hours_override || "")}" placeholder="小时"></td>
                  <td><input type="number" data-list="product_schedule_rules" data-index="${index}" data-field="lessons_per_block" value="${html(rule.lessons_per_block || "")}" placeholder="节数"></td>
                  <td><input type="number" step="0.5" data-list="product_schedule_rules" data-index="${index}" data-field="max_hours_per_class_per_day" value="${html(rule.max_hours_per_class_per_day || "")}" placeholder="小时"></td>
                  <td><input type="number" data-list="product_schedule_rules" data-index="${index}" data-field="max_blocks_per_class_per_day" value="${html(rule.max_blocks_per_class_per_day || "")}" placeholder="次数"></td>
                  <td><input type="number" step="0.5" data-list="product_schedule_rules" data-index="${index}" data-field="min_weekly_hours" value="${html(rule.min_weekly_hours || "")}" placeholder="小时"></td>
                  <td><input type="number" step="0.5" data-list="product_schedule_rules" data-index="${index}" data-field="max_weekly_hours" value="${html(rule.max_weekly_hours || "")}" placeholder="小时"></td>
                  <td>${editableCheckboxCell("product_schedule_rules", index, "same_half_day_block_required", rule.same_half_day_block_required, "启用")}</td>
                  <td>${editableCheckboxCell("product_schedule_rules", index, "same_half_day_4h_same_teacher_required", rule.same_half_day_4h_same_teacher_required, "启用")}</td>
                  <td>${editableCheckboxCell("product_schedule_rules", index, "effective_after_class_start", rule.effective_after_class_start, "启用")}</td>
                  <td><textarea data-list="product_schedule_rules" data-index="${index}" data-field="notes">${html(rule.notes)}</textarea></td>
                  <td><button type="button" class="small danger" data-action="delete-rule" data-index="${index}">删除</button></td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function classSearchText(cls) {
  return [
    cls.id,
    cls.name,
    cls.product_id,
    productName(cls.product_id),
    cls.project,
    cls.product_line,
    cls.sub_product,
    cls.product_system,
    cls.course_nature,
    cls.subject_category,
    cls.subject,
    arrayValues(cls.stages).join(" "),
    cls.exam_season,
    cls.exam_month,
    classActualScheduleWindowIds(cls).join(" "),
    cls.suite_code,
    cls.capacity_type,
    cls.size,
    cls.start_date,
    cls.end_date,
    arrayValues(cls.preferred_teaching_area_ids).map((areaId) => teachingAreaSearchText(areaId)).join(" "),
    arrayValues(cls.preferred_room_ids).map(roomName).join(" "),
    cls.notes,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function classMatchesSearch(cls, keyword) {
  const tokens = String(keyword || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const text = classSearchText(cls);
  return tokens.every((token) => text.includes(token));
}

function classTeacherMatchesSearch(cls, keyword) {
  const tokens = String(keyword || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const text = [cls.id, cls.name].filter(Boolean).join(" ").toLowerCase();
  return tokens.every((token) => text.includes(token));
}

function classProductFilterOptions() {
  const seen = new Set();
  return (state.classes || [])
    .filter((cls) => cls.product_id)
    .sort((a, b) => productPickerLabel(a.product_id).localeCompare(productPickerLabel(b.product_id), "zh-Hans-CN"))
    .map((cls) => ({ id: cls.product_id, name: productName(cls.product_id) || cls.product_id }))
    .filter((item) => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
}

function classSubjectFilterOptions() {
  return [...new Set((state.classes || []).map((cls) => cls.subject).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));
}

function classTeacherPageClasses() {
  return (state.classes || [])
    .filter((cls) => classTeacherMatchesSearch(cls, selected.classTeacherSearch));
}

function compactClassPickerItem(cls, active = false) {
  const classId = cls.id || "";
  const className = cls.name || "未填写班级名称";
  return `
    <button type="button" class="record-item class-picker-item ${active ? "active" : ""}" data-action="select-class" data-id="${html(classId)}" aria-label="${html([classId, className].filter(Boolean).join(" "))}">
      <strong class="class-picker-code">${html(classId || "未填写班级编码")}</strong>
      <span class="class-picker-name">${html(className)}</span>
    </button>
  `;
}

function classOptionLabel(classId) {
  const cls = (state.classes || []).find((item) => item.id === classId);
  if (!cls) return classId || "";
  return [cls.id, cls.name].filter(Boolean).join(" / ");
}

function classOptions() {
  return (state.classes || [])
    .slice()
    .sort((a, b) => String(a.suite_code || "").localeCompare(String(b.suite_code || ""), "zh-CN") || String(a.id).localeCompare(String(b.id), "zh-CN"))
    .map((cls) => ({ id: cls.id, label: classOptionLabel(cls.id) }));
}

function classCodeDatalistOptions() {
  return (state.classes || [])
    .slice()
    .sort((a, b) => String(a.id || "").localeCompare(String(b.id || ""), "zh-CN"))
    .map((cls) => `<option value="${html(cls.id)}" label="${html(classOptionLabel(cls.id))}"></option>`)
    .join("");
}

function classIdFromPickerValue(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const exact = (state.classes || []).find((cls) => cls.id === text);
  if (exact) return exact.id;
  return (state.classes || []).find((cls) => classOptionLabel(cls.id) === text)?.id || "";
}

function addClassConflictClass(groupIndex, classId) {
  const group = state.class_conflict_groups?.[groupIndex];
  if (!group || !classId) return false;
  const current = uniqueList(group.class_ids);
  if (current.includes(classId)) return false;
  group.class_ids = [...current, classId];
  return true;
}

function removeClassConflictClass(groupIndex, classId) {
  const group = state.class_conflict_groups?.[groupIndex];
  if (!group) return false;
  group.class_ids = uniqueList(group.class_ids).filter((value) => value !== classId);
  return true;
}

function classConflictClassToken(classId, groupIndex) {
  return `
    <span class="picker-token conflict-class-token" title="${html(classOptionLabel(classId))}">
      <span>${html(classId)}</span>
      <button type="button" data-action="remove-class-conflict-class" data-index="${groupIndex}" data-value="${html(classId)}" aria-label="移除 ${html(classId)}">x</button>
    </span>
  `;
}

function classConflictClassPicker(group, groupIndex) {
  const selectedClassIds = uniqueList(group.class_ids);
  return `
    <div class="token-picker conflict-class-picker">
      <input data-action="class-conflict-class-picker" data-index="${groupIndex}" value="" list="classConflictClassChoices" placeholder="输入班级编码搜索并选择添加">
      <div class="token-list conflict-class-token-list" aria-label="已选择互斥班级编码">
        ${selectedClassIds.length
          ? selectedClassIds.map((classId) => classConflictClassToken(classId, groupIndex)).join("")
          : `<span class="token-empty">未选择班级编码</span>`}
      </div>
    </div>
  `;
}

function suiteConflictGroupsFromClasses() {
  const groups = new Map();
  for (const cls of state.classes || []) {
    if (!cls.id || !cls.suite_code) continue;
    const key = `${cls.exam_season || ""}__${cls.suite_code}`;
    if (!groups.has(key)) {
      groups.set(key, {
        id: `SUITE_${key}`,
        name: `${cls.exam_season ? `${cls.exam_season} ` : ""}${cls.suite_code} 套班互斥`,
        exam_season: cls.exam_season || "",
        suite_code: cls.suite_code || "",
        class_ids: [],
        is_conflict_group_active: true,
        conflict_source: "套班编码",
        notes: "按套班编码自动生成",
      });
    }
    groups.get(key).class_ids.push(cls.id);
  }
  return [...groups.values()]
    .map((group) => ({ ...group, class_ids: uniqueList(group.class_ids) }))
    .filter((group) => group.class_ids.length >= 2)
    .sort((a, b) => a.id.localeCompare(b.id, "zh-CN"));
}

function conflictSearchText(group) {
  return [
    group.id,
    group.name,
    group.exam_season,
    group.suite_code,
    conflictGroupSource(group),
    arrayValues(group.class_ids).map(classOptionLabel).join(" "),
    group.notes,
  ].filter(Boolean).join(" ").toLowerCase();
}

function renderClassConflicts() {
  state.class_conflict_groups = state.class_conflict_groups || [];
  const groups = state.class_conflict_groups;
  const classIdSet = new Set((state.classes || []).map((cls) => cls.id).filter(Boolean));
  const keyword = selected.classConflictSearch.trim().toLowerCase();
  const matchedRows = groups
    .map((group, index) => ({ group, index }))
    .filter(({ group }) => !keyword || conflictSearchText(group).includes(keyword));
  const rows = limitDisplayedRows(matchedRows, visibleRowLimits.classConflicts);
  const activeGroups = groups.filter(conflictGroupIsActive).length;
  const autoGroups = groups.filter((group) => conflictGroupSource(group) === "套班编码").length;
  const manualGroups = groups.filter((group) => conflictGroupSource(group) !== "套班编码").length;
  const generatedSuiteGroups = suiteConflictGroupsFromClasses().length;
  const invalidActiveGroups = groups.filter((group) => conflictGroupIsActive(group) && uniqueList(group.class_ids).length < 2).length;
  const missingClassRefs = groups.reduce((sum, group) => {
    return sum + uniqueList(group.class_ids).filter((classId) => !classIdSet.has(classId)).length;
  }, 0);
  const conflictWarnings = invalidActiveGroups + missingClassRefs;
  const conflictTone = conflictWarnings ? "warning" : groups.length ? "ok" : "neutral";
  const conflictHealthText = groups.length
    ? conflictWarnings
      ? `${conflictWarnings} 项互斥口径待确认`
      : "互斥门禁已就绪"
    : "还没有互斥组";
  const conflictStats = [
    ["匹配互斥组", `${matchedRows.length} 个`, "搜索后的互斥组"],
    ["启用中", `${activeGroups} 个`, "会参与排课硬冲突检查"],
    ["套班生成", `${autoGroups} 个`, "按套班编码自动补充的互斥组"],
    ["手动维护", `${manualGroups} 个`, "人工补充的特殊互斥关系"],
    ["待确认", `${conflictWarnings} 项`, "少于 2 个班级或引用失效"],
  ];

  content.innerHTML = `
    <section class="class-conflict-hero">
      <div>
        <span>Conflict Gate</span>
        <h2>班级互斥关系</h2>
        <p>同一互斥组内的班级不能安排在同一课节；套班关系可自动补齐，特殊关系手动维护。</p>
      </div>
      <div class="class-conflict-health ${html(conflictTone)}">
        <span>互斥门禁健康度</span>
        <strong>${html(conflictHealthText)}</strong>
        <em>${html(displayLimitNote("互斥组", rows.length, matchedRows.length, groups.length))}</em>
      </div>
    </section>

    <section class="class-conflict-stat-grid" aria-label="班级互斥关键统计">
      ${conflictStats.map(([label, value, detail]) => `
        <article class="class-conflict-stat-card ${label === "待确认" && conflictWarnings ? "warning" : ""}">
          <span>${html(label)}</span>
          <strong>${html(value)}</strong>
          <em>${html(detail)}</em>
        </article>
      `).join("")}
    </section>

    ${section(
      "班级互斥关系",
      "维护不能排在同一课节的班级组。",
      `
        <div class="form-row">
          <label><span>搜索互斥组</span><input data-action="class-conflict-search" value="${html(selected.classConflictSearch)}" placeholder="套班编码 / 班级 / 科目 / 备注"></label>
          <div class="field-line narrow-fields">
            <button type="button" data-action="sync-suite-conflicts">按套班编码补充</button>
            <button type="button" data-action="add-class-conflict">新增互斥组</button>
          </div>
        </div>
        <div class="field-caption">${html(displayLimitNote("互斥组", rows.length, matchedRows.length, groups.length))} 当前班级数据可推导 ${generatedSuiteGroups} 个套班互斥组；每个启用互斥组至少需要 2 个班级。</div>
        ${classConflictTable(rows)}
      `,
    )}
  `;
}

function classConflictTable(rows) {
  if (!rows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap segmented-table class-conflict-table">
      <table>
        ${colgroupHtml(["260px", "340px", "420px", "90px", "280px", "80px"])}
        <thead>
          ${columnGroupRow([
            { label: "互斥组", span: 1 },
            { label: "来源", span: 1 },
            { label: "班级范围", span: 1 },
            { label: "状态", span: 1 },
            { label: "备注操作", span: 2 },
          ])}
          <tr>
            <th>互斥组</th><th>来源/套班</th><th>互斥班级</th><th>启用</th><th>备注</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              ({ group, index }) => `
                <tr>
                  <td>
                    <div class="class-conflict-name">
                      <input data-list="class_conflict_groups" data-index="${index}" data-field="name" value="${html(group.name)}" placeholder="互斥组名称">
                      <span>${html(group.id || "自动ID")}</span>
                    </div>
                  </td>
                  <td>
                    <div class="class-conflict-tags">
                      <select data-list="class_conflict_groups" data-index="${index}" data-field="conflict_source">${selectOptions(["套班编码", "手动"], conflictGroupSource(group), "来源")}</select>
                      <input data-list="class_conflict_groups" data-index="${index}" data-field="suite_code" value="${html(group.suite_code)}" placeholder="套班编码">
                      <input data-list="class_conflict_groups" data-index="${index}" data-field="exam_season" value="${html(group.exam_season)}" placeholder="考季">
                    </div>
                  </td>
                  <td>
                    ${classConflictClassPicker(group, index)}
                    <div class="field-caption">已选 ${arrayValues(group.class_ids).length} 个班级</div>
                  </td>
                  <td><label class="inline-check"><input type="checkbox" data-list="class_conflict_groups" data-index="${index}" data-field="is_conflict_group_active" ${conflictGroupIsActive(group) ? "checked" : ""}>启用</label></td>
                  <td><textarea data-list="class_conflict_groups" data-index="${index}" data-field="notes">${html(group.notes)}</textarea></td>
                  <td><button type="button" class="small danger" data-action="delete-class-conflict" data-index="${index}">删除</button></td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
      <datalist id="classConflictClassChoices">${classCodeDatalistOptions()}</datalist>
    </div>
  `;
}

function renderClassMeta() {
  for (const item of state.classes || []) applyClassAutoTags(item, false);
  const keyword = selected.classSearch.trim().toLowerCase();
  const allClasses = state.classes || [];
  const matchedRows = state.classes
    .map((cls, index) => ({ cls, index }))
    .filter(({ cls }) => classMatchesSearch(cls, keyword))
    .filter(({ cls }) => productMatchesTagFilters(cls, selected.classMetaFilters));
  const rows = limitDisplayedRows(matchedRows, visibleRowLimits.classMeta);
  const autoClasses = allClasses.filter((cls) => !cls.is_schedule_locked).length;
  const lockedClasses = allClasses.filter((cls) => cls.is_schedule_locked).length;
  const suiteCount = new Set(allClasses.map((cls) => cls.suite_code).filter(Boolean)).size;
  const missingScopeClasses = allClasses.filter((cls) => {
    return !cls.product_id
      || !cls.suite_code
      || !cls.subject
      || !cls.exam_season
      || !cls.start_date
      || !cls.end_date
      || !arrayValues(cls.stages).length;
  }).length;
  const scopeTone = missingScopeClasses ? "warning" : allClasses.length ? "ok" : "neutral";
  const scopeHealthText = allClasses.length
    ? missingScopeClasses
      ? `${missingScopeClasses} 个班级待补口径`
      : "班级范围口径已完整"
    : "还没有班级数据";
  const scopeStats = [
    ["匹配班级", `${matchedRows.length} 个`, "搜索和标签筛选后的结果"],
    ["班级总数", `${allClasses.length} 个`, "本轮维护的班级"],
    ["自动排课", `${autoClasses} 个`, "未锁定、可进入自动排课流程"],
    ["手动锁定", `${lockedClasses} 个`, "已固定，不参与自动移动"],
    ["套班数", `${suiteCount} 个`, "用于互斥关系"],
    ["待补口径", `${missingScopeClasses} 个`, "缺产品、日期边界、套班、科目、考季或阶段"],
  ];

  content.innerHTML = `
    <section class="class-scope-hero">
      <div>
        <span>Scope Foundation</span>
        <h2>班级基础信息</h2>
        <p>维护班级所属产品、考季套班、人数、阶段、日期范围和默认场地；年度窗口内的具体可排日期、时段和场地到“班级排课窗口”维护。</p>
      </div>
      <div class="class-scope-health ${html(scopeTone)}">
        <span>范围健康度</span>
        <strong>${html(scopeHealthText)}</strong>
        <em>${html(displayLimitNote("班级", rows.length, matchedRows.length, allClasses.length))}</em>
      </div>
    </section>

    <section class="class-scope-stat-grid" aria-label="班级范围关键统计">
      ${scopeStats.map(([label, value, detail]) => `
        <article class="class-scope-stat-card ${label === "待补口径" && missingScopeClasses ? "warning" : ""}">
          <span>${html(label)}</span>
          <strong>${html(value)}</strong>
          <em>${html(detail)}</em>
        </article>
      `).join("")}
    </section>

    ${section(
      "班级基础信息",
      "只维护班级基础口径；窗口、老师和互斥关系分别到对应页面维护。",
      `
        <div class="form-row">
          <label><span>搜索班级</span><input data-action="class-search" value="${html(selected.classSearch)}" placeholder="班级 / 产品 / 科目 / 考季 / 套班编码 / 教学区 / 教室"></label>
          <div class="field-line narrow-fields">
            <button type="button" data-action="clear-class-filters">清除筛选</button>
            <button type="button" data-action="download-classes">下载班级表</button>
            <button type="button" data-action="import-classes">导入班级表</button>
            <button type="button" data-action="add-class">新增班级</button>
          </div>
          <input type="file" data-action="import-classes-file" accept=".csv,text/csv" hidden>
        </div>
        ${productTagFilterControls("class-meta-tag-filter", selected.classMetaFilters, allClasses, matchedRows.length, allClasses.length, "clear-class-filters", false, "班级")}
        <div class="field-caption">${html(displayLimitNote("班级", rows.length, matchedRows.length, allClasses.length))} 阶段从所属产品课程中选择；具体可排年度窗口由实际日期边界生成后在“班级排课窗口”维护。</div>
        ${classMetaTable(rows)}
        ${productPickerDatalist()}
        ${teachingAreaPickerDatalist()}
      `,
    )}
  `;
}

function classMetaTable(rows) {
  if (!rows.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  return `
    <div class="table-wrap class-meta-table">
      <table>
        <colgroup>
          <col style="width: 360px">
          <col style="width: 300px">
          <col style="width: 130px">
          <col style="width: 120px">
          <col style="width: 120px">
          <col style="width: 110px">
          <col style="width: 80px">
          <col style="width: 260px">
          <col style="width: 132px">
          <col style="width: 100px">
          <col style="width: 132px">
          <col style="width: 112px">
          <col style="width: 132px">
          <col style="width: 100px">
          <col style="width: 320px">
          <col style="width: 360px">
          <col style="width: 170px">
          <col style="width: 220px">
          <col style="width: 130px">
        </colgroup>
        <thead>
          <tr class="column-group-row">
            <th colspan="3">基础信息</th>
            <th colspan="5">考试与阶段</th>
            <th colspan="6">日期边界</th>
            <th colspan="3">场地与状态</th>
            <th colspan="2">备注操作</th>
          </tr>
          <tr>
            <th>班级</th><th>所属产品</th><th>科目</th><th>考季</th><th>考试月份</th><th>套班编码</th><th>人数</th><th>阶段</th><th>最早日期</th><th>最早时段</th><th>固定首课日期</th><th>固定首课时段</th><th>最晚日期</th><th>最晚时段</th><th>默认教学区</th><th>默认教室</th><th>排课状态</th><th>备注</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              ({ cls }) => `
                <tr>
                  <td>
                    <div class="field-line wide-fields">
                      <input data-entity="class" data-id="${html(cls.id)}" data-field="id" value="${html(cls.id)}" placeholder="班级 ID">
                      <input data-entity="class" data-id="${html(cls.id)}" data-field="name" value="${html(cls.name)}" placeholder="班级名称">
                    </div>
                  </td>
                  <td>${classProductPicker(cls)}</td>
                  <td><input value="${html(cls.subject)}" disabled title="由所属产品带出"></td>
                  <td><select data-entity="class" data-id="${html(cls.id)}" data-field="exam_season">${selectOptions(classExamSeasonOptions(cls), String(cls.exam_season || ""), "请选择")}</select></td>
                  <td><input data-entity="class" data-id="${html(cls.id)}" data-field="exam_month" value="${html(cls.exam_month)}" placeholder="如 2026-12"></td>
                  <td><input data-entity="class" data-id="${html(cls.id)}" data-field="suite_code" value="${html(cls.suite_code)}" placeholder="套班编码"></td>
                  <td><input type="number" data-entity="class" data-id="${html(cls.id)}" data-field="size" value="${html(cls.size)}"></td>
                  <td>${classStageCheckboxOptions(cls)}</td>
                  <td><input type="date" data-entity="class" data-id="${html(cls.id)}" data-field="start_date" value="${html(cls.start_date)}"></td>
                  <td><select data-entity="class" data-id="${html(cls.id)}" data-field="start_period">${selectOptions(["AM", "PM", "EVENING"], cls.start_period, "不限制")}</select></td>
                  <td><input type="date" data-entity="class" data-id="${html(cls.id)}" data-field="first_lesson_date" value="${html(cls.first_lesson_date)}"></td>
                  <td><select data-entity="class" data-id="${html(cls.id)}" data-field="first_lesson_period">${selectOptions(["AM", "PM", "EVENING"], cls.first_lesson_period, "不限制")}</select></td>
                  <td><input type="date" data-entity="class" data-id="${html(cls.id)}" data-field="end_date" value="${html(cls.end_date)}"></td>
                  <td><select data-entity="class" data-id="${html(cls.id)}" data-field="end_period">${selectOptions(["AM", "PM", "EVENING"], cls.end_period, "不限制")}</select></td>
                  <td>${classTeachingAreaPicker(cls)}</td>
                  <td>
                    ${classRoomPicker(cls)}
                    ${classRoomRequirementToggle(cls)}
                  </td>
                  <td>${classScheduleLockedToggle(cls)}</td>
                  <td><input data-entity="class" data-id="${html(cls.id)}" data-field="notes" value="${html(cls.notes)}"></td>
                  <td>
                    <div class="field-line narrow-fields">
                      <button type="button" class="small" data-action="edit-class-teachers" data-id="${html(cls.id)}">老师</button>
                      <button type="button" class="small danger" data-action="delete-class" data-id="${html(cls.id)}">删除</button>
                    </div>
                  </td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function classTeacherSummary(cls) {
  const assignments = cls.teacher_assignments || [];
  const shared = assignments.filter(teacherAssignmentIsShared).length;
  const sharedMissingSource = assignments.filter(teacherAssignmentMissingSource).length;
  const missing = assignments.filter((assignment) => !teacherAssignmentIsShared(assignment) && !assignment.teacher_id && !assignment.teacher_name).length;
  return {
    total: assignments.length,
    missing,
    shared,
    sharedMissingSource,
    filled: Math.max(assignments.length - missing, 0),
  };
}

function classTeacherContextChips(cls) {
  const chips = [
    ["产品", productName(cls.product_id)],
    ["科目", cls.subject],
    ["阶段", sortStageValues(arrayValues(cls.stages)).join("/")],
    ["套班", cls.suite_code],
    ["年度窗口", listText(classActualScheduleWindowIds(cls))],
  ];
  const content = chips
    .filter(([, value]) => value !== undefined && value !== null && String(value).trim())
    .map(([label, value]) => `<span class="info-chip"><b>${html(label)}</b>${html(value)}</span>`)
    .join("");
  return content || `<span class="muted">暂无班级老师安排口径</span>`;
}

function classStatusPills(cls) {
  const summary = classTeacherSummary(cls);
  const teacherClass = summary.missing || summary.sharedMissingSource || !summary.total ? "warning" : "ok";
  return `
    <span class="status-pill ${teacherClass}">${html(summary.total ? `老师 ${summary.filled}/${summary.total}` : "老师未同步")}</span>
    ${summary.shared ? `<span class="status-pill ok">${html(`共享 ${summary.shared}`)}</span>` : ""}
    ${summary.sharedMissingSource ? `<span class="status-pill warning">${html(`共享缺主班 ${summary.sharedMissingSource}`)}</span>` : ""}
    <span class="status-pill">${html(cls.is_schedule_locked ? "手动锁定" : "自动排课")}</span>
  `;
}

function renderClasses() {
  for (const item of state.classes || []) applyClassAutoTags(item, false);
  const allClasses = state.classes || [];
  const matchedClassList = classTeacherPageClasses();
  const classList = limitDisplayedRows(matchedClassList, visibleRowLimits.classTeachers);
  if (selected.classId && !classList.some((item) => item.id === selected.classId)) {
    selected.classId = classList[0]?.id || "";
  }
  if (!selected.classId && classList[0]) selected.classId = classList[0].id;
  const cls = classList.find((item) => item.id === selected.classId) || null;
  const classSummaries = allClasses.map((item) => classTeacherSummary(item));
  const missingAssignments = classSummaries.reduce((sum, summary) => sum + summary.missing, 0);
  const sharedAssignments = classSummaries.reduce((sum, summary) => sum + summary.shared, 0);
  const sharedMissingSource = classSummaries.reduce((sum, summary) => sum + summary.sharedMissingSource, 0);
  const classesWithoutAssignments = classSummaries.filter((summary) => !summary.total).length;
  const selectedSummary = cls ? classTeacherSummary(cls) : null;
  const teacherGapCount = missingAssignments + sharedMissingSource + classesWithoutAssignments;
  const teacherTone = teacherGapCount ? "warning" : allClasses.length ? "ok" : "neutral";
  const teacherHealthText = allClasses.length
    ? teacherGapCount
      ? `${teacherGapCount} 项老师口径待确认`
      : "老师安排已完整"
    : "还没有班级数据";
  const summaryItems = [
    ["匹配班级", `${matchedClassList.length}/${allClasses.length}`],
    ["缺老师", `${missingAssignments}`],
    ["共享课表", `${sharedAssignments}`],
    ["共享缺主班", `${sharedMissingSource}`],
  ];
  const summarySubtitle = selectedSummary
    ? `当前选中：${cls.name || cls.id} · 老师 ${selectedSummary.filled}/${selectedSummary.total}${selectedSummary.shared ? ` · 共享 ${selectedSummary.shared}` : ""}`
    : "先选择一个班级，再维护老师安排。";
  const summaryBar = `
    <div class="class-teacher-summary-bar ${html(teacherTone)}">
      <div>
        <strong>${html(teacherHealthText)}</strong>
        <span>${html(summarySubtitle)}</span>
      </div>
      <div class="class-teacher-summary-metrics">
        ${summaryItems.map(([label, value]) => `<span><b>${html(value)}</b>${html(label)}</span>`).join("")}
      </div>
    </div>
  `;
  const list = `
    <div class="list-panel class-teacher-list">
      <div class="list-tools">
        <label><span>搜索班级</span><input data-action="class-teacher-search" value="${html(selected.classTeacherSearch)}" placeholder="班级编码 / 班级名称"></label>
      </div>
      <div class="record-list">
        ${classList.length
          ? classList.map((item) => compactClassPickerItem(item, item.id === selected.classId)).join("")
          : document.querySelector("#emptyStateTemplate").innerHTML}
      </div>
    </div>
  `;

  const detail = cls
    ? `
      <div class="class-editor teacher-assignment-panel">
        <div class="class-editor-head">
          <div class="class-title-block">
            <strong>${html(cls.name || cls.id)}</strong>
            <span>${html([cls.id, productName(cls.product_id), cls.subject].filter(Boolean).join(" · "))}</span>
          </div>
          <div class="class-status-pills">${classStatusPills(cls)}</div>
        </div>
        <div class="teacher-context-strip">${classTeacherContextChips(cls)}</div>
        <div class="teacher-assignment-toolbar">
          <div>
            <strong>老师安排</strong>
            <span>本班实际排课填老师；共享课表只填实际排课班级。</span>
          </div>
          <div>
            <button type="button" data-action="sync-teachers">同步当前班级</button>
            <button type="button" data-action="sync-all-teachers">同步全部班级</button>
          </div>
        </div>
        ${teacherTable(cls)}
      </div>
    `
    : document.querySelector("#emptyStateTemplate").innerHTML;

  content.innerHTML = `
    ${section("班级老师安排", displayLimitNote("班级", classList.length, matchedClassList.length, allClasses.length), `${summaryBar}<div class="split class-teacher-split">${list}<div>${detail}</div></div>`)}
  `;
}

function renderClassesWithSearchFocus(cursorPosition = null) {
  renderClasses();
  const searchInput = content.querySelector('input[data-action="class-teacher-search"]');
  if (!searchInput) return;
  searchInput.focus();
  const nextCursor = cursorPosition ?? searchInput.value.length;
  searchInput.setSelectionRange(nextCursor, nextCursor);
}

function scheduleClassTeacherSearchRender(cursorPosition = null) {
  window.clearTimeout(classTeacherSearchRenderTimer);
  classTeacherSearchRenderTimer = window.setTimeout(() => {
    renderClassesWithSearchFocus(cursorPosition);
  }, 120);
}

function flushClassTeacherSearchRender(cursorPosition = null) {
  window.clearTimeout(classTeacherSearchRenderTimer);
  renderClassesWithSearchFocus(cursorPosition);
}

function teacherTable(cls) {
  const assignments = cls.teacher_assignments || [];
  if (!assignments.length) return document.querySelector("#emptyStateTemplate").innerHTML;
  const sortedAssignments = assignments
    .map((assignment, index) => ({ assignment, index }))
    .sort(compareTeacherAssignmentRows);
  return `
    <div class="assignment-note compact">
      <strong>维护口径</strong>
      <span>本班实际排课维护任课老师；共享课表维护实际排课班级。教师请假、兼职限制等统一到“教师不可排时间”维护。</span>
    </div>
    <div class="table-wrap segmented-table teacher-assignment-wrap">
      <table class="teacher-assignment-table">
        ${colgroupHtml(["220px", "210px", "360px", "330px", "80px"])}
        <thead>
          ${columnGroupRow([
            { label: "课程", span: 1 },
            { label: "课表关系", span: 1 },
            { label: "老师/主班", span: 1 },
            { label: "备注", span: 1 },
            { label: "操作", span: 1 },
          ])}
          <tr>
            <th>课程</th><th>课表处理</th><th>任课老师 / 实际排课班级</th><th>备注与例外</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${sortedAssignments
            .map(({ assignment, index }) => {
              const mode = assignmentScheduleMode(assignment);
              const isShared = mode === "共享课表";
              const sourceClassId = assignmentReferenceClassId(assignment, cls);
              const inheritedLabel = sourceClassId ? classOptionLabel(sourceClassId) : "";
              return `
                <tr class="${isShared ? "shared-assignment-row" : ""}">
                  <td>${html(teacherCourseLabel(assignment))}</td>
                  <td><select data-assignment-index="${index}" data-field="class_schedule_mode">${selectLabeledOptions(teacherAssignmentScheduleModeOptions, mode, "请选择")}</select></td>
                  <td>
                    ${isShared
                      ? `
                        <div class="teacher-picker">
                          <input data-assignment-index="${index}" data-field="actual_scheduled_class_id" value="${html(sourceClassId)}" list="classTeacherSourceClasses" placeholder="输入实际排课班级">
                          ${inheritedLabel ? `<div class="field-caption">${html(inheritedLabel)}</div>` : ""}
                          <span class="assignment-inherit-note">共享该班课表，不单独生成课次。</span>
                        </div>
                      `
                      : `
                        <div class="teacher-picker">
                          <input data-assignment-index="${index}" data-field="teacher_name" value="${html(assignment.teacher_name)}" list="teacherNames" placeholder="输入教师姓名">
                          <input data-assignment-index="${index}" data-field="teacher_id" value="${html(assignment.teacher_id)}" list="teacherIds" placeholder="员工ID自动带出/可手动确认">
                          ${teacherMatchSelector(assignment, index)}
                        </div>
                      `}
                  </td>
                  <td>
                    <div class="assignment-note-stack">
                      <input data-assignment-index="${index}" data-field="notes" value="${html(assignment.notes)}" placeholder="备注">
                      ${isShared
                        ? ""
                        : `<input data-assignment-index="${index}" data-field="assignment_extra_time_requirement" value="${html(assignment.assignment_extra_time_requirement || "")}" placeholder="本安排额外时间要求（可选）">`}
                    </div>
                  </td>
                  <td><button type="button" class="small danger" data-action="delete-assignment" data-index="${index}">删除</button></td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
      <datalist id="classTeacherSourceClasses">${classCodeDatalistOptions()}</datalist>
      <datalist id="teacherNames">
        ${teacherNameOptions().map((teacher) => `<option value="${html(teacher.name)}">${html(teacherDetailLabel(teacher))}</option>`).join("")}
      </datalist>
      <datalist id="teacherIds">
        ${teacherChoices().map((teacher) => `<option value="${html(teacher.id)}">${html(`${teacher.name}${teacherDetailLabel(teacher) ? ` / ${teacherDetailLabel(teacher)}` : ""}`)}</option>`).join("")}
      </datalist>
    </div>
  `;
}

function classSubjectControl(cls) {
  const product = productById(cls.product_id);
  if (product?.subject) {
    return `<input value="${html(product.subject)}" disabled>`;
  }
  return `<select data-entity="class" data-id="${html(cls.id)}" data-field="subject">${selectOptions(productSubjects(cls.product_id), cls.subject, "不限制")}</select>`;
}

function teacherMatchSelector(assignment, index) {
  const matches = teacherNameMatches(assignment.teacher_name);
  const needsChoice = matches.length > 1 && !matches.some((teacher) => teacher.id === assignment.teacher_id);
  if (!needsChoice) return "";
  return `
    <div class="teacher-match">
      <span>存在同名老师，请选择员工ID</span>
      <select data-assignment-index="${index}" data-field="teacher_match_id">
        <option value="">选择老师</option>
        ${matches
          .map((teacher) => `<option value="${html(teacher.id)}">${html(`${teacher.id} / ${teacherDetailLabel(teacher) || teacher.name}`)}</option>`)
          .join("")}
      </select>
    </div>
  `;
}

function applyAssignmentTeacher(assignment, teacher, row = null) {
  assignment.teacher_id = teacher.id;
  assignment.teacher_name = teacher.name;
  const idInput = row?.querySelector('input[data-field="teacher_id"]');
  const nameInput = row?.querySelector('input[data-field="teacher_name"]');
  if (idInput) idInput.value = teacher.id;
  if (nameInput) nameInput.value = teacher.name;
}

function renderAreaLinks() {
  const links = state.teaching_area_links || [];
  const areaIds = new Set((state.teaching_areas || []).map((area) => area.id).filter(Boolean));
  const linkPairs = new Map();
  for (const link of links) {
    const key = [link.from_teaching_area_id || "", link.to_teaching_area_id || ""].sort().join("__");
    if (!key.replaceAll("_", "")) continue;
    linkPairs.set(key, (linkPairs.get(key) || 0) + 1);
  }
  const duplicateLinkCount = [...linkPairs.values()].filter((count) => count > 1).reduce((sum, count) => sum + count - 1, 0);
  const invalidEndpointCount = links.filter(
    (link) =>
      !link.from_teaching_area_id ||
      !link.to_teaching_area_id ||
      !areaIds.has(link.from_teaching_area_id) ||
      !areaIds.has(link.to_teaching_area_id) ||
      link.from_teaching_area_id === link.to_teaching_area_id,
  ).length;
  const missingTravelCount = links.filter((link) => !Number(link.driving_distance_km || 0) && !Number(link.travel_minutes || 0)).length;
  const linkIssueCount = duplicateLinkCount + invalidEndpointCount + missingTravelCount;
  const linkHealth = linkIssueCount
    ? {
        tone: "warning",
        title: `${linkIssueCount} 项关系需确认`,
        desc: "处理无效、重复和缺距离时长的记录。",
      }
    : {
        tone: "ok",
        title: "通勤关系可用",
        desc: "联排、替代和跨区提醒已具备。",
      };
  const countByType = (type) => links.filter((link) => link.relation_type === type).length;
  const linkStats = [
    ["关系记录", links.length, "当前教学区关系总量", ""],
    ["可联排", countByType("可联排"), "适合连续或相邻课次参考", ""],
    ["可替代", countByType("可替代"), "可作为资源不足时的备选", ""],
    ["不建议跨区", countByType("不建议跨区"), "运行前需要重点避开", countByType("不建议跨区") ? "warning" : ""],
    ["缺距离时长", missingTravelCount, "影响跨区通勤判断", missingTravelCount ? "warning" : ""],
    ["无效/重复", invalidEndpointCount + duplicateLinkCount, "教学区缺失、同区或重复关系", invalidEndpointCount + duplicateLinkCount ? "warning" : ""],
  ];
  const entries = links.map((link, index) => ({
    link,
    index,
    issues: areaLinkIssueLabels(link, areaIds, linkPairs),
  }));
  const filteredEntries = entries
    .filter((entry) => areaLinkMatchesSearch(entry, selected.areaLinkSearch))
    .filter(({ link }) => !selected.areaLinkRelationFilter || link.relation_type === selected.areaLinkRelationFilter)
    .filter(({ issues }) => {
      if (selected.areaLinkIssueFilter === "issues") return issues.length > 0;
      if (selected.areaLinkIssueFilter === "clean") return issues.length === 0;
      return true;
    });

  content.innerHTML = section(
    "",
    "",
    `
      <div class="resource-hero area-link-hero">
        <div>
          <span>AREA COMMUTE</span>
          <h2>教学区通勤关系</h2>
          <p>维护教学区之间能否联排、能否替代、是否不建议跨区，以及驾车距离和通勤时长。</p>
        </div>
        <div class="resource-health ${html(linkHealth.tone)}">
          <span>关系健康度</span>
          <strong>${html(linkHealth.title)}</strong>
          <em>${html(linkHealth.desc)}</em>
        </div>
      </div>
      <div class="resource-stat-grid">
        ${linkStats
          .map(
            ([label, value, note, tone]) => `
              <article class="resource-stat-card ${html(tone)}">
                <span>${html(label)}</span>
                <strong>${html(value)}</strong>
                <em>${html(note)}</em>
              </article>
            `,
          )
          .join("")}
      </div>
      <div class="form-row">
        <label><span>搜索</span><input data-action="area-link-search" value="${html(selected.areaLinkSearch)}" placeholder="教学区 / 关系 / 距离 / 备注"></label>
        <label><span>关系</span><select data-action="area-link-relation-filter">${selectOptions(["可联排", "可替代", "不建议跨区", "同校区"], selected.areaLinkRelationFilter, "全部关系")}</select></label>
        <label><span>状态</span><select data-action="area-link-issue-filter">${selectLabeledOptions([
          { value: "issues", label: "只看需确认" },
          { value: "clean", label: "只看无异常" },
        ], selected.areaLinkIssueFilter, "全部状态")}</select></label>
        <button type="button" data-action="clear-area-link-filters">清除筛选</button>
        <button type="button" data-action="add-area-link">新增通勤关系</button>
        <div class="muted">${html(displayLimitNote("通勤关系", filteredEntries.length, filteredEntries.length, links.length))}</div>
      </div>
      ${filteredEntries.length ? `<div class="table-wrap segmented-table area-link-table">
        <table>
          ${colgroupHtml(["150px", "240px", "240px", "124px", "112px", "124px", "210px", "260px", "78px"])}
          <thead>
            ${columnGroupRow([
              { label: "关系", span: 1 },
              { label: "教学区", span: 2 },
              { label: "通勤判断", span: 4 },
              { label: "备注操作", span: 2 },
            ])}
            <tr><th>关系 ID</th><th>教学区 A</th><th>教学区 B</th><th>关系</th><th>驾车距离(km)</th><th>驾车时长(分钟)</th><th>状态提示</th><th>备注</th><th></th></tr>
          </thead>
          <tbody>
            ${filteredEntries
              .map(
                ({ link, index, issues }) => `
                  <tr class="${issues.length ? "needs-review" : ""}">
                    <td><input data-list="teaching_area_links" data-index="${index}" data-field="id" value="${html(link.id)}"></td>
                    <td><select data-list="teaching_area_links" data-index="${index}" data-field="from_teaching_area_id">${selectOptions(
                      teachingAreaOptions(),
                      link.from_teaching_area_id,
                    )}</select></td>
                    <td><select data-list="teaching_area_links" data-index="${index}" data-field="to_teaching_area_id">${selectOptions(
                      teachingAreaOptions(),
                      link.to_teaching_area_id,
                    )}</select></td>
                    <td><select data-list="teaching_area_links" data-index="${index}" data-field="relation_type">${selectOptions(["可联排", "可替代", "不建议跨区", "同校区"], link.relation_type)}</select></td>
                    <td><input type="number" step="0.1" data-list="teaching_area_links" data-index="${index}" data-field="driving_distance_km" value="${html(link.driving_distance_km || 0)}"></td>
                    <td><input type="number" data-list="teaching_area_links" data-index="${index}" data-field="travel_minutes" value="${html(link.travel_minutes)}"></td>
                    <td>${areaLinkIssueBadges(issues)}</td>
                    <td><input data-list="teaching_area_links" data-index="${index}" data-field="notes" value="${html(link.notes)}"></td>
                    <td><button type="button" class="small danger" data-action="delete-area-link" data-index="${index}">删除</button></td>
                  </tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
      </div>` : document.querySelector("#emptyStateTemplate").innerHTML}
    `,
  );
}

function areaLinkIssueLabels(link, areaIds, linkPairs) {
  const issues = [];
  if (!link.from_teaching_area_id || !link.to_teaching_area_id) {
    issues.push("缺教学区");
  } else {
    if (!areaIds.has(link.from_teaching_area_id) || !areaIds.has(link.to_teaching_area_id)) issues.push("教学区无效");
    if (link.from_teaching_area_id === link.to_teaching_area_id) issues.push("同一教学区");
  }
  const pairKey = [link.from_teaching_area_id || "", link.to_teaching_area_id || ""].sort().join("__");
  if (pairKey.replaceAll("_", "") && (linkPairs.get(pairKey) || 0) > 1) issues.push("重复关系");
  if (!Number(link.driving_distance_km || 0) && !Number(link.travel_minutes || 0)) issues.push("缺距离时长");
  return issues;
}

function areaLinkIssueBadges(issues) {
  if (!issues.length) return `<span class="area-link-ok">无异常</span>`;
  return `<div class="area-link-issue-list">${issues.map((issue) => `<span>${html(issue)}</span>`).join("")}</div>`;
}

function areaLinkSearchText(entry) {
  const { link, issues } = entry;
  return [
    link.id,
    link.from_teaching_area_id,
    teachingAreaSearchText(link.from_teaching_area_id),
    link.to_teaching_area_id,
    teachingAreaSearchText(link.to_teaching_area_id),
    link.relation_type,
    link.driving_distance_km,
    link.travel_minutes,
    link.notes,
    issues.join(" "),
  ].filter(Boolean).join(" ").toLowerCase();
}

function areaLinkMatchesSearch(entry, keyword) {
  const tokens = String(keyword || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const text = areaLinkSearchText(entry);
  return tokens.every((token) => text.includes(token));
}

function uniqueDraftId(prefix, existingValues = []) {
  const existing = new Set(existingValues.filter(Boolean));
  const seed = Date.now().toString(36).toUpperCase();
  let id = `${prefix}_${seed}`;
  let suffix = 2;
  while (existing.has(id)) {
    id = `${prefix}_${seed}_${suffix}`;
    suffix += 1;
  }
  return id;
}

function addArea() {
  const id = uniqueDraftId("AREA", state.teaching_areas.map((area) => area.id));
  state.teaching_areas.push({
    id,
    name: "新增教学区",
    short_name: "新增",
    region_tag: "",
    address: "",
    longitude: "",
    latitude: "",
    campus: "",
    scheduling_capacity: 0,
    capacity_check: "请补可用教室",
    is_active: false,
    room_count: 0,
    active_room_count: 0,
    notes: "",
  });
  selected.areaId = id;
  showStatus("已新增教学区，请在表格中直接修改 ID、简称、名称和校区信息。", "ok");
  render();
}

function addRoom() {
  const area = currentArea();
  const id = uniqueDraftId("ROOM", state.rooms.map((room) => room.id));
  state.rooms.push({
    id,
    name: "新增教室",
    teaching_area_id: area?.id || "",
    teaching_area_name: area ? areaShortName(area) : "",
    campus: area?.campus || "",
    capacity: 0,
    room_type: "",
    is_active: true,
    notes: "",
  });
  selected.roomSearch = "";
  showStatus("已新增教室，请在表格中直接修改教室 ID、名称、容量等信息。", "ok");
  render();
}

function addProduct() {
  const productId = uniqueDraftId("PRODUCT", products().map((product) => product.id));
  const productName = "新增产品";
  const project = inferProject(productName);
  const productLine = inferProductLine(productName, "", project);
  state.products = state.products || [];
  state.products.push({
    id: productId,
    name: productName,
    project,
    product_line: productLine,
    sub_product: inferSubProduct(productLine, productName),
    product_system: "",
    standard_capacity: 0,
    capacity_type: "",
    subject: "",
    subject_category: "",
    course_nature: "",
    notes: "",
  });
  selected.productId = productId;
  selected.productLineFilter = "";
  selected.productSearch = "";
  selected.productMetaFilters = emptyProductTagFilters();
  selected.productCourseProductFilters = emptyProductTagFilters();
  showStatus("已新增产品，请在产品管理表中维护标签；课程课时可到“产品课程”页新增。", "ok");
  render();
}

function addCourse() {
  const product = products().find((item) => item.id === selected.productId);
  state.product_courses.push({
    product_id: product?.id || "",
    product_name: product?.name || "",
    subject_category: product?.subject_category || "公共课",
    subject: product?.subject || "",
    quarter: "",
    stage: "",
    stage_priority: 0,
    course_group: "",
    course_module: "",
    module_priority: 0,
    course_code: "",
    course_name: "",
    total_hours: 0,
    block_hours: 2,
    notes: "",
  });
  render();
}

function productCourseModuleKey(course) {
  return [course.subject || "", course.course_module || ""].join("|");
}

function productCourseNameTagDefaults() {
  const defaults = new Map();
  for (const course of state.product_courses || []) {
    const key = productCourseModuleKey(course);
    if (!key.endsWith("|") && (course.course_name || course.course_code) && !defaults.has(key)) {
      defaults.set(key, {
        course_code: course.course_code || "",
        course_name: course.course_name || "",
      });
    }
  }
  return defaults;
}

function syncCourseNameTagsFromModules() {
  const defaults = productCourseNameTagDefaults();
  let updated = 0;
  for (const course of state.product_courses || []) {
    if (course.course_name && course.course_code) continue;
    const defaultsForModule = defaults.get(productCourseModuleKey(course));
    if (!defaultsForModule) continue;
    if (!course.course_name && defaultsForModule.course_name) {
      course.course_name = defaultsForModule.course_name;
      updated += 1;
    }
    if (!course.course_code && defaultsForModule.course_code) {
      course.course_code = defaultsForModule.course_code;
      updated += 1;
    }
  }
  showStatus(updated ? `已按科目+模块补齐 ${updated} 个课程名称标签字段。` : "当前产品课程的课程名称标签已齐全。", updated ? "ok" : "warning");
  refreshProductDetail();
}

function addRule() {
  selected.ruleSearch = "";
  selected.ruleWindowFilter = "";
  selected.ruleDeliveryFilter = "";
  selected.ruleIssueFilter = "";
  state.product_schedule_rules.push({
    rule_id: `RULE_${Date.now()}`,
    rule_name: "新增排课规则",
    scope_type: "product_ids",
    product_id: "",
    product_ids: [],
    product_name: "",
    sub_product: "",
    season_window_id: "",
    window_name: "",
    effective_after_class_start: true,
    delivery_mode: "面授",
    allowed_periods: [],
    allowed_weekdays: [],
    block_hours: 2,
    lessons_per_block: 1,
    max_hours_per_class_per_day: 4,
    max_blocks_per_class_per_day: 1,
    min_weekly_hours: "",
    max_weekly_hours: "",
    same_half_day_block_required: true,
    same_half_day_4h_same_teacher_required: false,
    block_hours_override: 2,
    notes: "",
  });
  render();
}

function addBlackout() {
  const today = new Date().toISOString().slice(0, 10);
  state.global_blackout_dates = state.global_blackout_dates || [];
  state.global_blackout_dates.push({
    id: `BLACKOUT_${Date.now()}`,
    name: "全局停课",
    start_date: today,
    end_date: today,
    is_active: true,
    notes: "",
  });
  render();
}

function addTeacher() {
  const id = uniqueDraftId("TEACHER", (state.teachers || []).map((teacher) => teacher.id || teacher.employee_id));
  state.teachers = state.teachers || [];
  state.teachers.push({
    id,
    employee_id: id,
    name: "新增教师",
    gender: "",
    project: "考研",
    identity: "",
    teacher_role: "",
    teacher_type: "",
    employment_type: "",
    primary_subject: "",
    subject_type: "",
    contract_status: "",
    employment_status: "在职",
    notes: "",
  });
  selected.teacherSearch = "";
  showStatus("已新增教师，请在表格中直接修改员工ID、姓名、身份和教师类型。", "ok");
  render();
}

function defaultScheduleRuleTemplates() {
  const day = ["AM", "PM"];
  const evening = ["EVENING"];
  const monSat = ["周一", "周二", "周三", "周四", "周五", "周六"];
  const tueSat = ["周二", "周三", "周四", "周五", "周六"];
  const tueFri = ["周二", "周三", "周四", "周五"];
  const satSun = ["周六", "周日"];
  const wedSatSun = ["周三", "周六", "周日"];
  const rule = (id, name, keywords, windowName, periods, weekdaysValue, hours, notes, extra = {}) => {
    const season = seasonWindowDefaults[windowName] || {};
    const blockHours = Number(hours || 0);
    return {
      rule_id: id,
      rule_name: name,
      scope_type: "keywords",
      product_id: "",
      product_ids: [],
      product_name: "",
      product_name_keywords: keywords,
      subject: "",
      stage: "",
      course_module: "",
      course_group: "",
      season_window_id: season.season_window_id || "",
      window_name: windowName,
      effective_after_class_start: true,
      delivery_mode: periods.includes("EVENING") && periods.length === 1 ? "直播" : "面授",
      start_date: "",
      end_date: "",
      allowed_periods: periods,
      allowed_weekdays: weekdaysValue,
      excluded_weekdays: [],
      exception_weekdays: [],
      block_hours: blockHours,
      lessons_per_block: blockHours >= 4 ? 2 : 1,
      max_hours_per_class_per_day: blockHours >= 4 ? 4 : blockHours,
      max_blocks_per_class_per_day: 1,
      min_weekly_hours: "",
      max_weekly_hours: "",
      same_half_day_block_required: blockHours >= 4,
      same_half_day_4h_same_teacher_required: blockHours >= 4,
      block_hours_override: "",
      notes,
      ...extra,
    };
  };

  return [
    rule("RULE_HSY_WYH_WINTER_DAY", "寒暑营/无忧寒：寒假白天", ["寒暑营", "无忧寒"], "寒假", day, monSat, 4, "寒假每周一到周六白天排课。"),
    rule("RULE_HSY_WYH_SPRING_EVENING", "寒暑营/无忧寒：春季晚上", ["寒暑营", "无忧寒"], "春季", evening, tueFri, 2, "春季每周二到周五晚上排课。"),
    rule("RULE_HSY_WYH_SUMMER_DAY", "寒暑营/无忧寒：暑假白天", ["寒暑营", "无忧寒"], "暑假", day, monSat, 4, "暑假每周一到周六白天排课。"),
    rule("RULE_HSY_WYH_AUTUMN_EVENING", "寒暑营/无忧寒：秋季晚上", ["寒暑营", "无忧寒"], "秋季", evening, tueSat, 2, "秋季每周二到周六晚上排课。"),
    rule("RULE_WYQ_WINTER_WEEKEND_DAY", "无忧秋：寒假周末白天", ["无忧秋"], "寒假", day, satSun, 4, "寒假每周六周日白天排课。"),
    rule("RULE_WYQC_SPRING_WEEKEND_DAY", "无忧秋/无忧春：春季周末白天", ["无忧秋", "无忧春"], "春季", day, satSun, 4, "春季每周六周日白天排课。"),
    rule("RULE_WYQC_SUMMER_DAY", "无忧秋/无忧春：暑假白天", ["无忧秋", "无忧春"], "暑假", day, monSat, 4, "暑假每周一到周六白天排课。"),
    rule("RULE_WYQC_AUTUMN_WEEKEND_DAY", "无忧秋/无忧春：秋季周末白天", ["无忧秋", "无忧春"], "秋季", day, satSun, 4, "秋季每周六周日白天排课。"),
    rule("RULE_WYS_SUMMER_DAY", "无忧暑：暑假白天", ["无忧暑"], "暑假", day, monSat, 4, "暑假每周一到周六白天排课。"),
    rule("RULE_WYS_AUTUMN_WED_WEEKEND_DAY", "无忧暑：秋季周三/周末白天", ["无忧暑"], "秋季", day, wedSatSun, 4, "秋季每周三、周六、周日白天排课。"),
    rule("RULE_SJY_SUMMER_DAY", "暑假营：暑假白天", ["暑假营"], "暑假", day, monSat, 4, "暑假每周一到周六白天排课。"),
    rule("RULE_SJY_AUTUMN_EVENING", "暑假营：秋季晚上", ["暑假营"], "秋季", evening, tueFri, 2, "秋季每周二到周五晚上排课。"),
  ];
}

function loadScheduleRuleTemplates() {
  if (state.product_schedule_rules.length && !confirm("会用当前整理后的规则模板替换现有产品排课规则，是否继续？")) return;
  state.product_schedule_rules = defaultScheduleRuleTemplates();
  showStatus("已载入整理后的产品排课规则模板，记得点击“保存数据修改”。", "ok");
  render();
}

function addClass() {
  const product = products()[0];
  const id = uniqueDraftId("CLASS", state.classes.map((cls) => cls.id));
  const subject = product?.subject || productSubjects(product?.id || "")[0] || "";
  const cls = {
    id,
    name: "新增班级",
    product_id: product?.id || "",
    project: "",
    product_line: "",
    sub_product: "",
    product_system: "",
    course_nature: "",
    subject_category: productSubjectCategory(product?.id || "", subject),
    subject,
    stages: [],
    selected_stages: [],
    exam_season: "",
    exam_month: "",
    suite_code: "",
    standard_capacity: product?.standard_capacity || 0,
    capacity_type: inferCapacityType(product?.standard_capacity || 0),
    size: 0,
    start_date: "",
    start_period: "",
    first_lesson_date: "",
    first_lesson_period: "",
    end_date: "",
    end_period: "",
    preferred_teaching_area_ids: [],
    preferred_room_ids: [],
    preferred_room_is_required: false,
    is_schedule_locked: false,
    is_manual_schedule_locked: false,
    notes: "",
    teacher_assignments: [],
  };
  applyClassAutoTags(cls, false);
  pruneClassStages(cls, true);
  state.classes.push(cls);
  selected.classId = id;
  syncTeachers();
  showStatus("已新增班级，请在右侧直接修改班级 ID、名称、产品和日期限制。", "ok");
  render();
}

function syncTeachers() {
  const cls = currentClass();
  if (!cls || !cls.product_id) return 0;
  return syncClassTeachers(cls);
}

function syncAllClassTeachers() {
  let classCount = 0;
  let assignmentCount = 0;
  for (const cls of state.classes || []) {
    const count = syncClassTeachers(cls);
    if (count) {
      classCount += 1;
      assignmentCount += count;
    }
  }
  showStatus(`已同步 ${classCount} 个班级，共 ${assignmentCount} 条阶段/课程类别老师安排。记得点击“保存数据修改”。`, "ok");
}

function syncClassTeachers(cls) {
  if (!cls || !cls.product_id) return 0;
  const current = new Map();
  for (const assignment of cls.teacher_assignments || []) {
    const key = teacherAssignmentKey(assignment, cls.product_id);
    chooseCurrentTeacherAssignment(current, key, assignment);
    const rawKey = teacherAssignmentKey(assignment, "");
    if (rawKey !== key) chooseCurrentTeacherAssignment(current, rawKey, assignment);
    const [rawProduct, rawSubject, rawStage, rawGroup] = rawKey.split("||");
    if (rawProduct && rawProduct !== cls.product_id) {
      chooseCurrentTeacherAssignment(current, teacherAssignmentKeyFromParts("", rawSubject, rawStage, rawGroup), assignment);
    }
  }
  const groupedCourses = new Map();
  const courses = classProductCourses(cls).map(({ course }) => course);
  for (const course of courses) {
    const key = teacherAssignmentKey(course, cls.product_id);
    if (!groupedCourses.has(key)) groupedCourses.set(key, course);
  }
  cls.teacher_assignments = Array.from(groupedCourses.values()).map((course) => {
    const existing = resolveSyncedTeacherAssignment(course, cls.product_id, current, courses);
    const exactExisting = resolveExactTeacherAssignment(course, cls.product_id, current);
    const scheduleMode = assignmentScheduleMode(exactExisting, cls);
    const referenceClassId = scheduleMode === "共享课表" ? assignmentReferenceClassId(exactExisting, cls) : "";
    const isShared = scheduleMode === "共享课表";
    return {
      product_id: cls.product_id,
      product_name: productName(cls.product_id),
      subject: course.subject,
      stage: course.stage,
      course_group: course.course_group,
      class_schedule_mode: scheduleModeDisplayName(scheduleMode),
      actual_scheduled_class_id: isShared ? referenceClassId : cls.id,
      teacher_id: isShared ? "" : existing.teacher_id || "",
      teacher_name: isShared ? "" : existing.teacher_name || "",
      assignment_extra_time_requirement: isShared ? "" : existing.assignment_extra_time_requirement || exactExisting.assignment_extra_time_requirement || "",
      notes: exactExisting.notes || existing.notes || "",
    };
  });
  return cls.teacher_assignments.length;
}

function addAreaLink() {
  const first = state.teaching_areas[0]?.id || "";
  const second = state.teaching_areas[1]?.id || "";
  state.teaching_area_links.push({
    id: `${first}__${second}`,
    from_teaching_area_id: first,
    to_teaching_area_id: second,
    relation_type: "可联排",
    driving_distance_km: 0,
    travel_minutes: 0,
    notes: "",
  });
  selected.areaLinkSearch = "";
  selected.areaLinkRelationFilter = "";
  selected.areaLinkIssueFilter = "";
  showStatus("已新增教学区通勤关系，请核对教学区、关系类型、距离和时长。", "ok");
  renderAreaLinks();
}

function addClassConflictGroup() {
  state.class_conflict_groups = state.class_conflict_groups || [];
  const id = uniqueDraftId("CONFLICT", state.class_conflict_groups.map((group) => group.id));
  state.class_conflict_groups.push({
    id,
    name: "新增互斥组",
    exam_season: "",
    suite_code: "",
    class_ids: [],
    is_conflict_group_active: true,
    conflict_source: "手动",
    notes: "",
  });
  showStatus("已新增班级互斥组，请用班级编码搜索添加至少 2 个互斥班级。", "ok");
  renderClassConflicts();
}

function syncSuiteConflicts() {
  state.class_conflict_groups = state.class_conflict_groups || [];
  const existingIds = new Set(state.class_conflict_groups.map((group) => group.id).filter(Boolean));
  const generated = suiteConflictGroupsFromClasses();
  let added = 0;
  for (const group of generated) {
    if (existingIds.has(group.id)) continue;
    state.class_conflict_groups.push(group);
    existingIds.add(group.id);
    added += 1;
  }
  showStatus(added ? `已按套班编码补充 ${added} 个互斥组。` : "套班编码互斥组已齐全，无需补充。", added ? "ok" : "warning");
  renderClassConflicts();
}

function addTeacherUnavailable() {
  state.teacher_unavailability = state.teacher_unavailability || [];
  const id = uniqueDraftId("UNAVAIL", state.teacher_unavailability.map((item) => item.unavailable_id));
  state.teacher_unavailability.push({
    unavailable_id: id,
    employee_id: "",
    teacher_name: "",
    primary_subject: "",
    unavailable_type: "请假",
    start_date: "",
    end_date: "",
    weekdays: [],
    periods: [],
    schedule_window_ids: [],
    is_active: true,
    reason: "",
    data_source: "后台手动新增",
    notes: "ID按规则自动生成；项目/用工类型从05表按employee_id关联。",
  });
  selected.teacherUnavailableSearch = "";
  showStatus("已新增教师不可排记录，请填写老师、日期或星期/时段。", "ok");
  renderTeacherUnavailable();
}

function isLiveSearchAction(action) {
  return [
    "area-search",
    "room-search",
    "teacher-search",
    "teacher-unavailable-search",
    "product-search",
    "class-search",
    "class-teacher-search",
    "class-conflict-search",
    "time-slot-search",
    "class-window-search",
    "class-window-area-picker",
    "class-window-room-picker",
    "area-link-search",
    "rule-search",
    "locked-lesson-search",
    "business-mapping-search",
  ].includes(action);
}

function isComposingInput(target, event) {
  return Boolean(event?.isComposing || target.dataset.composing === "true");
}

function isMutatingControl(target) {
  if (target.dataset.list || target.dataset.entity || target.dataset.assignmentIndex) return true;
  if (target.dataset.listCheckbox === "true" || target.dataset.entityCheckbox === "true") return true;
  return mutatingControlActions.has(target.dataset.action || "");
}

content.addEventListener("input", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (isMutatingControl(target) && !isComposingInput(target, event)) markUnsavedChange();
  handleValueChange(target, event);
});

content.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (isMutatingControl(target)) markUnsavedChange();
  handleValueChange(target, event);
});

content.addEventListener("compositionstart", (event) => {
  const target = event.target;
  if (target instanceof HTMLElement && isLiveSearchAction(target.dataset.action)) {
    target.dataset.composing = "true";
  }
});

content.addEventListener("compositionend", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement) || !isLiveSearchAction(target.dataset.action)) return;
  delete target.dataset.composing;
  handleValueChange(target, event);
});

content.addEventListener("scroll", (event) => {
  const target = event.target;
  if (target instanceof HTMLElement && target.matches("[data-product-list]")) {
    selected.productListScrollTop = target.scrollTop;
  }
}, true);

function handleValueChange(target, event = null) {
  if (target.dataset.action === "room-search") {
    if (isComposingInput(target, event)) return;
    selected.roomSearch = target.value;
    render();
    return;
  }
  if (target.dataset.action === "area-search") {
    if (isComposingInput(target, event)) return;
    const cursorPosition = target.selectionStart ?? target.value.length;
    selected.areaSearch = target.value;
    renderRooms();
    const searchInput = content.querySelector('input[data-action="area-search"]');
    if (searchInput) {
      searchInput.focus();
      searchInput.setSelectionRange(cursorPosition, cursorPosition);
    }
    return;
  }
  if (target.dataset.action === "teacher-search") {
    if (isComposingInput(target, event)) return;
    selected.teacherSearch = target.value;
    renderTeachers();
    return;
  }
  if (target.dataset.action === "teacher-unavailable-search") {
    if (isComposingInput(target, event)) return;
    selected.teacherUnavailableSearch = target.value;
    renderTeacherUnavailable();
    return;
  }
  if (target.dataset.action === "product-search") {
    if (isComposingInput(target, event)) return;
    selected.productSearch = target.value;
    renderProductMeta();
    return;
  }
  if (target.dataset.action === "product-meta-tag-filter") {
    selected.productMetaFilters[target.dataset.field] = target.value;
    renderProductMeta();
    return;
  }
  if (target.dataset.action === "product-course-product-filter") {
    selected.productCourseProductFilters[target.dataset.field] = target.value;
    selected.productListScrollTop = 0;
    selected.courseFilters = emptyCourseFilters();
    renderProducts();
    return;
  }
  if (target.dataset.action === "class-search") {
    if (isComposingInput(target, event)) return;
    const cursorPosition = target.selectionStart ?? target.value.length;
    selected.classSearch = target.value;
    renderClassMeta();
    const searchInput = content.querySelector('input[data-action="class-search"]');
    if (searchInput) {
      searchInput.focus();
      searchInput.setSelectionRange(cursorPosition, cursorPosition);
    }
    return;
  }
  if (target.dataset.action === "class-conflict-search") {
    if (isComposingInput(target, event)) return;
    const cursorPosition = target.selectionStart ?? target.value.length;
    selected.classConflictSearch = target.value;
    renderClassConflicts();
    const searchInput = content.querySelector('input[data-action="class-conflict-search"]');
    if (searchInput) {
      searchInput.focus();
      searchInput.setSelectionRange(cursorPosition, cursorPosition);
    }
    return;
  }
  if (target.dataset.action === "time-slot-search") {
    if (isComposingInput(target, event)) return;
    selected.timeSlotSearch = target.value;
    renderTimeData();
    return;
  }
  if (target.dataset.action === "class-window-search") {
    if (isComposingInput(target, event)) return;
    selected.classWindowSearch = target.value;
    renderClassWindows();
    return;
  }
  if (target.dataset.action === "class-window-area-picker") {
    if (isComposingInput(target, event)) return;
    const item = state.class_window_boundaries[Number(target.dataset.index)];
    if (!item) return;
    const areaId = teachingAreaIdFromPickerValue(target.value);
    if (areaId) {
      addClassWindowTeachingArea(item, areaId);
      showStatus(`已添加窗口教学区：${teachingAreaPickerLabel(areaId)}`, "ok");
      renderClassWindows();
    } else if (event?.type === "change" && target.value.trim()) {
      target.value = "";
      showStatus("没有匹配到教学区，请从下拉建议中选择。", "warning");
    }
    return;
  }
  if (target.dataset.action === "class-window-room-picker") {
    if (isComposingInput(target, event)) return;
    const item = state.class_window_boundaries[Number(target.dataset.index)];
    if (!item) return;
    const roomId = classWindowRoomIdFromPickerValue(target.value, item);
    if (roomId) {
      addClassWindowRoom(item, roomId);
      showStatus(`已添加窗口教室：${roomPickerLabel(roomId)}`, "ok");
      renderClassWindows();
    } else if (event?.type === "change" && target.value.trim()) {
      target.value = "";
      showStatus("没有匹配到可选教室，请先确认窗口教学区或从下拉建议中选择。", "warning");
    }
    return;
  }
  if (target.dataset.action === "locked-lesson-search") {
    if (isComposingInput(target, event)) return;
    selected.lockedLessonSearch = target.value;
    renderLockedLessons();
    return;
  }
  if (target.dataset.action === "area-link-search") {
    if (isComposingInput(target, event)) return;
    selected.areaLinkSearch = target.value;
    renderAreaLinks();
    return;
  }
  if (target.dataset.action === "area-link-relation-filter") {
    selected.areaLinkRelationFilter = target.value;
    renderAreaLinks();
    return;
  }
  if (target.dataset.action === "area-link-issue-filter") {
    selected.areaLinkIssueFilter = target.value;
    renderAreaLinks();
    return;
  }
  if (target.dataset.action === "business-mapping-search") {
    if (isComposingInput(target, event)) return;
    selected.businessMappingSearch = target.value;
    renderBusinessMappings();
    return;
  }
  if (target.dataset.action === "business-mapping-status-filter") {
    selected.businessMappingStatusFilter = target.value;
    renderBusinessMappings();
    return;
  }
  if (target.dataset.action === "rule-search") {
    if (isComposingInput(target, event)) return;
    const cursorPosition = target.selectionStart ?? target.value.length;
    selected.ruleSearch = target.value;
    renderRules();
    const searchInput = content.querySelector('input[data-action="rule-search"]');
    if (searchInput) {
      searchInput.focus();
      searchInput.setSelectionRange(cursorPosition, cursorPosition);
    }
    return;
  }
  if (target.dataset.action === "rule-window-filter") {
    selected.ruleWindowFilter = target.value;
    renderRules();
    return;
  }
  if (target.dataset.action === "rule-delivery-filter") {
    selected.ruleDeliveryFilter = target.value;
    renderRules();
    return;
  }
  if (target.dataset.action === "rule-issue-filter") {
    selected.ruleIssueFilter = target.value;
    renderRules();
    return;
  }
  if (target.dataset.action === "class-teacher-search") {
    if (isComposingInput(target, event)) return;
    const cursorPosition = target.selectionStart ?? target.value.length;
    selected.classTeacherSearch = target.value;
    if (event?.type === "input") {
      scheduleClassTeacherSearchRender(cursorPosition);
    } else {
      flushClassTeacherSearchRender(cursorPosition);
    }
    return;
  }
  if (target.dataset.action === "class-conflict-class-picker") {
    const classId = classIdFromPickerValue(target.value);
    if (!classId) return;
    const groupIndex = Number(target.dataset.index);
    if (addClassConflictClass(groupIndex, classId)) {
      showStatus(`已添加互斥班级：${classId}`, "ok");
    } else {
      showStatus(`互斥组中已包含班级：${classId}`, "warning");
    }
    renderClassConflicts();
    return;
  }
  if (target.dataset.action === "class-meta-tag-filter") {
    selected.classMetaFilters[target.dataset.field] = target.value;
    renderClassMeta();
    return;
  }
  if (target.dataset.action === "class-product-filter") {
    selected.classProductFilter = target.value;
    renderClassMeta();
    return;
  }
  if (target.dataset.action === "class-subject-filter") {
    selected.classSubjectFilter = target.value;
    renderClassMeta();
    return;
  }
  if (target.dataset.action === "batch-suite-codes") {
    selected.batchSuiteCodes = target.value;
    return;
  }
  if (target.dataset.action === "batch-class-ids") {
    selected.batchClassIds = target.value;
    return;
  }
  if (target.dataset.action === "batch-sub-products") {
    selected.batchSubProducts = target.value;
    return;
  }
  if (target.dataset.action === "class-product-picker") {
    if (isComposingInput(target, event)) return;
    const cls = state.classes.find((item) => item.id === target.dataset.id);
    if (!cls) return;
    const productId = productIdFromSearchValue(target.value, cls);
    if (!target.value.trim()) {
      if (event?.type === "change") {
        applyClassProduct(cls, "");
        renderActiveClassView({ preservePosition: true });
      }
      return;
    }
    if (productId && productId !== cls.product_id) {
      applyClassProduct(cls, productId);
      showStatus(`已选择产品：${productPickerLabel(productId)}`, "ok");
      renderActiveClassView({ preservePosition: true });
    } else if (!productId && event?.type === "change") {
      target.value = productPickerLabel(cls.product_id);
      showStatus("没有唯一匹配的产品，请继续输入产品ID、正课/导学、科目等关键字后再选择。", "warning");
    }
    return;
  }
  if (target.dataset.action === "class-area-picker") {
    const cls = state.classes.find((item) => item.id === target.dataset.id);
    if (!cls) return;
    const areaId = teachingAreaIdFromPickerValue(target.value);
    if (areaId) {
      addClassTeachingArea(cls, areaId);
      showStatus(`已添加教学区：${teachingAreaPickerLabel(areaId)}`, "ok");
      renderActiveClassView({ preservePosition: activeTab === "classMeta" });
    }
    return;
  }
  if (target.dataset.action === "class-room-picker") {
    const cls = state.classes.find((item) => item.id === target.dataset.id);
    if (!cls) return;
    const roomId = roomIdFromPickerValue(target.value, cls);
    if (roomId) {
      addClassRoom(cls, roomId);
      showStatus(`已添加教室：${roomPickerLabel(roomId)}`, "ok");
      renderActiveClassView({ preservePosition: activeTab === "classMeta" });
    }
    return;
  }
  if (target.dataset.action === "import-products-file") {
    importProductsFile(target).catch((error) => showStatus(error.message, "error"));
    return;
  }
  if (target.dataset.action === "import-classes-file") {
    importClassesFile(target).catch((error) => showStatus(error.message, "error"));
    return;
  }
  if (target.dataset.action === "course-filter") {
    selected.courseFilters[target.dataset.field] = target.value;
    applyProductCourseFilters();
    return;
  }
  if (target.dataset.action === "course-name-picker") {
    if (event?.type === "input") return;
    const course = state.product_courses[Number(target.dataset.index)];
    if (!course) return;
    const text = target.value.trim();
    if (!text) {
      course.course_name = "";
      course.course_code = "";
      applyProductCourseFilters();
      return;
    }
    const tag = courseNameTagFromPickerValue(text);
    if (tag) {
      course.course_name = tag.course_name || "";
      course.course_code = tag.course_code || "";
      target.value = course.course_name;
      showStatus(`已选择课程名称标签：${course.course_name}${course.course_code ? `（${course.course_code}）` : ""}`, "ok");
    } else {
      course.course_name = text;
      course.course_code = "";
      showStatus("未匹配到课程编码，已作为自定义课程名称标签保留。", "warning");
    }
    applyProductCourseFilters();
    return;
  }
  if (target.dataset.action === "product-line-filter") {
    selected.productLineFilter = target.value;
    selected.productListScrollTop = 0;
    selected.productCourseProductFilters.product_line = target.value;
    selected.courseFilters = emptyCourseFilters();
    renderProducts();
    return;
  }
  if (target.dataset.action === "product-field") {
    const value = target.type === "number" ? Number(target.value || 0) : target.value;
    setProductField(selected.productId, target.dataset.field, value);
    if (["project", "product_line"].includes(target.dataset.field)) refreshProductDetail();
    return;
  }

  if (target.dataset.listCheckbox === "true") {
    const selector = `input[data-list-checkbox="true"][data-list="${target.dataset.list}"][data-index="${target.dataset.index}"][data-field="${target.dataset.field}"]:checked`;
    setByIndex(target.dataset.list, target.dataset.index, target.dataset.field, [...content.querySelectorAll(selector)].map((item) => item.value));
    return;
  }

  if (target.dataset.entityCheckbox === "true") {
    const selector = `input[data-entity-checkbox="true"][data-entity="${target.dataset.entity}"][data-id="${target.dataset.id}"][data-field="${target.dataset.field}"]:checked`;
    const values = [...content.querySelectorAll(selector)].map((item) => item.value);
    if (target.dataset.entity === "class") {
      const cls = state.classes.find((item) => item.id === target.dataset.id);
      if (!cls) return;
      cls[target.dataset.field] = values;
      if (target.dataset.field === "stages") {
        cls.selected_stages = [...values];
        syncClassTeachers(cls);
      }
      if (activeTab !== "classMeta") renderClasses();
    }
    return;
  }

  if (target.dataset.list) {
    const listName = target.dataset.list;
    const rowIndex = Number(target.dataset.index);
    const field = target.dataset.field;
    const previousValue = state[listName]?.[rowIndex]?.[field];
    let value = target instanceof HTMLSelectElement && target.multiple
      ? selectedOptions(target)
      : target.type === "checkbox"
        ? target.checked
        : target.type === "number"
          ? Number(target.value || 0)
          : target.value;
    if (listName === "product_schedule_rules" && field === "product_name_keywords") {
      value = arrayValues(value);
    }
    if (listName === "business_product_mappings" && field === "class_name_keywords") {
      value = arrayValues(value);
    }
    setByIndex(listName, rowIndex, field, value);
    if (listName === "class_conflict_groups") {
      const item = state.class_conflict_groups[rowIndex];
      if (!item) return;
      if (field === "is_conflict_group_active") item.is_active = value;
      if (field === "conflict_source") item.source = value;
    }
    if (listName === "class_window_boundaries") {
      const item = state.class_window_boundaries[rowIndex];
      if (!item) return;
      if (field === "class_id") {
        applyClassWindowClassDefaults(item, { overwriteDates: true, overwriteResources: true });
        showStatus("已根据班级带出产品、名称、日期边界和默认场地，记得点击“保存数据修改”。", "ok");
        renderClassWindows();
        return;
      }
      if (field === "schedule_window_id") {
        applyClassWindowScheduleDefaults(item, { overwriteDates: true });
        showStatus("已根据年度窗口带出年份、季节、顺序和日期边界，记得点击“保存数据修改”。", "ok");
        renderClassWindows();
        return;
      }
      if (["class_window_id", "window_year", "window_order", "window_sequence"].includes(field)) {
        return;
      }
    }
    if (listName === "teachers") {
      const teacher = state.teachers[rowIndex];
      if (field === "id") {
        teacher.employee_id = value;
        for (const cls of state.classes) {
          for (const assignment of cls.teacher_assignments || []) {
            if (previousValue && assignment.teacher_id === previousValue) assignment.teacher_id = value;
          }
        }
      }
      if (field === "name") {
        for (const cls of state.classes) {
          for (const assignment of cls.teacher_assignments || []) {
            if (assignment.teacher_id === teacher.id) assignment.teacher_name = value;
          }
        }
      }
      if (field === "primary_subject") {
        applyTeacherSubjectType(teacher);
        renderTeachers();
        return;
      }
      if (field === "teacher_role") {
        teacher.identity = value;
      }
      if (field === "employment_type") {
        teacher.teacher_type = value;
      }
    }
    if (listName === "products") {
      const product = state.products[rowIndex];
      if (field === "id") {
        syncProductId(previousValue, value);
        selected.productId = value;
      }
      if (field === "name") {
        syncProductName(product.id, value);
        return;
      }
      if (field === "project") {
        product.product_line = inferProductLine(product.name, "", product.project);
        product.sub_product = inferSubProduct(product.product_line, product.name);
        renderProductMeta();
        return;
      }
      if (field === "product_line") {
        product.sub_product = inferSubProduct(product.product_line, product.name);
        renderProductMeta();
        return;
      }
      if (field === "standard_capacity") {
        product.capacity_type = inferCapacityType(product.standard_capacity);
        return;
      }
      for (const cls of state.classes || []) {
        if (cls.product_id === product.id) applyClassAutoTags(cls, true);
      }
    }
    if (listName === "business_product_mappings") {
      const mapping = state.business_product_mappings[rowIndex];
      if (!mapping) return;
      if (field === "erp_product_key") {
        applyBusinessMappingErpProduct(mapping);
        showStatus("已根据ERP标准课程产品带出课程编码、版本和课时信息。", "ok");
        renderBusinessMappings();
        return;
      }
      if (field === "local_product_id") {
        syncBusinessMappingLocalFields(mapping);
        renderBusinessMappings();
        return;
      }
    }
    if (listName === "rooms" && field === "teaching_area_id") {
      const room = state.rooms[rowIndex];
      const area = state.teaching_areas.find((item) => item.id === room.teaching_area_id);
      room.teaching_area_name = area ? areaShortName(area) : "";
      room.campus = area?.campus || "";
      renderRooms();
      return;
    }
    if (target.dataset.list === "product_schedule_rules" && target.dataset.field === "product_id") {
      const rule = state.product_schedule_rules[Number(target.dataset.index)];
      rule.product_name = productName(rule.product_id);
      rule.product_ids = rule.product_id ? [rule.product_id] : [];
      rule.scope_type = "product_ids";
      rule.product_name_keywords = [];
    }
    if (target.dataset.list === "product_schedule_rules" && target.dataset.field === "product_name_keywords") {
      const rule = state.product_schedule_rules[Number(target.dataset.index)];
      rule.scope_type = "keywords";
      rule.product_id = "";
      rule.product_ids = [];
      rule.product_name = "";
    }
    if (target.dataset.list === "product_schedule_rules" && target.dataset.field === "season_window_id") {
      const rule = state.product_schedule_rules[Number(target.dataset.index)];
      rule.window_name = seasonWindowName(rule.season_window_id);
    }
    if (target.dataset.list === "product_schedule_rules" && target.dataset.field === "block_hours") {
      const rule = state.product_schedule_rules[Number(target.dataset.index)];
      rule.block_hours_override = rule.block_hours;
    }
    if (target.dataset.list === "product_schedule_rules" && target.dataset.field === "scope_type") {
      const rule = state.product_schedule_rules[Number(target.dataset.index)];
      if (rule.scope_type === "all") {
        rule.product_id = "";
        rule.product_ids = [];
        rule.product_name = "";
        rule.product_name_keywords = [];
      }
      if (rule.scope_type === "keywords") {
        rule.product_id = "";
        rule.product_ids = [];
        rule.product_name = "";
      }
      if (rule.scope_type === "product_ids") {
        rule.product_name_keywords = [];
      }
      renderRules();
      return;
    }
    if (target.dataset.list === "product_courses") {
      const course = state.product_courses[Number(target.dataset.index)];
      if (course && target.dataset.field === "window_name") {
        course.quarter = course.window_name;
      }
      if (course && target.dataset.field === "module_priority_in_group") {
        course.module_priority = course.module_priority_in_group;
      }
      if (course && ["subject", "course_module"].includes(target.dataset.field) && (!course.course_name || !course.course_code)) {
        const defaultsForModule = productCourseNameTagDefaults().get(productCourseModuleKey(course));
        if (defaultsForModule) {
          course.course_name = course.course_name || defaultsForModule.course_name || "";
          course.course_code = course.course_code || defaultsForModule.course_code || "";
        }
      }
      applyProductCourseFilters();
    }
    return;
  }

  if (target.dataset.entity === "area") {
    const area = state.teaching_areas.find((item) => item.id === target.dataset.id);
    if (!area) return;
    const oldId = area.id;
    area[target.dataset.field] = target.value;
    if (target.dataset.field === "id") {
      const newId = target.value.trim();
      for (const room of state.rooms) {
        if (room.teaching_area_id === oldId) room.teaching_area_id = newId;
      }
      for (const cls of state.classes) {
        cls.preferred_teaching_area_ids = arrayValues(cls.preferred_teaching_area_ids).map((id) => (id === oldId ? newId : id));
      }
      for (const link of state.teaching_area_links) {
        if (link.from_teaching_area_id === oldId) link.from_teaching_area_id = newId;
        if (link.to_teaching_area_id === oldId) link.to_teaching_area_id = newId;
      }
      selected.areaId = newId;
    }
    if (["id", "short_name", "name", "campus"].includes(target.dataset.field)) {
      for (const room of state.rooms) {
        if (room.teaching_area_id === area.id) {
          room.teaching_area_name = areaShortName(area);
          room.campus = area.campus || "";
        }
      }
    }
    return;
  }

  if (target.dataset.entity === "class") {
    const rawValue = target instanceof HTMLSelectElement && target.multiple
      ? selectedOptions(target)
      : target.type === "number"
        ? Number(target.value || 0)
        : target.type === "checkbox"
          ? target.checked
          : target.value;
    const cls = state.classes.find((item) => item.id === target.dataset.id);
    if (!cls) return;
    const value = ["stages", "preferred_teaching_area_ids", "preferred_room_ids"].includes(target.dataset.field) && !(target instanceof HTMLSelectElement && target.multiple)
      ? arrayValues(rawValue)
      : rawValue;
    cls[target.dataset.field] = value;
    if (target.dataset.field === "id") selected.classId = value;
    if (target.dataset.field === "is_schedule_locked") cls.is_manual_schedule_locked = value;
    if (target.dataset.field === "name") {
      applyClassAutoTags(cls, true);
      return;
    }
    if (target.dataset.field === "product_id") {
      applyClassProduct(cls, cls.product_id);
      renderActiveClassView({ preservePosition: true });
      return;
    }
    if (target.dataset.field === "subject") {
      if (productSubjectCategory(cls.product_id, cls.subject)) cls.subject_category = productSubjectCategory(cls.product_id, cls.subject);
      pruneClassStages(cls, true);
      syncClassTeachers(cls);
      renderActiveClassView({ preservePosition: true });
      return;
    }
    if (target.dataset.field === "preferred_teaching_area_ids") {
      pruneClassRoomSelection(cls);
      renderActiveClassView({ preservePosition: true });
      return;
    }
    return;
  }

  if (target.dataset.assignmentIndex) {
    const cls = currentClass();
    if (!cls) return;
    const assignment = cls.teacher_assignments[Number(target.dataset.assignmentIndex)];
    if (!assignment) return;
    const field = target.dataset.field;
    const row = target.closest("tr");
    if (field === "teacher_match_id") {
      const teacher = teacherById(target.value);
      if (teacher) {
        applyAssignmentTeacher(assignment, teacher, row);
        showStatus(`已选择 ${teacher.name}（${teacher.id}）。`, "ok");
        renderClasses();
      }
      return;
    }
    if (field === "class_schedule_mode") {
      const currentClassId = currentClass()?.id || assignment.class_id || "";
      const requestedMode = normalizeScheduleMode(target.value);
      assignment.class_schedule_mode = scheduleModeDisplayName(requestedMode);
      delete assignment.schedule_mode;
      delete assignment.inherit_from_class_id;
      delete assignment.teacher_available_slots;
      if (requestedMode === "共享课表") {
        assignment.teacher_id = "";
        assignment.teacher_name = "";
        assignment.assignment_extra_time_requirement = "";
        assignment.actual_scheduled_class_id =
          assignment.actual_scheduled_class_id && assignment.actual_scheduled_class_id !== currentClassId
            ? assignment.actual_scheduled_class_id
            : "";
      } else {
        assignment.actual_scheduled_class_id = currentClassId;
      }
      renderClasses();
      return;
    }
    if (field === "actual_scheduled_class_id") {
      const currentClassId = currentClass()?.id || assignment.class_id || "";
      const sourceClassId = classIdFromPickerValue(target.value) || target.value.trim();
      assignment.actual_scheduled_class_id = sourceClassId || currentClassId;
      delete assignment.schedule_mode;
      delete assignment.inherit_from_class_id;
      delete assignment.teacher_available_slots;
      if (sourceClassId && sourceClassId !== currentClassId) {
        assignment.class_schedule_mode = scheduleModeDisplayName("共享课表");
        assignment.teacher_id = "";
        assignment.teacher_name = "";
        assignment.assignment_extra_time_requirement = "";
      } else {
        assignment.class_schedule_mode = scheduleModeDisplayName("本班实际排课");
      }
      renderClasses();
      return;
    }
    assignment[field] = target.value;
    if (field === "teacher_id") {
      const teacher = teacherById(assignment.teacher_id);
      if (teacher) {
        applyAssignmentTeacher(assignment, teacher, row);
      }
    }
    if (field === "teacher_name") {
      const matches = teacherNameMatches(assignment.teacher_name);
      if (matches.length === 1) {
        applyAssignmentTeacher(assignment, matches[0], row);
        showStatus(`已按姓名匹配到教师ID：${matches[0].id}`, "ok");
        if (row?.querySelector(".teacher-match")) renderClasses();
      } else if (matches.length > 1) {
        if (!matches.some((teacher) => teacher.id === assignment.teacher_id)) assignment.teacher_id = "";
        showStatus(`存在 ${matches.length} 位同名老师，请在该行选择具体员工ID。`, "warning");
        renderClasses();
      } else {
        const currentTeacher = teacherById(assignment.teacher_id);
        if (currentTeacher && currentTeacher.name !== assignment.teacher_name) {
          assignment.teacher_id = "";
          const idInput = row?.querySelector('input[data-field="teacher_id"]');
          if (idInput) idInput.value = "";
        }
      }
    }
    return;
  }

  if (target.dataset.action === "rename-product-id") {
    const oldId = selected.productId;
    const newId = target.value.trim();
    syncProductId(oldId, newId);
    selected.productId = newId;
    return;
  }

  if (target.dataset.action === "rename-product-name") {
    syncProductName(selected.productId, target.value);
    for (const rule of state.product_schedule_rules) {
      if (rule.product_id === selected.productId) rule.product_name = target.value;
    }
  }
}

content.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const action = button.dataset.action;
  if (!action) return;
  if (mutatingButtonActions.has(action)) markUnsavedChange();

  if (action === "switch-tab") {
    switchTab(button.dataset.tab);
    return;
  }

  if (action === "select-area") selected.areaId = button.dataset.id;
  if (action === "add-area") addArea();
  if (action === "add-room") addRoom();
  if (action === "delete-room") state.rooms.splice(Number(button.dataset.index), 1);
  if (action === "add-teacher") addTeacher();
  if (action === "delete-teacher") state.teachers.splice(Number(button.dataset.index), 1);
  if (action === "add-teacher-unavailable") {
    addTeacherUnavailable();
    return;
  }
  if (action === "delete-teacher-unavailable") {
    state.teacher_unavailability.splice(Number(button.dataset.index), 1);
    renderTeacherUnavailable();
    return;
  }
  if (action === "select-product") {
    const productList = button.closest("[data-product-list]");
    if (productList) selected.productListScrollTop = productList.scrollTop;
    selected.productId = button.dataset.id;
    selected.courseFilters = emptyCourseFilters();
    updateProductListActive();
    refreshProductDetail();
    return;
  }
  if (action === "add-product") addProduct();
  if (action === "download-products") {
    downloadProductsCsv();
    return;
  }
  if (action === "import-products") {
    content.querySelector('input[data-action="import-products-file"]')?.click();
    return;
  }
  if (action === "clear-product-meta-filters") {
    selected.productSearch = "";
    selected.productMetaFilters = emptyProductTagFilters();
    renderProductMeta();
    return;
  }
  if (action === "clear-product-course-product-filters") {
    selected.productCourseProductFilters = emptyProductTagFilters();
    selected.productLineFilter = "";
    selected.productListScrollTop = 0;
    selected.courseFilters = emptyCourseFilters();
    renderProducts();
    return;
  }
  if (action === "clear-area-link-filters") {
    selected.areaLinkSearch = "";
    selected.areaLinkRelationFilter = "";
    selected.areaLinkIssueFilter = "";
    renderAreaLinks();
    return;
  }
  if (action === "download-classes") {
    downloadClassesCsv();
    return;
  }
  if (action === "import-classes") {
    content.querySelector('input[data-action="import-classes-file"]')?.click();
    return;
  }
  if (action === "clear-class-filters") {
    selected.classSearch = "";
    selected.classProductFilter = "";
    selected.classSubjectFilter = "";
    selected.classMetaFilters = emptyProductTagFilters();
    renderClassMeta();
    return;
  }
  if (action === "refresh-business-product-mappings") {
    ensureBusinessProductMappingRows();
    return;
  }
  if (action === "run-pipeline") {
    const input = content.querySelector('input[data-action="pipeline-files"]');
    uploadAndRunPipeline(input).catch((error) => showStatus(error.message, "error"));
    return;
  }
  if (action === "generate-template") {
    const input = content.querySelector('input[data-action="template-source-files"]');
    generateFormalTemplate(input).catch((error) => showStatus(error.message, "error"));
    return;
  }
  if (action === "run-preflight") {
    const input = content.querySelector('input[data-action="preflight-files"]');
    runPipelinePreflight(input).catch((error) => showStatus(error.message, "error"));
    return;
  }
  if (action === "run-batch-fast") {
    runBatchSchedule("fast").catch((error) => showStatus(error.message, "error"));
    return;
  }
  if (action === "run-batch-full") {
    runBatchSchedule("full").catch((error) => showStatus(error.message, "error"));
    return;
  }
  if (action === "refresh-product-tags") {
    const product = state.products[Number(button.dataset.index)] || productById(selected.productId);
    if (product) {
      applyProductAutoTags(product.id, true);
      for (const cls of state.classes || []) {
        if (cls.product_id === product.id) applyClassAutoTags(cls, true);
      }
    }
    showStatus("已按产品名称规则刷新项目、产品线、子产品和班容类型。", "ok");
  }
  if (action === "delete-product") {
    deleteProductAtIndex(Number(button.dataset.index));
  }
  if (action === "add-course") addCourse();
  if (action === "delete-course") state.product_courses.splice(Number(button.dataset.index), 1);
  if (action === "clear-course-filters") selected.courseFilters = emptyCourseFilters();
  if (action === "sync-course-name-tags") {
    syncCourseNameTagsFromModules();
    return;
  }
  if (action === "load-rule-templates") {
    loadScheduleRuleTemplates();
    return;
  }
  if (action === "clear-rule-filters") {
    selected.ruleSearch = "";
    selected.ruleWindowFilter = "";
    selected.ruleDeliveryFilter = "";
    selected.ruleIssueFilter = "";
    renderRules();
    return;
  }
  if (action === "add-rule") addRule();
  if (action === "delete-rule") state.product_schedule_rules.splice(Number(button.dataset.index), 1);
  if (action === "add-blackout") addBlackout();
  if (action === "delete-blackout") state.global_blackout_dates.splice(Number(button.dataset.index), 1);
  if (action === "add-schedule-window") {
    addScheduleWindow();
    return;
  }
  if (action === "generate-window-time-slots") {
    generateTimeSlotsForSingleWindow(button.dataset.index);
    return;
  }
  if (action === "generate-all-time-slots") {
    generateTimeSlotsForAllWindows();
    return;
  }
  if (action === "select-class") selected.classId = button.dataset.id;
  if (action === "edit-class-teachers") {
    selected.classId = button.dataset.id;
    activeTab = "classes";
    render();
    return;
  }
  if (action === "add-class") addClass();
  if (action === "delete-class") {
    deleteClassById(button.dataset.id);
  }
  if (action === "remove-class-area") {
    const cls = state.classes.find((item) => item.id === button.dataset.id);
    if (cls) {
      removeClassTeachingArea(cls, button.dataset.value);
      showStatus("已移除教学区，并同步筛掉不在所选教学区内的指定教室。", "ok");
      renderActiveClassView({ preservePosition: activeTab === "classMeta" });
    }
    return;
  }
  if (action === "remove-class-room") {
    const cls = state.classes.find((item) => item.id === button.dataset.id);
    if (cls) {
      removeClassRoom(cls, button.dataset.value);
      showStatus("已移除指定教室。", "ok");
      renderActiveClassView({ preservePosition: activeTab === "classMeta" });
    }
    return;
  }
  if (action === "remove-class-window-area") {
    const item = state.class_window_boundaries[Number(button.dataset.id)];
    if (item) {
      removeClassWindowTeachingArea(item, button.dataset.value);
      showStatus("已移除窗口教学区，并同步筛掉不在所选教学区内的窗口教室。", "ok");
      renderClassWindows();
    }
    return;
  }
  if (action === "remove-class-window-room") {
    const item = state.class_window_boundaries[Number(button.dataset.id)];
    if (item) {
      removeClassWindowRoom(item, button.dataset.value);
      showStatus("已移除窗口教室。", "ok");
      renderClassWindows();
    }
    return;
  }
  if (action === "refresh-class-tags") {
    const cls = currentClass();
    if (cls) {
      applyClassAutoTags(cls, true);
      showStatus("已同步所属产品标签。", "ok");
    }
  }
  if (action === "sync-teachers") {
    const count = syncTeachers();
    showStatus(`已同步当前班级 ${count} 条阶段/课程类别老师安排。记得点击“保存数据修改”。`, "ok");
  }
  if (action === "sync-all-teachers") syncAllClassTeachers();
  if (action === "delete-assignment") {
    const cls = currentClass();
    if (cls?.teacher_assignments) cls.teacher_assignments.splice(Number(button.dataset.index), 1);
  }
  if (action === "add-class-window") {
    addClassWindow();
    return;
  }
  if (action === "delete-class-window") {
    state.class_window_boundaries.splice(Number(button.dataset.index), 1);
    showStatus("已删除班级排课窗口，记得点击“保存数据修改”。", "ok");
    renderClassWindows();
    return;
  }
  if (action === "add-area-link") addAreaLink();
  if (action === "delete-area-link") state.teaching_area_links.splice(Number(button.dataset.index), 1);
  if (action === "add-class-conflict") {
    addClassConflictGroup();
    return;
  }
  if (action === "sync-suite-conflicts") {
    syncSuiteConflicts();
    return;
  }
  if (action === "remove-class-conflict-class") {
    removeClassConflictClass(Number(button.dataset.index), button.dataset.value);
    showStatus(`已移除互斥班级：${button.dataset.value}`, "ok");
    renderClassConflicts();
    return;
  }
  if (action === "delete-class-conflict") state.class_conflict_groups.splice(Number(button.dataset.index), 1);
  render();
});

document.querySelectorAll("[data-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    switchTab(button.dataset.tab);
  });
});

document.querySelector("#reloadBtn").addEventListener("click", () => loadData().catch((error) => showStatus(error.message, "error")));
for (const button of saveButtons) {
  button.addEventListener("click", () => saveData().catch((error) => showStatus(error.message, "error")));
}
document.querySelector("#exportBtn").addEventListener("click", () => exportSchedulerInput().catch((error) => showStatus(error.message, "error")));

updateSaveControls("正在准备本地数据...");
loadData().catch((error) => showStatus(error.message, "error"));
