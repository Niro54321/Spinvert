// Spinvert share server: anyone using Spinvert can turn a screenshot into a link.
//
//   POST /upload               body: the PNG, JPEG or WebP bytes  ->  { url, image, delete, expires }
//   GET  /<id>                 a page showing the picture (with a link preview for chat apps)
//   GET  /<id>.<ext>           the picture itself
//   GET  /delete/<id>/<key>    asks to confirm; POST to the same address deletes it
//
// Pictures live in R2 under random ten-character names nobody can guess. Only the
// uploader gets the delete key; the bucket keeps a SHA-256 of it, not the key.

const ID = /^[A-Za-z0-9]{10}$/;
const KEY = /^[A-Za-z0-9]{24}$/;
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
const TYPES = { png: "image/png", jpg: "image/jpeg", webp: "image/webp" };

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    try {
      if (path === "/upload" && request.method === "POST") return await upload(request, env, url);
      if (path === "/" && request.method === "GET") return home(env);
      let m = path.match(/^\/delete\/([A-Za-z0-9]+)\/([A-Za-z0-9]+)$/);
      if (m && ID.test(m[1]) && KEY.test(m[2])) return await remove(request, env, m[1], m[2]);
      m = path.match(/^\/([A-Za-z0-9]+)\.(png|jpg|webp)$/);
      if (m && ID.test(m[1]) && request.method === "GET") return await picture(env, m[1], m[2]);
      m = path.match(/^\/([A-Za-z0-9]+)$/);
      if (m && ID.test(m[1]) && request.method === "GET") return await viewer(env, url, m[1]);
      return page(env, "Not found", "<p>There is no picture here.</p>", 404);
    } catch (e) {
      console.error(e);
      return json({ error: "Something went wrong on the server. Please try again." }, 500);
    }
  },
};

// ------------------------------------------------------------------ upload

async function upload(request, env, url) {
  const ip = request.headers.get("CF-Connecting-IP") || "local";
  if (env.UPLOADS) {
    const { success } = await env.UPLOADS.limit({ key: ip });
    if (!success) return json({ error: "Too many uploads. Please wait a minute." }, 429);
  }
  const max = Number(env.MAX_BYTES || 10485760);
  if (Number(request.headers.get("Content-Length") || 0) > max) return tooBig(max);
  const body = new Uint8Array(await request.arrayBuffer());
  if (body.length > max) return tooBig(max);
  const ext = kind(body);
  if (!ext) return json({ error: "Only PNG, JPEG and WebP pictures can be shared." }, 415);

  const id = random(10);
  const key = random(24);
  const days = Number(env.EXPIRE_DAYS || 365);
  const expires = new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
  await env.SHOTS.put(`${id}.${ext}`, body, {
    httpMetadata: { contentType: TYPES[ext] },
    customMetadata: { deleteHash: await sha256(key), uploaded: new Date().toISOString() },
  });
  const base = url.origin;
  return json({ url: `${base}/${id}`, image: `${base}/${id}.${ext}`, delete: `${base}/delete/${id}/${key}`, expires });
}

function tooBig(max) {
  return json({ error: `The picture is too big (the limit is ${Math.round(max / 1048576)} MB).` }, 413);
}

/** "png", "jpg" or "webp" from the file's first bytes, never from what the client claims. */
function kind(b) {
  if (b.length > 8 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47 &&
      b[4] === 0x0d && b[5] === 0x0a && b[6] === 0x1a && b[7] === 0x0a) return "png";
  if (b.length > 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "jpg";
  if (b.length > 12 && String.fromCharCode(...b.slice(0, 4)) === "RIFF" &&
      String.fromCharCode(...b.slice(8, 12)) === "WEBP") return "webp";
  return null;
}

/** Random letters and digits, without the bias a plain modulo would add. */
function random(length) {
  let out = "";
  while (out.length < length) {
    for (const byte of crypto.getRandomValues(new Uint8Array(length * 2))) {
      if (byte < 248 && out.length < length) out += ALPHABET[byte % 62];
    }
  }
  return out;
}

async function sha256(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ------------------------------------------------------------------ viewing

async function find(env, id) {
  for (const ext of Object.keys(TYPES)) {
    const head = await env.SHOTS.head(`${id}.${ext}`);
    if (head) return { ext, head };
  }
  return null;
}

async function picture(env, id, ext) {
  const obj = await env.SHOTS.get(`${id}.${ext}`);
  if (!obj) return new Response("Not found", { status: 404, headers: SAFE });
  return new Response(obj.body, {
    headers: {
      ...SAFE,
      "Content-Type": TYPES[ext],
      "Content-Length": String(obj.size),
      "Cache-Control": "public, max-age=86400",
      "Content-Security-Policy": "default-src 'none'; sandbox",
    },
  });
}

async function viewer(env, url, id) {
  const found = await find(env, id);
  if (!found) return page(env, "Not found", "<p>This picture was deleted or has expired.</p>", 404);
  const image = `${url.origin}/${id}.${found.ext}`;
  const meta = `<meta property="og:image" content="${image}"><meta name="twitter:card" content="summary_large_image">`;
  const body = `<a class="shot" href="${image}"><img src="${image}" alt="Screenshot"></a>
    <p class="row"><a class="btn" href="${image}" download>Download</a>${report(env, id)}</p>`;
  return page(env, "Screenshot", body, 200, meta);
}

function report(env, id) {
  const contact = (env.ABUSE_CONTACT || "").trim();
  if (!/^[^\s@<>"']+@[^\s@<>"']+$/.test(contact)) return "";
  return `<a class="btn quiet" href="mailto:${contact}?subject=Report%20picture%20${id}">Report</a>`;
}

// ------------------------------------------------------------------ deleting

async function remove(request, env, id, key) {
  const found = await find(env, id);
  if (!found || found.head.customMetadata?.deleteHash !== (await sha256(key))) {
    return page(env, "Not found", "<p>This picture was already deleted, or the link is wrong.</p>", 404);
  }
  if (request.method !== "POST") {
    // Chat apps open links to preview them, so deleting needs a press.
    return page(env, "Delete picture", `<p>Delete this picture for everyone?</p>
      <form method="post"><button class="btn danger" type="submit">Delete</button></form>`);
  }
  await env.SHOTS.delete(`${id}.${found.ext}`);
  return page(env, "Deleted", "<p>The picture is deleted. Its link no longer works.</p>");
}

// ------------------------------------------------------------------ pages

const SAFE = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Robots-Tag": "noindex, nofollow",
};

function home(env) {
  return page(env, "Spinvert share", `<p>Screenshots shared from
    <a href="${env.PROJECT_URL}">Spinvert</a>, the free file converter for Windows.</p>`);
}

function page(env, title, body, status = 200, meta = "") {
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">
<title>${title} · Spinvert</title>${meta}<style>
:root{color-scheme:dark;--bg:#0f1117;--card:rgba(255,255,255,.06);--line:rgba(255,255,255,.14);--text:#f2f3f7;--muted:#9aa0ad;--accent:#7c5cff}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;gap:18px;padding:28px 16px;
background:radial-gradient(1200px 600px at 20% -10%,#2a2150 0,transparent 60%),var(--bg);color:var(--text);font:15px/1.5 "Segoe UI",system-ui,sans-serif}
main{width:100%;max-width:1200px;display:flex;flex-direction:column;align-items:center;gap:16px;padding:18px;border:1px solid var(--line);
border-radius:18px;background:var(--card);backdrop-filter:blur(18px)}
.shot img{display:block;max-width:100%;max-height:78vh;border-radius:10px}
.row{display:flex;gap:10px;margin:0}.btn{border:1px solid var(--line);border-radius:999px;padding:7px 16px;color:var(--text);
background:rgba(255,255,255,.08);text-decoration:none;font:inherit;cursor:pointer}.btn:hover{background:rgba(255,255,255,.16)}
.quiet{color:var(--muted)}.danger{background:#d93f5c;border-color:#d93f5c}a{color:#b9a8ff}
footer{color:var(--muted);font-size:13px}</style></head><body><main>${body}</main>
<footer>Shared with <a href="${env.PROJECT_URL}">Spinvert</a></footer></body></html>`;
  return new Response(html, {
    status,
    headers: {
      ...SAFE,
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    },
  });
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...SAFE, "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
