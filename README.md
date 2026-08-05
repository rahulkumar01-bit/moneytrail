# Money Trail Report Generator

A desktop app that takes a "BankAction_CompleteTrail" style Excel workbook
and produces:

1. **HTML Output** — the interactive, pan/zoom flowchart with a details
   panel per account (transactions, ATM cash withdrawals, cheque
   withdrawals, and hold amounts).
2. **Single-Sheet PDF Output** — the printable, card-style poster laid out
   left to right by layer.

The interface lets you upload a `.xlsx` file, tick which output(s) you
want, and generates them next to the source file (or a folder you choose).

**This same processing logic is also available two other ways:**
- **`webapi/`** — a hosted web API (deployable free on Render) that does
  the same extraction/HTML/PDF generation, for use by scripts or other
  services instead of the desktop UI. See `webapi/README.md`.
- **`automation/`** — a Gmail-watching agent (Google Apps Script, no
  separate hosting needed) that automatically processes `.xlsx`
  attachments emailed to a given inbox and replies with the results.
  Built on top of `webapi/`. See `automation/README.md`.

---

## 1. What's in this folder

```
MoneyTrailApp/
  core/
    extract.py         # reads the .xlsx into a plain data structure
    layout.py           # computes node positions for the HTML diagram
    html_gen.py          # fills the HTML template with the extracted data
    pdf_gen.py            # draws the single-sheet card PDF
    templates/
      money_trail_template.html   # the approved HTML look-and-feel
  gui/
    app.py                # the Tkinter desktop UI
  webapi/
    app.py                  # Flask API wrapping core/ for remote use
    README.md                 # how to deploy this on Render (free)
  automation/
    MoneytrailAgent.gs          # Gmail-watching agent (Google Apps Script)
    README.md                     # how to set it up
  Procfile                          # tells Render how to run webapi/app.py
  main.py                             # desktop app entry point
  requirements.txt
  build_windows.bat        # builds a Windows .exe (run ON Windows)
  build_macos.sh             # builds a macOS .app (run ON macOS)
```

## 2. Important note on how this was built and tested

Everything in `core/` (the Excel parsing, the HTML generation, and the PDF
generation) was written and **tested end-to-end** against your sample
workbook in the sandbox this was built in — the output matches the
reference HTML and PDF exactly.

The **GUI and native packaging could not be run or tested in that same
sandbox**, because it's a headless Linux container with no display server,
no `tkinter` package, and no internet access (so nothing could be
installed either). Tkinter and PyInstaller are both extremely standard,
well-documented tools and the code follows their normal patterns, but you
should do a first test run on your own machine before relying on it.

Also, **PyInstaller does not cross-compile** — a build run on Linux
produces a Linux binary, a build run on Windows produces a `.exe`, and a
build run on macOS produces a `.app`. That's why there are two separate
build scripts below: each one has to be run on its own operating system to
produce that OS's native app. There's no way around this from a single
machine; you (or a colleague) need brief access to a Windows PC and a Mac,
or a CI service that offers both.

**The web API (`webapi/`)** was tested end-to-end in that same sandbox —
ran the real Flask app (via its dev server, since `pip install gunicorn`
wasn't reachable without internet access, but that only changes which
WSGI server runs the identical app code, not the app's behavior), hit
`/health` and `/process` with a real workbook over an actual HTTP
request, and confirmed the output byte-for-byte matches calling the
`core/` pipeline directly. Confirmed the error paths too (missing
file, non-.xlsx upload, a workbook missing the required sheet).

**The Gmail agent (`automation/MoneytrailAgent.gs`)** can't run in this
sandbox at all — Apps Script only executes inside Google's own
infrastructure. Instead, it was tested by loading the actual script
into a JavaScript sandbox with every Google API it calls (`GmailApp`,
`UrlFetchApp`, `PropertiesService`, etc.) replaced with a mock, and
driving it through its real entry point (`checkForMoneytrailEmails`)
across four scenarios: a normal successful reply, a rejected/invalid
workbook (confirming the sender gets a real explanation, not silence),
six consecutive simulated server failures (confirming it retries
without spamming you, then gives up with exactly one alert email
rather than one per attempt), and an empty inbox (confirming it's a
clean no-op). All four passed. What that can't confirm is Google's own
infrastructure behavior — real OAuth consent screens, real trigger
timing/jitter, real Gmail search syntax execution — so do the "send
yourself a test email" step in `automation/README.md` once it's set up
before relying on it for anything time-sensitive.

## 3. Running it from source (quickest way to try it)

On any machine with Python 3.9+ installed:

```bash
cd MoneyTrailApp
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
python main.py
```

> **macOS note:** if you installed Python via Homebrew and get a
> `No module named '_tkinter'` error, run `brew install python-tk` (or use
> the official python.org installer, which bundles Tk already).

## 4. Building a standalone Windows .exe

On a Windows machine:

```
cd MoneyTrailApp
build_windows.bat
```

This creates a virtual environment, installs dependencies, and runs
PyInstaller. The finished app is at `dist\MoneyTrailReportGenerator.exe`
— a single file you can copy anywhere and double-click to run, no Python
installation required on the target PC.

## 5. Building a standalone macOS .app

On a Mac:

```
cd MoneyTrailApp
chmod +x build_macos.sh
./build_macos.sh
```

The finished app is at `dist/MoneyTrailReportGenerator.app`.

> **Gatekeeper note:** since this isn't signed with an Apple Developer
> certificate, the first time you (or anyone else) opens it, macOS will
> block it. Right-click the app → **Open** → **Open** again to approve it
> once. If you plan to distribute this beyond your own machine, you'll
> want to sign and notarize it with an Apple Developer account.

## 6. Using the app

1. **Browse...** and select your `.xlsx` source file. The upload box shows
   "Please upload the source file" until you do.
2. Tick **HTML Output** and/or **Single-Sheet PDF Output**.
3. (Optional) **Choose...** a save folder — otherwise output files are
   saved next to the source workbook.
4. Click **Generate Report**. When it finishes, each output shows an
   **Open** button.

## 7. Expected workbook format

The app expects the same sheet names and columns as your sample file:

- `Money Transfer to` (required) — the money-trail edges themselves
- `Withdrawal through ATM` (optional) — per-account cash withdrawal records
- `Cash Withdrawal through Cheque` (optional) — per-account cheque records
- `Transaction put on hold` (optional) — per-account hold amounts

If the optional sheets are missing, the app still runs — it just won't
have withdrawal/hold figures to show. If the required sheet is missing or
empty, you'll get a clear error message rather than a crash.

## 8. Customizing

- To change the HTML look and feel, edit
  `core/templates/money_trail_template.html` directly — `html_gen.py`
  only swaps in the data, so any styling changes you make there carry
  through automatically.
- To change the PDF card layout/colors, edit `core/pdf_gen.py`
  (`FIELD_COLORS`, `BOX_W`, `COL_GAP`, etc. near the top of the file).

## 9. Changelog - latest fixes

- **HTML: fixed "undefined" account labels.** Node objects were
  missing the `short` (last-4-digits) field the template's JS expects;
  `core/layout.py` now adds it.
- **HTML: layer spacing tripled** (`core/layout.py`, `COL_W`).
- **HTML: selection now persists on click.** Hovering still shows a
  quick preview highlight; clicking an account locks that highlight
  and the details panel open until you click empty canvas space (or
  close the panel), instead of vanishing the moment the mouse moves.
- **PDF: fixed the origin-accounts/Layer-0 overlap** with the
  complaint summary card — column 0 now starts far enough below the
  summary card's actual height instead of a fixed offset that didn't
  account for it.
- **PDF: layer spacing doubled** (`core/pdf_gen.py`, `COL_GAP`).
- **PDF: connector lines are now darker and thicker** for easier
  visual tracing across a dense diagram.
- **PDF: the Remarks field/section has been removed** from every
  transaction entry.
- **UI: HTML/PDF checkbox labels now reliably render** on all
  platforms — they were ttk.Checkbutton widgets whose text color could
  be silently overridden by the OS theme; switched to classic
  tk.Checkbutton widgets with explicit colors, matching the same fix
  already used elsewhere in this UI.

I was able to test and verify all of the extraction/layout/PDF logic
numerically in the sandbox this was built in (confirmed exact spacing
multipliers, confirmed zero overlap by coordinate math, confirmed the
Remarks text no longer appears anywhere in the PDF's extracted text,
confirmed every HTML node now carries a `short` value). I traced
through the click/hover JavaScript logic carefully but could not
execute it in an actual browser in that sandbox (no headless browser
available) — give the persistent-selection behavior a quick real
click-through once you have this running, in case anything about
real mouse/browser event timing differs from the trace.

