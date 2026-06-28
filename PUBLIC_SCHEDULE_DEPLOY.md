# 预排课表公网只读发布

这个发布站只用于跨部门查看预排课表。它不会开放本地后台的数据维护、导入、保存或重排接口。

## 访问入口

- 主入口：`/schedule`
- 下载课表明细：`/download/schedule.csv`
- 下载排课报告：`/download/report.md`
- 健康检查：`/healthz`

发布站读取以下文件：

- `outputs/batch_schedule_maintenance.html`
- `outputs/batch_schedule_maintenance.csv`
- `outputs/batch_schedule_maintenance_report.md`

## 生成密码哈希

```bash
python3 schedule_publish_server.py --hash-password
```

复制输出值，作为部署平台环境变量 `SCHEDULE_VIEWER_PASSWORD_HASH`。

## 本地验证

```bash
export SCHEDULE_VIEWER_USERNAME="xdf"
export SCHEDULE_VIEWER_PASSWORD_HASH="上一步生成的哈希"
export SCHEDULE_VIEWER_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
PORT=8780 ./scripts/start_schedule_publish.sh
```

然后打开：

```text
http://127.0.0.1:8780/schedule
```

## 平台部署

任选一个支持 Python Web Service 的平台。仓库里已提供 `Procfile`：

```text
web: python schedule_publish_server.py
```

平台环境变量建议设置：

| 变量 | 用途 |
| --- | --- |
| `SCHEDULE_VIEWER_USERNAME` | 只读查看账号 |
| `SCHEDULE_VIEWER_PASSWORD_HASH` | 使用 `--hash-password` 生成的密码哈希 |
| `SCHEDULE_VIEWER_SECRET_KEY` | Cookie 签名密钥，建议 `secrets.token_urlsafe(48)` |
| `SCHEDULE_VIEWER_COOKIE_SECURE` | 公网 HTTPS 部署时设为 `1` |
| `SCHEDULE_VIEWER_SESSION_TTL_SECONDS` | 登录有效期，默认 12 小时 |
| `SCHEDULE_VIEWER_OUTPUT_DIR` | 输出目录，默认 `outputs` |

平台会提供 `PORT`，服务会自动读取。部署后访问平台给出的 HTTPS 地址加 `/schedule`。

## Cloudflare Pages 部署

Cloudflare Pages 不能直接运行 Python 服务，因此本项目提供了 Cloudflare 专用发布包。发布包使用 `_worker.js` 在 Cloudflare 边缘侧做登录、Cookie 和白名单文件访问。

生成发布包：

```bash
python3 scripts/build_cloudflare_publish_bundle.py
```

发布包目录：

```text
outputs/cloudflare_schedule_publish/
```

首次发布建议项目名：

```text
xdf-schedule-maintenance
```

用 Wrangler 登录并上传：

```bash
npx --yes wrangler login
PROJECT_NAME=xdf-schedule-maintenance ./scripts/deploy_cloudflare_schedule.sh
```

当前固定查看链接使用 `production` 分支别名：

```text
https://production.xdf-schedule-maintenance.pages.dev/schedule
```

Cloudflare Pages 环境变量需要配置：

| 变量 | 用途 |
| --- | --- |
| `SCHEDULE_VIEWER_USERNAME` | 只读查看账号 |
| `SCHEDULE_VIEWER_PASSWORD_HASH_V2` | Cloudflare 推荐使用的密码哈希，格式不含 `$`，迭代次数需不高于 Workers PBKDF2 上限 100000 |
| `SCHEDULE_VIEWER_PASSWORD_HASH` | 兼容旧格式，可使用 `schedule_publish_server.py --hash-password` 生成 |
| `SCHEDULE_VIEWER_SECRET_KEY` | Cookie 签名密钥，建议 `secrets.token_urlsafe(48)` |
| `SCHEDULE_VIEWER_COOKIE_SECURE` | 线上设为 `1` |

也可以用 Wrangler 写入密钥：

```bash
npx --yes wrangler pages secret put SCHEDULE_VIEWER_USERNAME --project-name xdf-schedule-maintenance
npx --yes wrangler pages secret put SCHEDULE_VIEWER_PASSWORD_HASH_V2 --project-name xdf-schedule-maintenance
npx --yes wrangler pages secret put SCHEDULE_VIEWER_SECRET_KEY --project-name xdf-schedule-maintenance
npx --yes wrangler pages secret put SCHEDULE_VIEWER_COOKIE_SECURE --project-name xdf-schedule-maintenance
```

如果使用 `--branch production` 发布到 `production.<project>.pages.dev`，这个分支别名属于 Pages 的 preview 环境，密钥也要带 `--env preview` 写入一份。不要用未转义的 `.env` bulk 写入旧版 `SCHEDULE_VIEWER_PASSWORD_HASH`，因为 `$` 分隔符容易被解析破坏。

如果通过 Cloudflare 控制台手动上传，选择 `Workers & Pages` -> `Create application` -> `Pages` -> `Upload assets`，上传 `outputs/cloudflare_schedule_publish/` 整个文件夹或压缩包。Direct Upload 支持 `_worker.js`，但请确认环境变量已配置后再访问 `/schedule`。

## 更新发布内容

本地继续用后台或脚本生成最新课表，然后把这三个输出文件同步到线上发布环境：

```text
outputs/batch_schedule_maintenance.html
outputs/batch_schedule_maintenance.csv
outputs/batch_schedule_maintenance_report.md
```

线上服务只读取这些文件，不会自行生成或修改课表。

## 安全边界

- 未登录访问 `/schedule` 和下载入口会跳转登录页。
- 只有白名单文件可以访问。
- `/api/save`、`/outputs/...`、`/data/...` 等管理或数据路径不会对外提供。
- 不要把本地后台管理服务绑定到公网地址。
