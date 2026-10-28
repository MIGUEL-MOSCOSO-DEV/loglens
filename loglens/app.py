import csv
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .paths import data_dir
from .reader import Filters, Tail, level_of, search
from .ui import Tasks, table, theme


class LogLens:
    def __init__(self, root):
        self.root = root
        root.title("LogLens — Lector de registros")
        root.geometry("1160x780")
        theme(root, "#24231f", "#eee9da", "#e9bd61")
        self.tasks = Tasks(root)
        self.path = None
        self.tail = None
        self.cancel = threading.Event()
        self.working = False
        self.filters = Filters(data_dir() / "filters.json")
        top = ttk.Frame(root, padding=20)
        top.pack(fill="x")
        ttk.Label(top, text="LOG / LENS", font=("Consolas", 24, "bold")).pack(side="left")
        ttk.Button(top, text="Abrir archivo…", command=self.open).pack(side="right")
        self.filename = tk.StringVar(value="Ningún archivo abierto")
        ttk.Label(root, textvariable=self.filename, padding=(20, 4), style="Sub.TLabel").pack(
            anchor="w"
        )
        tools = ttk.Frame(root, padding=20)
        tools.pack(fill="x")
        ttk.Label(tools, text="CONTIENE").pack(side="left", padx=(0, 8))
        self.query = tk.StringVar()
        entry = ttk.Entry(tools, textvariable=self.query, width=32)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda event: self.find())
        self.level = tk.StringVar(value="TODOS")
        ttk.Combobox(
            tools,
            textvariable=self.level,
            values=["TODOS", "TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"],
            state="readonly",
            width=10,
        ).pack(side="left", padx=8)
        self.case = tk.BooleanVar()
        ttk.Checkbutton(tools, text="Aa", variable=self.case).pack(side="left", padx=8)
        ttk.Button(tools, text="Buscar", command=self.find).pack(side="left", padx=4)
        ttk.Button(tools, text="Cancelar", command=self.cancel.set).pack(side="left", padx=4)
        body = ttk.Frame(root, padding=(20, 0))
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, width=190)
        left.pack(side="left", fill="y", padx=(0, 20))
        ttk.Label(left, text="FILTROS GUARDADOS", style="Sub.TLabel").pack(anchor="w", pady=10)
        self.saved = tk.Listbox(
            left,
            bg="#302e28",
            fg="#eee9da",
            selectbackground="#8c6d2c",
            borderwidth=0,
            width=22,
            height=15,
            font=("Segoe UI", 10),
        )
        self.saved.pack(fill="y", expand=True)
        self.saved.bind("<<ListboxSelect>>", self.apply_filter)
        ttk.Button(left, text="Guardar filtro", command=self.save_filter).pack(fill="x", pady=8)
        ttk.Button(left, text="Seguir en vivo", command=self.toggle_tail).pack(fill="x", pady=8)
        ttk.Button(left, text="Exportar resultados", command=self.export).pack(fill="x", pady=8)
        content = ttk.Frame(body)
        content.pack(side="left", fill="both", expand=True)
        self.tree = table(content, ("Línea", "Nivel", "Registro"), (70, 80, 660))
        self.tree.bind("<<TreeviewSelect>>", self.preview)
        self.detail = tk.Text(
            content,
            height=6,
            bg="#191a18",
            fg="#e7e0c9",
            font=("Consolas", 10),
            wrap="word",
            borderwidth=0,
            padx=12,
            pady=12,
            state="disabled",
        )
        self.detail.pack(fill="x", pady=(0, 12))
        self.status = tk.StringVar(
            value="Abre un registro UTF-8. Búsqueda por streaming, hasta 2000 resultados visibles."
        )
        ttk.Label(root, textvariable=self.status, padding=16).pack(
            side="bottom", fill="x", before=body
        )
        self.rows = {}
        self.refresh_filters()
        root.after(500, self.poll)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def open(self):
        path = filedialog.askopenfilename(
            title="Abrir registro",
            filetypes=[("Registros", "*.log *.txt *.jsonl"), ("Todos", "*.*")],
        )
        if path:
            if self.working:
                messagebox.showinfo(
                    "Búsqueda activa", "Cancela la búsqueda actual antes de cambiar de archivo."
                )
                return
            self.path = path
            self.tail = None
            self.filename.set(path)
            self.find()

    def find(self):
        if not self.path or self.working:
            return
        self.tail = None
        self.cancel.clear()
        self.working = True
        path, query, level, case = self.path, self.query.get(), self.level.get(), self.case.get()
        self.status.set("Leyendo archivo… Puedes cancelar sin cerrar el programa.")

        def work():
            try:
                return search(path, query, level, case, cancel=self.cancel)
            finally:
                self.working = False

        self.tasks.run(work, self.render)

    def render(self, result):
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for row in result["rows"]:
            key = self.tree.insert("", "end", values=(row[0], row[1], row[2][:250]))
            self.rows[key] = row
        self.status.set(
            f"{len(result['rows'])} coincidencias · {result['scanned']} líneas leídas · {result['skipped']} líneas >256 KB omitidas"
            + (" · Límite alcanzado" if result["limited"] else "")
            + (" · Cancelado" if result["cancelled"] else "")
        )

    def preview(self, event=None):
        selected = self.tree.selection()
        if selected and selected[0] in self.rows:
            self.detail.configure(state="normal")
            self.detail.delete("1.0", "end")
            self.detail.insert("1.0", self.rows[selected[0]][2])
            self.detail.configure(state="disabled")

    def refresh_filters(self):
        self.saved.delete(0, "end")
        try:
            for name in self.filters.all():
                self.saved.insert("end", name)
        except ValueError as error:
            messagebox.showerror("Filtros", str(error))

    def save_filter(self):
        name = simpledialog.askstring("Guardar filtro", "Nombre del filtro", parent=self.root)
        if name:
            try:
                self.filters.save(name, self.query.get(), self.level.get(), self.case.get())
                self.refresh_filters()
            except (ValueError, OSError) as error:
                messagebox.showerror("Filtros", str(error))

    def apply_filter(self, event):
        selection = self.saved.curselection()
        if selection:
            config = self.filters.all()[self.saved.get(selection[0])]
            self.query.set(config["query"])
            self.level.set(config["level"])
            self.case.set(config["case"])
            self.find()

    def toggle_tail(self):
        if self.working or not self.path:
            return
        self.tail = None if self.tail else Tail(self.path)
        self.status.set(
            "Seguimiento activo: mostrando solo nuevas líneas completas."
            if self.tail
            else "Seguimiento detenido."
        )

    def poll(self):
        if self.tail:
            try:
                reset, lines = self.tail.read()
                for text in lines:
                    severity = level_of(text)
                    query = self.query.get()
                    matches = (
                        query in text if self.case.get() else query.casefold() in text.casefold()
                    )
                    if matches and (self.level.get() == "TODOS" or self.level.get() == severity):
                        key = self.tree.insert("", "end", values=("LIVE", severity, text[:250]))
                        self.rows[key] = ("LIVE", severity, text)
                        children = self.tree.get_children()
                        if len(children) > 2000:
                            self.rows.pop(children[0], None)
                            self.tree.delete(children[0])
                if reset:
                    self.status.set("Rotación o truncado detectado. Continuando desde el inicio.")
            except OSError as error:
                self.status.set(str(error))
                self.tail = None
        self.root.after(500, self.poll)

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["line", "level", "record"])
                for row in self.rows.values():
                    writer.writerow(
                        [
                            "'" + str(cell)
                            if str(cell).startswith(("=", "+", "-", "@", "\t", "\r"))
                            else cell
                            for cell in row
                        ]
                    )
            self.status.set("Resultados exportados.")

    def close(self):
        self.cancel.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    LogLens(root)
    root.mainloop()
