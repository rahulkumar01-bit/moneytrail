# Moneytrail Gmail Agent

Watches a Gmail inbox for emails with the subject **"Moneytrail
Details"** and an `.xlsx` attachment, sends the attachment to your
deployed [web API](../webapi/README.md) for processing, and replies in
the same thread with the generated HTML report and PDF poster attached.

Runs entirely inside Google's own infrastructure (Google Apps Script) —
there's nothing to host for this part, no OAuth credentials to manage,
and no server that can go down independently of Gmail itself.

## Before you start

Deploy the web API first (see `../webapi/README.md`) and confirm
`https://YOUR-APP.onrender.com/health` returns `{"status": "ok"}`.
You'll need that URL below.

## Setup (about 5 minutes)

1. Go to **https://script.google.com** (sign in with the Gmail account
   you want this to watch) → **New project**.
2. Delete the placeholder `myFunction() {}` code, then paste in the
   entire contents of `MoneytrailAgent.gs`.
3. Near the top of the file, edit these three lines:
   ```javascript
   const RENDER_API_URL = 'https://YOUR-APP.onrender.com';   // your actual URL, no trailing slash
   const SUBJECT_FILTER = 'Moneytrail Details';                 // change only if you want a different subject
   const PROCESSED_LABEL_NAME = 'Moneytrail/Processed';           // fine to leave as-is
   ```
4. Save the project (any name is fine, e.g. "Moneytrail Agent").
5. In the function dropdown at the top of the editor, select **`setup`**,
   then click **Run**.
6. Google will prompt you to authorize the script — it's asking for
   Gmail read/send access, which is exactly what it needs to do its
   job. Click through **Advanced → Go to (project name) (unsafe)** if
   you see a warning screen — this is Google's standard warning for
   any script you haven't published/verified, not a sign anything is
   wrong with your own script.
7. Check the **Execution log** (View → Logs, or the log panel at the
   bottom) — it should say `Setup complete...`. That means two Gmail
   labels were created (`Moneytrail/Processed`, `Moneytrail/Failed`)
   and the 5-minute recurring trigger is installed.

That's it — it's live. You can close the tab; Apps Script keeps
running the trigger in the background regardless of whether the editor
is open.

## Testing it

Send yourself (or have someone send you) an email with subject exactly
**"Moneytrail Details"** and a `.xlsx` workbook attached. Either wait
up to 5 minutes for the trigger, or speed things up while testing: open
the script, select **`checkForMoneytrailEmails`** from the function
dropdown, and click **Run** to process immediately.

You should get a reply in the same thread within a minute or so, with
the HTML and PDF attached.

## How it behaves

- **Matching is exact-subject + has an .xlsx attachment.** Emails that
  don't match either condition are ignored entirely — this agent never
  touches anything else in the inbox.
- **Each thread is only ever processed once.** After a successful
  reply (or a permanent rejection — see below), the thread is labeled
  `Moneytrail/Processed` and excluded from all future searches, so
  re-running the trigger (or even the same email arriving twice) can't
  cause a duplicate reply.
- **A bad workbook gets a real answer, not silence.** If the API
  rejects the file (e.g. missing the required "Money Transfer to"
  sheet), the sender gets a reply explaining why, instead of the
  request just vanishing.
- **A down API gets retried, not given up on immediately.** If the web
  API is temporarily unreachable (e.g. mid cold-start, or briefly
  down), the thread is left unlabeled and retried on the next 5-minute
  pass. After 6 consecutive failures (~30 minutes), it stops retrying,
  labels the thread `Moneytrail/Failed`, and emails you (the script
  owner) an alert with the error detail — so a real outage doesn't
  fail silently forever. To retry after fixing the underlying problem,
  just remove the `Moneytrail/Failed` label from that thread.
- **Only looks at the last 2 days of mail** (`ONLY_NEWER_THAN_DAYS` in
  the config) — this is a safety net so that if the script is ever
  paused for a while, restarting it doesn't suddenly try to bulk-reply
  to a backlog of old matching threads. Raise it if you have a
  specific reason to.

## A note on timing

Google's time-driven triggers don't fire at an exact, guaranteed
second — actual firing can drift by up to a few minutes within the
configured interval, especially under load on Google's side. Combined
with the web API's occasional cold-start delay (up to ~60s), the
realistic worst case is roughly 5-7 minutes from email arrival to
reply, comfortably inside a 10-minute target with real margin — but
it's not a hard, contractually-guaranteed number, since neither Apps
Script's trigger timing nor Render's free-tier wake time are ones you
control directly.

## Customizing

- **Different email body wording**: edit the strings directly in
  `handleThread_` inside `MoneytrailAgent.gs`.
- **Faster than 5 minutes**: change `.everyMinutes(5)` in
  `installTrigger()` to `1`, then re-run `setup()` (or just
  `installTrigger()`) to replace the existing trigger. Apps Script
  supports triggers as frequent as every minute, though Google may
  introduce a small amount of jitter regardless.
- **Multiple recipients / a shared inbox**: this works the same way on
  a Google Workspace shared/group inbox as it does on a personal Gmail
  account — just run the setup from an account that has access to it.
