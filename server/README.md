# Spinvert share server

Turns a Spinvert screenshot into a link, like Lightshot. It's a small
[Cloudflare Worker](https://developers.cloudflare.com/workers/) that keeps the
pictures in [R2](https://developers.cloudflare.com/r2/).

| Request | What it does |
| --- | --- |
| `POST /upload` | Body: the PNG, JPEG or WebP bytes. Returns `{url, image, delete, expires}` |
| `GET /<id>` | A page showing the picture, with a preview for chat apps |
| `GET /<id>.png` | The picture itself |
| `GET /delete/<id>/<key>` | Asks to confirm; `POST` to the same address deletes it |

**Safety:**
- The server checks a file's first bytes, so nothing but real pictures is
  stored (no SVG or HTML).
- The limit is 10 MB per picture, and uploads are rate-limited per visitor.
- Names are ten random characters, so links can't be guessed.
- Pages say `noindex`, so search engines skip them.
- The delete key is stored only as a SHA-256 hash.
- A delete link needs a button press, so a chat app's link preview can't delete a picture.

## Run it yourself

```bash
cd server
npm install
npx wrangler dev          # a local server at http://127.0.0.1:8787, with local storage
```

To test Spinvert against it, set *Settings → Share server* to `http://127.0.0.1:8787`.

## Put it online

You need a free Cloudflare account. R2 asks for a payment method even on the
free tier: 10 GB of storage and unlimited viewing.

```bash
cd server
npx wrangler login
npx wrangler r2 bucket create spinvert-shots
npx wrangler r2 bucket lifecycle add spinvert-shots expire-after-a-year --expire-days 365
npx wrangler deploy
```

Set `ABUSE_CONTACT` in `wrangler.toml` to an email address before you share
the server with others. A *Report* button then appears on every picture page.
With your own domain on Cloudflare, also turn on Cloudflare's free CSAM Scanning
Tool for it.
