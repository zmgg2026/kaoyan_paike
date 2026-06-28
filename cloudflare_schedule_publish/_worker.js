const COOKIE_NAME = "schedule_viewer_session";
const DEFAULT_TTL_SECONDS = 12 * 60 * 60;

const SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "no-referrer",
  "Content-Security-Policy":
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'",
};

function textResponse(body, status = 200, headers = {}) {
  return new Response(body, {
    status,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      ...SECURITY_HEADERS,
      ...headers,
    },
  });
}

function htmlEscape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function base64ToBytes(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function bytesToBase64Url(bytes) {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function base64UrlToBytes(value) {
  const padded = value.replaceAll("-", "+").replaceAll("_", "/") + "=".repeat((4 - (value.length % 4)) % 4);
  return base64ToBytes(padded);
}

function bytesToHex(bytes) {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function constantTimeEqual(left, right) {
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let index = 0; index < left.length; index += 1) {
    diff |= left[index] ^ right[index];
  }
  return diff === 0;
}

function parsePasswordHash(encoded) {
  const text = String(encoded || "").trim();

  if (text.startsWith("pbkdf2_sha256_v2.")) {
    const parts = text.split(".");
    if (parts.length !== 4) {
      throw new Error("invalid password hash");
    }
    const iterations = Number.parseInt(parts[1], 10);
    if (!Number.isFinite(iterations) || iterations < 100000) {
      throw new Error("invalid hash iterations");
    }
    return {
      iterations,
      salt: base64UrlToBytes(parts[2]),
      digest: base64UrlToBytes(parts[3]),
    };
  }

  const parts = text.split("$");
  if (parts.length !== 4 || parts[0] !== "pbkdf2_sha256") {
    throw new Error("invalid password hash");
  }
  const iterations = Number.parseInt(parts[1], 10);
  if (!Number.isFinite(iterations) || iterations < 100000) {
    throw new Error("invalid hash iterations");
  }
  return {
    iterations,
    salt: base64ToBytes(parts[2]),
    digest: base64ToBytes(parts[3]),
  };
}

async function verifyPassword(password, encodedHash) {
  const parsed = parsePasswordHash(encodedHash);
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const derivedBits = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      hash: "SHA-256",
      salt: parsed.salt,
      iterations: parsed.iterations,
    },
    key,
    parsed.digest.length * 8,
  );
  return constantTimeEqual(new Uint8Array(derivedBits), parsed.digest);
}

async function signPayload(payloadText, secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payloadText));
  return bytesToHex(new Uint8Array(signature));
}

function getCookie(request, name) {
  const header = request.headers.get("Cookie") || "";
  for (const item of header.split(";")) {
    const [rawName, ...rest] = item.trim().split("=");
    if (rawName === name) return rest.join("=");
  }
  return "";
}

function sessionTtl(env) {
  const raw = Number.parseInt(env.SCHEDULE_VIEWER_SESSION_TTL_SECONDS || "", 10);
  return Number.isFinite(raw) && raw > 0 ? raw : DEFAULT_TTL_SECONDS;
}

function secureCookie(env) {
  return String(env.SCHEDULE_VIEWER_COOKIE_SECURE || "").toLowerCase() === "1";
}

async function makeSessionCookie(env) {
  const payload = {
    u: env.SCHEDULE_VIEWER_USERNAME,
    exp: Math.floor(Date.now() / 1000) + sessionTtl(env),
    n: crypto.randomUUID(),
  };
  const payloadText = bytesToBase64Url(new TextEncoder().encode(JSON.stringify(payload)));
  const signature = await signPayload(payloadText, env.SCHEDULE_VIEWER_SECRET_KEY);
  const secure = secureCookie(env) ? "; Secure" : "";
  return `${COOKIE_NAME}=${payloadText}.${signature}; Path=/; Max-Age=${sessionTtl(env)}; HttpOnly; SameSite=Lax${secure}`;
}

function clearSessionCookie(env) {
  const secure = secureCookie(env) ? "; Secure" : "";
  return `${COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax${secure}`;
}

async function isAuthenticated(request, env) {
  const rawCookie = getCookie(request, COOKIE_NAME);
  if (!rawCookie || !env.SCHEDULE_VIEWER_USERNAME || !env.SCHEDULE_VIEWER_SECRET_KEY) return false;
  const [payloadText, signature] = rawCookie.split(".");
  if (!payloadText || !signature) return false;
  const expected = await signPayload(payloadText, env.SCHEDULE_VIEWER_SECRET_KEY);
  if (signature !== expected) return false;
  try {
    const payload = JSON.parse(new TextDecoder().decode(base64UrlToBytes(payloadText)));
    return payload.u === env.SCHEDULE_VIEWER_USERNAME && Number(payload.exp || 0) >= Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

function redirect(location, status = 303, headers = {}) {
  return new Response(null, {
    status,
    headers: {
      Location: location,
      "Cache-Control": "no-store",
      ...SECURITY_HEADERS,
      ...headers,
    },
  });
}

function loginPage(error = "", status = 200) {
  const errorBlock = error ? `<p class="error">${htmlEscape(error)}</p>` : "";
  return new Response(`<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>预排课表只读查看</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #1f2933;
      background: #f4f7fb;
    }
    main {
      width: min(420px, calc(100vw - 32px));
      padding: 28px;
      background: #fff;
      border: 1px solid #d9e2ec;
      border-radius: 8px;
      box-shadow: 0 16px 48px rgba(15, 23, 42, 0.12);
    }
    h1 { margin: 0 0 8px; font-size: 24px; }
    p { margin: 0 0 20px; color: #52606d; line-height: 1.6; }
    label { display: block; margin: 14px 0 6px; font-weight: 600; }
    input {
      width: 100%;
      height: 42px;
      padding: 8px 10px;
      border: 1px solid #bcccdc;
      border-radius: 6px;
      font-size: 16px;
    }
    button {
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
    }
    .error {
      padding: 10px 12px;
      border-radius: 6px;
      color: #9f1239;
      background: #fff1f2;
    }
  </style>
</head>
<body>
  <main>
    <h1>预排课表只读查看</h1>
    <p>请输入查看账号。登录后只能查看和下载课表，不能修改排课数据。</p>
    ${errorBlock}
    <form method="post" action="/login">
      <label for="username">账号</label>
      <input id="username" name="username" autocomplete="username" required autofocus>
      <label for="password">密码</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">登录查看课表</button>
    </form>
  </main>
</body>
</html>`, {
    status,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      ...SECURITY_HEADERS,
    },
  });
}

function withSecurityHeaders(response, extraHeaders = {}) {
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries(SECURITY_HEADERS)) headers.set(key, value);
  for (const [key, value] of Object.entries(extraHeaders)) headers.set(key, value);
  headers.set("Cache-Control", "no-cache, no-store, must-revalidate");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function serveAsset(request, env, assetPath, extraHeaders = {}) {
  const url = new URL(request.url);
  url.pathname = assetPath;
  url.search = "";
  const response = await env.ASSETS.fetch(new Request(url, request));
  if (response.status === 404) return textResponse("发布文件不存在\n", 503);
  return withSecurityHeaders(response, extraHeaders);
}

async function requireAuth(request, env) {
  return (await isAuthenticated(request, env)) ? null : redirect("/login");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === "/healthz") {
      return textResponse("ok\n", 200, { "Cache-Control": "no-cache" });
    }

    if (path === "/") {
      return redirect((await isAuthenticated(request, env)) ? "/schedule" : "/login");
    }

    if (path === "/login" && request.method === "GET") {
      return (await isAuthenticated(request, env)) ? redirect("/schedule") : loginPage();
    }

    if (path === "/login" && request.method === "POST") {
      const passwordHash = env.SCHEDULE_VIEWER_PASSWORD_HASH_V2 || env.SCHEDULE_VIEWER_PASSWORD_HASH;
      if (!env.SCHEDULE_VIEWER_USERNAME || !passwordHash || !env.SCHEDULE_VIEWER_SECRET_KEY) {
        return textResponse("发布服务缺少登录环境变量\n", 503);
      }
      const form = await request.formData();
      const username = String(form.get("username") || "").trim();
      const password = String(form.get("password") || "");
      const ok = username === env.SCHEDULE_VIEWER_USERNAME && await verifyPassword(password, passwordHash);
      if (!ok) return loginPage("账号或密码不正确", 401);
      return redirect("/schedule", 303, { "Set-Cookie": await makeSessionCookie(env) });
    }

    if (path === "/logout") {
      return redirect("/login", 303, { "Set-Cookie": clearSessionCookie(env) });
    }

    if (path === "/schedule" && (request.method === "GET" || request.method === "HEAD")) {
      const authResponse = await requireAuth(request, env);
      if (authResponse) return authResponse;
      return serveAsset(request, env, "/schedule_content.txt", { "Content-Type": "text/html; charset=utf-8" });
    }

    if (path === "/download/schedule.csv" && (request.method === "GET" || request.method === "HEAD")) {
      const authResponse = await requireAuth(request, env);
      if (authResponse) return authResponse;
      return serveAsset(request, env, "/schedule.csv", {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="batch_schedule_maintenance.csv"',
      });
    }

    if (path === "/download/report.md" && (request.method === "GET" || request.method === "HEAD")) {
      const authResponse = await requireAuth(request, env);
      if (authResponse) return authResponse;
      return serveAsset(request, env, "/report.md", {
        "Content-Type": "text/markdown; charset=utf-8",
        "Content-Disposition": 'attachment; filename="batch_schedule_maintenance_report.md"',
      });
    }

    return textResponse("未找到该页面\n", 404);
  },
};
