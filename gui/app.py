"""
Money Trail Report Generator
-----------------------------
A small, modern-styled desktop GUI (Tkinter/ttk - ships with standard
Python on Windows and macOS, so no extra runtime is needed) that wraps
the core extraction / HTML / PDF generation pipeline.

Run directly with:  python -m gui.app
(from the project root, with the venv/requirements installed)
"""

import os
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

# allow running this file directly (python gui/app.py) as well as as a module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.extract import extract_data, ExtractionError
from core.html_gen import generate_html
from core.pdf_gen import generate_pdf


# ---------------------------------------------------------------- palette
BG = "#0f1115"
PANEL = "#161a22"
PANEL2 = "#1d2330"
BORDER = "#2a3140"
TEXT = "#e8eaf0"
TEXT_DIM = "#9aa3b5"
TEXT_MUTE = "#6b7386"
ACCENT = "#4d8eff"
ACCENT_HOVER = "#6fa2ff"
GREEN = "#5fbf5f"
RED = "#e0654a"

FONT_FAMILY = "Segoe UI" if sys.platform.startswith("win") else "Helvetica"


class MoneyTrailApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Money Trail Report Generator")
        self.geometry("620x560")
        self.minsize(560, 520)
        self.configure(bg=BG)

        self.source_path = None
        self.output_dir = None
        self.html_var = tk.BooleanVar(value=True)
        self.pdf_var = tk.BooleanVar(value=True)

        self._build_style()
        self._build_ui()

    # ------------------------------------------------------------ styling
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure(
            "TLabel", background=BG, foreground=TEXT,
            font=(FONT_FAMILY, 10),
        )
        style.configure(
            "Title.TLabel", background=BG, foreground=TEXT,
            font=(FONT_FAMILY, 18, "bold"),
        )
        style.configure(
            "Subtitle.TLabel", background=BG, foreground=TEXT_DIM,
            font=(FONT_FAMILY, 10),
        )
        style.configure(
            "Section.TLabel", background=BG, foreground=TEXT_MUTE,
            font=(FONT_FAMILY, 10, "bold"),
        )
        style.configure(
            "FileName.TLabel", background=PANEL2, foreground=TEXT,
            font=(FONT_FAMILY, 10), padding=10,
        )
        style.configure(
            "Placeholder.TLabel", background=PANEL2, foreground=TEXT_MUTE,
            font=(FONT_FAMILY, 10, "italic"), padding=10,
        )
        style.configure(
            "Status.TLabel", background=BG, foreground=TEXT_DIM,
            font=(FONT_FAMILY, 9),
        )

        style.configure(
            "TCheckbutton", background=BG, foreground=TEXT,
            font=(FONT_FAMILY, 10),
        )
        style.map("TCheckbutton", background=[("active", BG)])

        style.configure(
            "Accent.TButton", font=(FONT_FAMILY, 11, "bold"),
            foreground="#0b0d11", background=ACCENT, padding=10, borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#3a4258")])

        style.configure(
            "Secondary.TButton", font=(FONT_FAMILY, 10),
            foreground=TEXT, background=PANEL2, padding=8, borderwidth=1,
        )
        style.map("Secondary.TButton", background=[("active", "#242c3c")])

        style.configure(
            "Horizontal.TProgressbar", troughcolor=PANEL2,
            background=ACCENT, bordercolor=PANEL2, lightcolor=ACCENT, darkcolor=ACCENT,
        )

    # ------------------------------------------------------------ layout
    def _build_ui(self):
        pad = 24

        header = ttk.Frame(self, style="TFrame")
        header.pack(fill="x", padx=pad, pady=(pad, 4))
        ttk.Label(header, text="Money Trail Report Generator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Upload a bank-action trail workbook and generate the flowchart HTML and/or PDF report.",
            style="Subtitle.TLabel", wraplength=560, justify="left",
        ).pack(anchor="w", pady=(4, 0))

        # ---------------- file upload section ----------------
        upload_section = ttk.Frame(self, style="TFrame")
        upload_section.pack(fill="x", padx=pad, pady=(20, 4))
        ttk.Label(upload_section, text="SOURCE FILE", style="Section.TLabel").pack(anchor="w")

        upload_box = tk.Frame(self, bg=PANEL2, highlightbackground=BORDER, highlightthickness=1)
        upload_box.pack(fill="x", padx=pad, pady=(6, 0))

        self.file_label = ttk.Label(
            upload_box, text="Please upload the source file",
            style="Placeholder.TLabel", anchor="w",
        )
        self.file_label.pack(side="left", fill="x", expand=True)

        browse_btn = ttk.Button(
            upload_box, text="Browse...", style="Secondary.TButton",
            command=self._on_browse,
        )
        browse_btn.pack(side="right", padx=10, pady=8)

        # ---------------- output options ----------------
        opts_section = ttk.Frame(self, style="TFrame")
        opts_section.pack(fill="x", padx=pad, pady=(24, 4))
        ttk.Label(opts_section, text="OUTPUT FORMAT", style="Section.TLabel").pack(anchor="w")

        opts_box = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        opts_box.pack(fill="x", padx=pad, pady=(6, 0))

        cb1 = tk.Checkbutton(
            opts_box, text="HTML Output  (interactive flowchart, opens in your browser)",
            variable=self.html_var, bg=PANEL, fg=TEXT, activebackground=PANEL,
            activeforeground=TEXT, selectcolor=PANEL2, highlightthickness=0,
            bd=0, font=(FONT_FAMILY, 10), anchor="w",
        )
        cb1.pack(anchor="w", padx=14, pady=(12, 6), fill="x")

        cb2 = tk.Checkbutton(
            opts_box, text="Single-Sheet PDF Output  (printable card-style poster)",
            variable=self.pdf_var, bg=PANEL, fg=TEXT, activebackground=PANEL,
            activeforeground=TEXT, selectcolor=PANEL2, highlightthickness=0,
            bd=0, font=(FONT_FAMILY, 10), anchor="w",
        )
        cb2.pack(anchor="w", padx=14, pady=(0, 12), fill="x")

        # ---------------- output folder ----------------
        out_section = ttk.Frame(self, style="TFrame")
        out_section.pack(fill="x", padx=pad, pady=(24, 4))
        ttk.Label(out_section, text="SAVE TO", style="Section.TLabel").pack(anchor="w")

        out_box = tk.Frame(self, bg=PANEL2, highlightbackground=BORDER, highlightthickness=1)
        out_box.pack(fill="x", padx=pad, pady=(6, 0))

        self.out_label = ttk.Label(
            out_box, text="(same folder as the source file)",
            style="Placeholder.TLabel", anchor="w",
        )
        self.out_label.pack(side="left", fill="x", expand=True)

        choose_out_btn = ttk.Button(
            out_box, text="Choose...", style="Secondary.TButton",
            command=self._on_choose_output_dir,
        )
        choose_out_btn.pack(side="right", padx=10, pady=8)

        # ---------------- generate button ----------------
        action_frame = ttk.Frame(self, style="TFrame")
        action_frame.pack(fill="x", padx=pad, pady=(28, 8))

        self.generate_btn = ttk.Button(
            action_frame, text="Generate Report", style="Accent.TButton",
            command=self._on_generate,
        )
        self.generate_btn.pack(fill="x", ipady=4)

        self.progress = ttk.Progressbar(
            self, mode="indeterminate", style="Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x", padx=pad, pady=(4, 0))

        # ---------------- status / log ----------------
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel", wraplength=560).pack(
            anchor="w", padx=pad, pady=(10, 0)
        )

        self.result_frame = ttk.Frame(self, style="TFrame")
        self.result_frame.pack(fill="x", padx=pad, pady=(10, 0))

    # ------------------------------------------------------------ actions
    def _on_browse(self):
        path = filedialog.askopenfilename(
            title="Select the source workbook",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not path:
            return
        self.source_path = path
        self.file_label.configure(text=os.path.basename(path), style="FileName.TLabel")
        self.status_var.set("Ready.")
        for w in self.result_frame.winfo_children():
            w.destroy()

    def _on_choose_output_dir(self):
        d = filedialog.askdirectory(title="Choose an output folder")
        if not d:
            return
        self.output_dir = d
        self.out_label.configure(text=d, style="FileName.TLabel")

    def _on_generate(self):
        if not self.source_path:
            messagebox.showwarning(
                "No file selected",
                "Please upload the source file before generating a report.",
            )
            return
        if not self.html_var.get() and not self.pdf_var.get():
            messagebox.showwarning(
                "No output selected",
                "Please select at least one output format (HTML and/or PDF).",
            )
            return

        self.generate_btn.configure(state="disabled")
        self.progress.start(12)
        self.status_var.set("Processing workbook...")
        for w in self.result_frame.winfo_children():
            w.destroy()

        thread = threading.Thread(target=self._run_generation, daemon=True)
        thread.start()

    def _run_generation(self):
        try:
            out_dir = Path(self.output_dir) if self.output_dir else Path(self.source_path).parent
            base_name = Path(self.source_path).stem

            data = extract_data(self.source_path)

            outputs = []
            if self.html_var.get():
                html_path = out_dir / f"{base_name}_money_trail.html"
                generate_html(data, html_path)
                outputs.append(("HTML report", str(html_path)))

            if self.pdf_var.get():
                pdf_path = out_dir / f"{base_name}_money_trail.pdf"
                generate_pdf(data, pdf_path)
                outputs.append(("PDF report", str(pdf_path)))

            self.after(0, self._on_generation_success, outputs)

        except ExtractionError as e:
            self.after(0, self._on_generation_error, str(e))
        except Exception:
            self.after(0, self._on_generation_error, traceback.format_exc())

    def _on_generation_success(self, outputs):
        self.progress.stop()
        self.generate_btn.configure(state="normal")
        self.status_var.set("Done. Generated:")

        for label, path in outputs:
            row = tk.Frame(self.result_frame, bg=BG)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=f"\u2713 {label}: {path}", style="Subtitle.TLabel").pack(
                side="left", fill="x", expand=True
            )
            ttk.Button(
                row, text="Open", style="Secondary.TButton",
                command=lambda p=path: self._open_path(p),
            ).pack(side="right")

    def _on_generation_error(self, message):
        self.progress.stop()
        self.generate_btn.configure(state="normal")
        self.status_var.set("Something went wrong.")
        messagebox.showerror("Generation failed", message)

    def _open_path(self, path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                webbrowser.open(f"file://{path}")
        except Exception as e:
            messagebox.showerror("Could not open file", str(e))


def main():
    app = MoneyTrailApp()
    app.mainloop()


if __name__ == "__main__":
    main()
