# Money Trail Web API

A thin Flask wrapper around the same `core/` pipeline the desktop app
uses. One endpoint: send it an `.xlsx`, get back the HTML report and
PDF poster. This is what the Gmail agent (see `../automation/`) calls
to actually do the processing.

This does **not** send any email itself — that's entirely the Apps
Script agent's job. This service is stateless and has no secrets to
configure.

## 1. Test it locally first (optional but recommended)

```bash
cd MoneyTrailApp
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r webapi/requirements.txt
python webapi/app.py
```

Then in another terminal:

```bash
curl -X POST http://127.0.0.1:5001/process \
  -F "file=@/path/to/your/workbook.xlsx" \
  -o response.json
```

`response.json` will contain `html_base64` and `pdf_base64` fields —
that's the whole contract.

## 2. Deploy to Render (free tier)

1. Push this whole `MoneyTrailApp/` folder to a GitHub repo (same repo
   you can also build the desktop app from — nothing here conflicts
   with `main.py` / `gui/`).
2. Render dashboard → **New** → **Web Service** → connect that repo.
3. **Runtime**: Python 3.
4. **Build command**: `pip install -r webapi/requirements.txt`
5. **Start command**: `cd webapi && gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120`
   (this is also in the included `Procfile`, which Render should
   detect automatically — the explicit build/start commands above are
   just there in case it doesn't).
6. **Instance type**: Free.
7. Click **Create Web Service**. You'll get a URL like
   `https://money-trail-api.onrender.com`.
8. Confirm it's alive: `curl https://YOUR-APP.onrender.com/health`
   should return `{"status": "ok"}` (give it up to a minute on the
   very first request — free instances cold-start).

That URL is what you'll paste into the Apps Script config in the next
step (see `../automation/README.md`).

## 3. What to expect on the free tier

- **Cold starts.** Render's free web services sleep after 15 minutes
  of no traffic and take roughly 30-60 seconds to wake up on the next
  request. The Apps Script agent accounts for this with a generous
  timeout — the occasional slow reply is expected behavior, not a bug.
- **No persistent storage needed.** Every request is processed in a
  temp directory that's cleaned up immediately after — there's nothing
  to back up or lose between requests.
- **Upload size cap.** Set to 15 MB in `app.py`
  (`MAX_UPLOAD_MB`) — comfortably more than these workbooks need, but
  raise it there if you ever hit it.
