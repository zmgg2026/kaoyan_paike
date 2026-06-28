from __future__ import annotations

import http.cookiejar
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import schedule_publish_server


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def start_server(output_dir: Path) -> tuple[schedule_publish_server.SchedulePublishHTTPServer, threading.Thread, str]:
    config = schedule_publish_server.PublishConfig(
        username="viewer",
        password_hash=schedule_publish_server.hash_password("secret"),
        secret_key="test-secret-key-for-schedule-publish-server",
        output_dir=output_dir,
        session_ttl_seconds=3600,
    )
    server = schedule_publish_server.SchedulePublishHTTPServer(("127.0.0.1", 0), config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


class SchedulePublishServerTest(unittest.TestCase):
    def test_auth_gate_and_readonly_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "batch_schedule_maintenance.html").write_text("<html><body>课表维护页</body></html>", encoding="utf-8")
            (output_dir / "batch_schedule_maintenance.csv").write_text("class_id,date\nC1,2026-07-01\n", encoding="utf-8")
            (output_dir / "batch_schedule_maintenance_report.md").write_text("# 排课报告\n", encoding="utf-8")

            server, thread, base_url = start_server(output_dir)
            try:
                no_redirect = urllib.request.build_opener(NoRedirectHandler)
                with self.assertRaises(urllib.error.HTTPError) as schedule_error:
                    no_redirect.open(f"{base_url}/schedule", timeout=10)
                self.assertEqual(schedule_error.exception.code, 303)
                self.assertEqual(schedule_error.exception.headers["Location"], "/login")

                cookie_jar = http.cookiejar.CookieJar()
                opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
                payload = urllib.parse.urlencode({"username": "viewer", "password": "secret"}).encode("utf-8")
                request = urllib.request.Request(f"{base_url}/login", data=payload, method="POST")
                with opener.open(request, timeout=10) as response:
                    body = response.read().decode("utf-8")
                self.assertIn("课表维护页", body)

                with opener.open(f"{base_url}/download/schedule.csv", timeout=10) as response:
                    self.assertIn("attachment", response.headers["Content-Disposition"])
                    self.assertIn("C1,2026-07-01", response.read().decode("utf-8"))

                with opener.open(f"{base_url}/download/report.md", timeout=10) as response:
                    self.assertIn("# 排课报告", response.read().decode("utf-8"))

                for path in ("/api/save", "/outputs/batch_schedule_maintenance.html", "/data/classes.json"):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        opener.open(f"{base_url}{path}", timeout=10)
                    self.assertEqual(error.exception.code, 404)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

    def test_invalid_login_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "batch_schedule_maintenance.html").write_text("<html></html>", encoding="utf-8")
            (output_dir / "batch_schedule_maintenance.csv").write_text("", encoding="utf-8")
            (output_dir / "batch_schedule_maintenance_report.md").write_text("", encoding="utf-8")

            server, thread, base_url = start_server(output_dir)
            try:
                payload = urllib.parse.urlencode({"username": "viewer", "password": "wrong"}).encode("utf-8")
                request = urllib.request.Request(f"{base_url}/login", data=payload, method="POST")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request, timeout=10)
                self.assertEqual(error.exception.code, 401)
                self.assertIn("账号或密码不正确", error.exception.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()


if __name__ == "__main__":
    unittest.main()
