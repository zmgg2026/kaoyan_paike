#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import time
from dataclasses import dataclass
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse
import html as html_lib


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = ROOT / "outputs"
HASH_PREFIX = "pbkdf2_sha256"
DEFAULT_HASH_ITERATIONS = 310_000


def b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64decode(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))


def hash_password(password: str, *, iterations: int = DEFAULT_HASH_ITERATIONS, salt: Optional[bytes] = None) -> str:
    if not password:
        raise ValueError("密码不能为空")
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
    return f"{HASH_PREFIX}${iterations}${b64encode(salt_bytes)}${b64encode(digest)}"


def parse_password_hash(encoded_hash: str) -> tuple[int, bytes, bytes]:
    prefix, iterations_text, salt_text, digest_text = encoded_hash.split("$", 3)
    if prefix != HASH_PREFIX:
        raise ValueError("unsupported hash prefix")
    iterations = int(iterations_text)
    salt = b64decode(salt_text)
    expected = b64decode(digest_text)
    if iterations < 100_000 or not salt or not expected:
        raise ValueError("weak or incomplete hash")
    return iterations, salt, expected


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        iterations, salt, expected = parse_password_hash(encoded_hash)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class PublishConfig:
    username: str
    password_hash: str
    secret_key: str
    output_dir: Path = DEFAULT_OUTPUT_DIR
    session_ttl_seconds: int = 12 * 60 * 60
    cookie_secure: bool = False
    cookie_name: str = "schedule_viewer_session"

    @property
    def schedule_html(self) -> Path:
        return self.output_dir / "batch_schedule_maintenance.html"

    @property
    def schedule_csv(self) -> Path:
        return self.output_dir / "batch_schedule_maintenance.csv"

    @property
    def report_md(self) -> Path:
        return self.output_dir / "batch_schedule_maintenance_report.md"


def load_config_from_env() -> PublishConfig:
    username = os.environ.get("SCHEDULE_VIEWER_USERNAME", "").strip()
    password_hash_text = os.environ.get("SCHEDULE_VIEWER_PASSWORD_HASH", "").strip()
    secret_key = os.environ.get("SCHEDULE_VIEWER_SECRET_KEY", "").strip()
    output_dir = Path(os.environ.get("SCHEDULE_VIEWER_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))).expanduser()
    ttl = int(os.environ.get("SCHEDULE_VIEWER_SESSION_TTL_SECONDS", str(12 * 60 * 60)))
    cookie_secure = env_bool("SCHEDULE_VIEWER_COOKIE_SECURE", False)

    missing = [
        name
        for name, value in (
            ("SCHEDULE_VIEWER_USERNAME", username),
            ("SCHEDULE_VIEWER_PASSWORD_HASH", password_hash_text),
            ("SCHEDULE_VIEWER_SECRET_KEY", secret_key),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("缺少只读发布服务环境变量: " + ", ".join(missing))
    if len(secret_key) < 32:
        raise RuntimeError("SCHEDULE_VIEWER_SECRET_KEY 至少需要 32 个字符")
    try:
        parse_password_hash(password_hash_text)
    except Exception as exc:
        raise RuntimeError("SCHEDULE_VIEWER_PASSWORD_HASH 格式不正确，请用 --hash-password 生成") from exc

    return PublishConfig(
        username=username,
        password_hash=password_hash_text,
        secret_key=secret_key,
        output_dir=output_dir.resolve(),
        session_ttl_seconds=ttl,
        cookie_secure=cookie_secure,
    )


class SchedulePublishHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], config: PublishConfig):
        super().__init__(server_address, SchedulePublishHandler)
        self.config = config


class SchedulePublishHandler(BaseHTTPRequestHandler):
    server_version = "SchedulePublish/1.0"

    @property
    def config(self) -> PublishConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - - [{self.log_date_time_string()}] {format % args}")

    def add_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "base-uri 'none'; frame-ancestors 'none'",
        )

    def send_bytes(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "text/plain; charset=utf-8",
        attachment_name: str = "",
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        if attachment_name:
            self.send_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
        self.add_security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def redirect(self, location: str, *, status: int = 303) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.add_security_headers()
        self.end_headers()

    def not_found(self) -> None:
        self.send_bytes("未找到该页面\n".encode("utf-8"), status=404)

    def service_unavailable(self, message: str) -> None:
        self.send_bytes((message + "\n").encode("utf-8"), status=503)

    def make_session_cookie(self, username: str) -> str:
        payload = {
            "u": username,
            "exp": int(time.time()) + self.config.session_ttl_seconds,
            "n": secrets.token_urlsafe(12),
        }
        payload_text = b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
        signature = hmac.new(self.config.secret_key.encode("utf-8"), payload_text.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{payload_text}.{signature}"

    def verify_session_cookie(self, raw_value: str) -> bool:
        try:
            payload_text, signature = raw_value.split(".", 1)
            expected = hmac.new(self.config.secret_key.encode("utf-8"), payload_text.encode("ascii"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return False
            payload = json.loads(b64url_decode(payload_text).decode("utf-8"))
            if payload.get("u") != self.config.username:
                return False
            return int(payload.get("exp", 0)) >= int(time.time())
        except Exception:
            return False

    def is_authenticated(self) -> bool:
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return False
        jar = cookies.SimpleCookie()
        try:
            jar.load(cookie_header)
        except cookies.CookieError:
            return False
        morsel = jar.get(self.config.cookie_name)
        return bool(morsel and self.verify_session_cookie(morsel.value))

    def set_session_cookie(self) -> None:
        cookie = cookies.SimpleCookie()
        cookie[self.config.cookie_name] = self.make_session_cookie(self.config.username)
        cookie[self.config.cookie_name]["httponly"] = True
        cookie[self.config.cookie_name]["path"] = "/"
        cookie[self.config.cookie_name]["samesite"] = "Lax"
        cookie[self.config.cookie_name]["max-age"] = str(self.config.session_ttl_seconds)
        if self.config.cookie_secure:
            cookie[self.config.cookie_name]["secure"] = True
        for value in cookie.values():
            self.send_header("Set-Cookie", value.OutputString())

    def clear_session_cookie(self) -> None:
        cookie = cookies.SimpleCookie()
        cookie[self.config.cookie_name] = ""
        cookie[self.config.cookie_name]["path"] = "/"
        cookie[self.config.cookie_name]["max-age"] = "0"
        cookie[self.config.cookie_name]["httponly"] = True
        cookie[self.config.cookie_name]["samesite"] = "Lax"
        if self.config.cookie_secure:
            cookie[self.config.cookie_name]["secure"] = True
        for value in cookie.values():
            self.send_header("Set-Cookie", value.OutputString())

    def require_auth(self) -> bool:
        if self.is_authenticated():
            return True
        self.redirect("/login")
        return False

    def send_login_page(self, *, status: int = 200, error: str = "") -> None:
        error_html = f'<p class="error">{html_lib.escape(error)}</p>' if error else ""
        body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>预排课表只读查看</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #1f2933;
      background: #f4f7fb;
    }}
    main {{
      width: min(420px, calc(100vw - 32px));
      padding: 28px;
      background: #fff;
      border: 1px solid #d9e2ec;
      border-radius: 8px;
      box-shadow: 0 16px 48px rgba(15, 23, 42, 0.12);
    }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    p {{ margin: 0 0 20px; color: #52606d; line-height: 1.6; }}
    label {{ display: block; margin: 14px 0 6px; font-weight: 600; }}
    input {{
      width: 100%;
      height: 42px;
      padding: 8px 10px;
      border: 1px solid #bcccdc;
      border-radius: 6px;
      font-size: 16px;
    }}
    button {{
      width: 100%;
      height: 44px;
      margin-top: 20px;
      border: 0;
      border-radius: 6px;
      background: #1d4ed8;
      color: #fff;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
    }}
    .error {{
      padding: 10px 12px;
      border-radius: 6px;
      color: #9f1239;
      background: #fff1f2;
    }}
  </style>
</head>
<body>
  <main>
    <h1>预排课表只读查看</h1>
    <p>请输入查看账号。登录后只能查看和下载课表，不能修改排课数据。</p>
    {error_html}
    <form method="post" action="/login">
      <label for="username">账号</label>
      <input id="username" name="username" autocomplete="username" required autofocus>
      <label for="password">密码</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">登录查看课表</button>
    </form>
  </main>
</body>
</html>
"""
        self.send_bytes(body.encode("utf-8"), status=status, content_type="text/html; charset=utf-8")

    def send_file(self, path: Path, *, content_type: str = "", attachment_name: str = "") -> None:
        if not path.exists() or not path.is_file():
            self.service_unavailable(f"发布文件不存在: {path.name}")
            return
        resolved = path.resolve()
        output_root = self.config.output_dir.resolve()
        if output_root != resolved.parent and output_root not in resolved.parents:
            self.not_found()
            return
        guessed_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_bytes(
            resolved.read_bytes(),
            content_type=guessed_type,
            attachment_name=attachment_name,
            cache_control="no-cache, no-store, must-revalidate",
        )

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self.send_bytes(b"ok\n", content_type="text/plain; charset=utf-8", cache_control="no-cache")
            return
        if path == "/login":
            if self.is_authenticated():
                self.redirect("/schedule")
            else:
                self.send_login_page()
            return
        if path == "/logout":
            self.send_response(303)
            self.send_header("Location", "/login")
            self.send_header("Cache-Control", "no-store")
            self.clear_session_cookie()
            self.add_security_headers()
            self.end_headers()
            return
        if path == "/":
            self.redirect("/schedule" if self.is_authenticated() else "/login")
            return
        if path == "/schedule":
            if self.require_auth():
                self.send_file(self.config.schedule_html, content_type="text/html; charset=utf-8")
            return
        if path == "/download/schedule.csv":
            if self.require_auth():
                self.send_file(self.config.schedule_csv, content_type="text/csv; charset=utf-8", attachment_name="batch_schedule_maintenance.csv")
            return
        if path == "/download/report.md":
            if self.require_auth():
                self.send_file(self.config.report_md, content_type="text/markdown; charset=utf-8", attachment_name="batch_schedule_maintenance_report.md")
            return
        self.not_found()

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/login":
            self.not_found()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > 8192:
            self.send_login_page(status=413, error="提交内容过大")
            return
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        form = parse_qs(body, keep_blank_values=True)
        username = form.get("username", [""])[0].strip()
        password = form.get("password", [""])[0]
        if username == self.config.username and verify_password(password, self.config.password_hash):
            self.send_response(303)
            self.send_header("Location", "/schedule")
            self.send_header("Cache-Control", "no-store")
            self.set_session_cookie()
            self.add_security_headers()
            self.end_headers()
            return
        self.send_login_page(status=401, error="账号或密码不正确")


def main() -> None:
    parser = argparse.ArgumentParser(description="预排课表公网只读发布服务")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", default=int(os.environ.get("PORT", "8000")), type=int)
    parser.add_argument("--hash-password", nargs="?", const=True, metavar="PASSWORD", help="生成 SCHEDULE_VIEWER_PASSWORD_HASH 后退出；不带参数时安全输入密码")
    args = parser.parse_args()

    if args.hash_password is not None:
        if args.hash_password is True:
            password = getpass.getpass("请输入查看密码: ")
            confirm = getpass.getpass("请再次输入查看密码: ")
            if password != confirm:
                raise SystemExit("两次密码不一致")
        else:
            password = str(args.hash_password)
        print(hash_password(password))
        return

    config = load_config_from_env()
    server = SchedulePublishHTTPServer((args.host, args.port), config)
    print(f"预排课表只读发布服务已启动: http://{args.host}:{args.port}/schedule")
    server.serve_forever()


if __name__ == "__main__":
    main()
