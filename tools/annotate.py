"""Anotador visual local de referências draft (Tkinter opcional)."""

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image

from fluteomr.annotation_editor import (
    AnnotationEditor,
    canvas_to_image,
    drag_box,
    hit_box,
    image_to_canvas,
    move_box,
    next_pending_clef,
    resize_box,
)
from fluteomr.annotations import AnnotationError
from fluteomr.image_io import load_image

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    from PIL import ImageTk
except ModuleNotFoundError:
    tk = None


class Annotator:
    """Canvas rolável e controles; regras e integridade ficam no modelo."""

    def __init__(self, root):
        self.root = root
        self.root.title("FluteOMR — revisão de referências")
        self.root.geometry("1280x800")
        self.editor: AnnotationEditor | None = None
        self.image: Image.Image | None = None
        self.suggestions: dict | None = None
        self.suggestion_staff_ids: list[str] = []
        self.photo = None
        self.zoom = 1.0
        self.selected: tuple[str, str] | None = None
        self.drag_start: tuple[int, int] | None = None
        self.drag_original: dict | None = None
        self.drag_resize = False
        self.preview = None
        self.pending_box: dict | None = None
        self.review_mode = True
        self.tool = tk.StringVar(value="Selecionar")
        self.clef_kind = tk.StringVar(value="")
        self.show_staffs = tk.BooleanVar(value=True)
        self.show_systems = tk.BooleanVar(value=False)
        self.show_clefs = tk.BooleanVar(value=True)
        self.show_suggestions = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Abra um reference-draft.json.")
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.bind("<Control-s>", lambda _event: self._save())
        self.root.bind("<Control-o>", lambda _event: self._open_dialog())
        self.root.bind("<Escape>", self._cancel_edit)

    def _build(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x")
        for title, command in (
            ("Abrir", self._open_dialog),
            ("Salvar rascunho", self._save),
            ("Salvar como", self._save_as),
            ("Reverter", self._revert),
            ("Checar", self._check),
            ("−", lambda: self._change_zoom(1 / 1.25)),
            ("+", lambda: self._change_zoom(1.25)),
            ("Página", self._fit),
            ("Largura", self._fit_width),
            ("Seleção", self._focus_selected),
        ):
            ttk.Button(bar, text=title, command=command).pack(side="left", padx=2)
        ttk.Combobox(
            bar,
            textvariable=self.tool,
            state="readonly",
            width=16,
            values=(
                "Navegar",
                "Selecionar",
                "Mover/redimensionar",
                "Nova pauta",
                "Caixa de clave",
            ),
        ).pack(side="left", padx=8)
        ttk.Button(bar, text="Revisar claves", command=self._enter_review).pack(
            side="left", padx=3
        )

        pane = ttk.PanedWindow(self.root, orient="horizontal")
        pane.pack(fill="both", expand=True)
        viewer = ttk.Frame(pane)
        pane.add(viewer, weight=4)
        self.canvas = tk.Canvas(viewer, bg="#bbbbbb", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        viewer.rowconfigure(0, weight=1)
        viewer.columnconfigure(0, weight=1)
        ttk.Scrollbar(viewer, orient="vertical", command=self._yview).grid(
            row=0, column=1, sticky="ns"
        )
        self.yscroll = viewer.grid_slaves(row=0, column=1)[0]
        ttk.Scrollbar(viewer, orient="horizontal", command=self._xview).grid(
            row=1, column=0, sticky="ew"
        )
        self.xscroll = viewer.grid_slaves(row=1, column=0)[0]
        self.canvas.configure(
            xscrollcommand=self.xscroll.set, yscrollcommand=self.yscroll.set
        )
        self.canvas.bind("<Configure>", lambda _event: self._render())
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind(
            "<Button-4>", lambda event: self._zoom_at(1.2, event.x, event.y)
        )
        self.canvas.bind(
            "<Button-5>", lambda event: self._zoom_at(1 / 1.2, event.x, event.y)
        )
        self.canvas.bind("<Shift-MouseWheel>", self._horizontal_wheel)

        side_shell = ttk.Frame(pane)
        pane.add(side_shell, weight=1)
        side_canvas = tk.Canvas(side_shell, highlightthickness=0, width=320)
        side_canvas.pack(side="left", fill="both", expand=True)
        side_scroll = ttk.Scrollbar(
            side_shell, orient="vertical", command=side_canvas.yview
        )
        side_scroll.pack(side="right", fill="y")
        side_canvas.configure(yscrollcommand=side_scroll.set)
        side = ttk.Frame(side_canvas, padding=6)
        side_window = side_canvas.create_window((0, 0), window=side, anchor="nw")
        side.bind(
            "<Configure>",
            lambda _event: side_canvas.configure(scrollregion=side_canvas.bbox("all")),
        )
        side_canvas.bind(
            "<Configure>",
            lambda event: side_canvas.itemconfigure(side_window, width=event.width),
        )
        self.progress = tk.StringVar(value="Abra um rascunho para revisar claves")
        ttk.Label(side, text="Revisar claves", font=("TkDefaultFont", 13, "bold")).pack(
            anchor="w"
        )
        ttk.Label(side, textvariable=self.progress, wraplength=300).pack(anchor="w")
        self.review_list = tk.Listbox(side, height=9, exportselection=False)
        self.review_list.pack(fill="x", pady=4)
        self.review_list.bind("<<ListboxSelect>>", self._review_selection)
        nav = ttk.Frame(side)
        nav.pack(fill="x")
        ttk.Button(nav, text="Anterior", command=self._previous_clef).pack(
            side="left", fill="x", expand=True
        )
        self.next_button = ttk.Button(
            nav, text="Próxima pendente", command=self._next_pending
        )
        self.next_button.pack(side="left", fill="x", expand=True)
        self.suggestion_button = ttk.Button(
            side, text="Confirmar sugestão", command=self._confirm_suggestion
        )
        self.suggestion_button.pack(fill="x", pady=(8, 2))
        self.correct_button = ttk.Button(
            side,
            text="Corrigir região / desenhar caixa",
            command=self._start_correction,
        )
        self.correct_button.pack(fill="x", pady=2)
        kind_row = ttk.Frame(side)
        kind_row.pack(fill="x")
        ttk.Label(kind_row, text="Tipo visto:").pack(side="left")
        kind_choice = ttk.Combobox(
            kind_row,
            textvariable=self.clef_kind,
            values=("Sol", "Fá", "Dó", "Outra"),
            state="readonly",
            width=12,
        )
        kind_choice.pack(side="left", fill="x", expand=True)
        kind_choice.bind("<<ComboboxSelected>>", lambda _event: self._update_review())
        self.apply_correction_button = ttk.Button(
            side, text="Confirmar correção desenhada", command=self._confirm_correction
        )
        self.apply_correction_button.pack(fill="x", pady=2)
        ttk.Button(
            side, text="Não é clave de sol / outra clave", command=self._not_treble
        ).pack(fill="x", pady=2)
        ttk.Button(
            side, text="Não consigo identificar", command=self._mark_unknown
        ).pack(fill="x", pady=2)
        ttk.Label(
            side,
            text="Tracejado = sugestão; sólido = referência; amarelo = seleção. "
            "Abrir ou navegar não confirma a revisão.",
            wraplength=300,
        ).pack(anchor="w", pady=5)
        layers = ttk.Frame(side)
        layers.pack(fill="x")
        for title, variable in (
            ("Pautas", self.show_staffs),
            ("Sistemas", self.show_systems),
            ("Claves", self.show_clefs),
            ("Sugestões", self.show_suggestions),
        ):
            ttk.Checkbutton(
                layers, text=title, variable=variable, command=self._render
            ).pack(side="left")
        self.advanced_button = ttk.Button(
            side, text="Mostrar opções avançadas", command=self._toggle_advanced
        )
        self.advanced_button.pack(fill="x", pady=4)
        self.advanced_container = ttk.Frame(side)
        advanced_canvas = tk.Canvas(
            self.advanced_container, highlightthickness=0, height=190
        )
        advanced_canvas.pack(side="left", fill="both", expand=True)
        advanced_scroll = ttk.Scrollbar(
            self.advanced_container,
            orient="vertical",
            command=advanced_canvas.yview,
        )
        advanced_scroll.pack(side="right", fill="y")
        advanced_canvas.configure(yscrollcommand=advanced_scroll.set)
        self.advanced = ttk.Frame(advanced_canvas)
        advanced_window = advanced_canvas.create_window(
            (0, 0), window=self.advanced, anchor="nw"
        )
        self.advanced.bind(
            "<Configure>",
            lambda _event: advanced_canvas.configure(
                scrollregion=advanced_canvas.bbox("all")
            ),
        )
        advanced_canvas.bind(
            "<Configure>",
            lambda event: advanced_canvas.itemconfigure(
                advanced_window, width=event.width
            ),
        )
        self.tree = ttk.Treeview(
            self.advanced, columns=("state",), show="tree headings", height=6
        )
        self.tree.heading("#0", text="Anotação")
        self.tree.heading("state", text="Estado")
        self.tree.column("#0", width=125)
        self.tree.column("state", width=170)
        self.tree.pack(fill="x")
        self.tree.tag_configure("pending", foreground="#ad5b00")
        self.tree.tag_configure("reviewed", foreground="#176b2d")
        self.tree.bind("<<TreeviewSelect>>", self._tree_selection)

        globals_box = ttk.LabelFrame(self.advanced, text="Página / cobertura")
        globals_box.pack(fill="x", pady=6)
        self.global_vars = {}
        for label, key, values in (
            ("Conjunto", "split", ("unspecified", "development", "test")),
            ("Pautas", "staffs", ("unknown", "partial", "complete")),
            ("Sistemas", "systems", ("unknown", "partial", "complete")),
            ("Claves", "clefs", ("unknown", "partial", "complete")),
        ):
            row = ttk.Frame(globals_box)
            row.pack(fill="x")
            ttk.Label(row, text=label, width=10).pack(side="left")
            variable = tk.StringVar(value=values[0])
            self.global_vars[key] = variable
            ttk.Combobox(
                row, textvariable=variable, values=values, state="readonly"
            ).pack(side="left", fill="x", expand=True)
        ttk.Button(globals_box, text="Aplicar página", command=self._apply_page).pack(
            fill="x"
        )

        self.properties = ttk.LabelFrame(self.advanced, text="Propriedades numéricas")
        self.properties.pack(fill="x")
        actions = ttk.Frame(self.advanced)
        actions.pack(fill="x")
        for title, command in (
            ("Novo sistema", self._add_system),
            ("Nova clave", self._add_clef),
            ("Excluir selecionado", self._delete),
        ):
            ttk.Button(actions, text=title, command=command).pack(fill="x")
        ttk.Button(self.advanced, text="Checar estrutura", command=self._check).pack(
            fill="x"
        )
        ttk.Button(
            self.advanced,
            text="Como confirmar a página",
            command=self._confirmation_help,
        ).pack(fill="x")
        ttk.Label(self.root, textvariable=self.status, anchor="w", wraplength=760).pack(
            fill="x"
        )

    def open(self, path: Path, image_dir: Path):
        editor = AnnotationEditor(path, image_dir)
        image = load_image(image_dir / editor.data["image"]["filename"])
        suggestions = None
        suffix = ".reference-draft.json"
        if path.name.endswith(suffix):
            sidecar = path.with_name(path.name[: -len(suffix)] + ".suggestions.json")
            if sidecar.is_file():
                proposal = json.loads(sidecar.read_text(encoding="utf-8"))
                if (
                    proposal.get("kind") != "suggestions_not_ground_truth"
                    or proposal.get("image") != editor.data["image"]
                ):
                    raise AnnotationError("sugestões não correspondem à imagem")
                suggestions = proposal["detections"]
        self.editor, self.image = editor, image
        self.suggestions = suggestions
        self.suggestion_staff_ids = [staff["id"] for staff in editor.data["staffs"]]
        self.selected = None
        self.pending_box = None
        self._populate_tree()
        self._populate_review()
        self._load_page_properties()
        if editor.data["staffs"]:
            self._select("clefs", editor.data["staffs"][0]["id"])
            self.root.after(100, self._focus_selected)
        else:
            self._fit()
        self._update_status()

    def _open_dialog(self):
        if not self._may_leave():
            return
        filename = filedialog.askopenfilename(
            title="Abrir referência JSON", filetypes=[("JSON", "*.json")]
        )
        if not filename:
            return
        directory = filedialog.askdirectory(title="Pasta do PNG/JPEG original")
        if not directory:
            return
        self._try(lambda: self.open(Path(filename), Path(directory)))

    def _may_leave(self) -> bool:
        if self.pending_box and not messagebox.askokcancel(
            "Caixa não confirmada",
            "Há uma caixa desenhada ainda não confirmada. Descartá-la?",
        ):
            return False
        if self.editor is None or not self.editor.dirty:
            return True
        response = messagebox.askyesnocancel(
            "Alterações não salvas", "Salvar o rascunho antes de continuar?"
        )
        if response is None:
            return False
        if response:
            return self._save()
        return True

    def _close(self):
        if self._may_leave():
            self.root.destroy()

    def _try(self, operation):
        try:
            result = operation()
        except (
            AnnotationError,
            OSError,
            ValueError,
            PermissionError,
            StopIteration,
            KeyError,
            TypeError,
        ) as exc:
            messagebox.showerror("FluteOMR", str(exc))
            return False
        self._update_status()
        return True if result is None else result

    def _save(self) -> bool:
        if self.editor is None:
            return False
        if self.pending_box:
            messagebox.showinfo(
                "Caixa não confirmada",
                "Confirme ou cancele a caixa desenhada antes de salvar.",
            )
            return False
        return self._try(lambda: self.editor.save()) is not False

    def _save_as(self):
        if self.editor is None:
            return
        if self.pending_box:
            messagebox.showinfo(
                "Caixa não confirmada",
                "Confirme ou cancele a caixa desenhada antes de salvar.",
            )
            return
        filename = filedialog.asksaveasfilename(
            title="Salvar rascunho como", defaultextension=".json"
        )
        if filename:
            self._try(lambda: self.editor.save(Path(filename)))

    def _revert(self):
        if (
            self.editor
            and self.editor.dirty
            and messagebox.askyesno(
                "Reverter", "Descartar alterações ainda não salvas?"
            )
        ):
            self.editor.revert()
            self._load_page_properties()
            self._refresh()

    def _check(self):
        if self.editor and self._try(self.editor.check) is not False:
            messagebox.showinfo(
                "Checagem",
                "Estrutura e imagem íntegras. Revisão musical não verificada.",
            )

    def _confirmation_help(self):
        messagebox.showinfo(
            "Confirmação humana",
            "Salve e revise musicalmente o rascunho. Depois use "
            "python -m tools.evaluate_annotations confirm --annotation ARQUIVO "
            "--images-dir PASTA --output NOVA_REFERENCIA.reference.json "
            "--reviewer SEU_NOME --confirm-reviewed. A interface não confirma.",
        )

    def _update_status(self):
        if self.editor:
            state = self.editor.data["review"]["status"]
            dirty = " • alterações não salvas" if self.editor.dirty else ""
            mode = " • somente leitura" if not self.editor.editable else ""
            self.status.set(f"{self.editor.path.name} • {state}{mode}{dirty}")

    def _load_page_properties(self):
        if self.editor is None:
            return
        self.global_vars["split"].set(self.editor.data["split"])
        for key, value in self.editor.data["coverage"].items():
            self.global_vars[key].set(value)

    def _apply_page(self):
        if self.editor:
            self._try(
                lambda: self.editor.update_page(
                    split=self.global_vars["split"].get(),
                    coverage={
                        key: self.global_vars[key].get()
                        for key in ("staffs", "systems", "clefs")
                    },
                )
            )

    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        if self.editor is None:
            return
        for kind, title in (
            ("staffs", "Pautas"),
            ("systems", "Sistemas"),
            ("clefs", "Claves"),
        ):
            self.tree.insert("", "end", iid=f"group:{kind}", text=title, open=True)
            for item in self.editor.data[kind]:
                item_id = item["staff_id"] if kind == "clefs" else item["id"]
                review_state = item.get("review_state", item.get("state", ""))
                state = review_state
                if kind == "clefs" and self.suggestions is not None:
                    staff_index = (
                        self.suggestion_staff_ids.index(item_id)
                        if item_id in self.suggestion_staff_ids
                        else None
                    )
                    predicted_clefs = self.suggestions.get("clefs", [])
                    if staff_index is not None and staff_index < len(predicted_clefs):
                        state += f" / sug {predicted_clefs[staff_index]['status']}"
                tag = (
                    "reviewed"
                    if review_state in ("confirmed", "present", "absent")
                    else "pending"
                )
                self.tree.insert(
                    f"group:{kind}",
                    "end",
                    iid=f"{kind}:{item_id}",
                    text=item_id,
                    values=(state,),
                    tags=(tag,),
                )

    def _populate_review(self):
        self.review_list.delete(0, "end")
        if not self.editor:
            return
        for index, staff in enumerate(self.editor.data["staffs"]):
            clef = next(
                (
                    item
                    for item in self.editor.data["clefs"]
                    if item["staff_id"] == staff["id"]
                ),
                None,
            )
            state = (
                "Pendente" if clef is None or clef["state"] == "unknown" else "Revisada"
            )
            self.review_list.insert("end", f"{index + 1}. {staff['id']} — {state}")

    def _review_selection(self, _event=None):
        if not self.editor or not self.review_list.curselection():
            return
        index = self.review_list.curselection()[0]
        self._select("clefs", self.editor.data["staffs"][index]["id"])

    def _enter_review(self):
        self.review_mode = True
        self.tool.set("Selecionar")
        if self.editor and self.editor.data["staffs"]:
            item_id = (
                self.selected[1]
                if self.selected and self.selected[0] == "clefs"
                else self.editor.data["staffs"][0]["id"]
            )
            self._select("clefs", item_id)

    def _toggle_advanced(self):
        if self.advanced_container.winfo_manager():
            self.advanced_container.pack_forget()
            self.advanced_button.configure(text="Mostrar opções avançadas")
        else:
            self.advanced_container.pack(fill="both", expand=True)
            self.advanced_button.configure(text="Ocultar opções avançadas")

    def _current_clef_id(self):
        return (
            self.selected[1] if self.selected and self.selected[0] == "clefs" else None
        )

    def _current_prediction(self):
        item_id = self._current_clef_id()
        if item_id is None or self.suggestions is None:
            return None
        if item_id not in self.suggestion_staff_ids:
            return None
        index = self.suggestion_staff_ids.index(item_id)
        predictions = self.suggestions.get("clefs", [])
        return predictions[index] if index < len(predictions) else None

    def _update_review(self):
        if not self.editor:
            return
        item_id = self._current_clef_id()
        ids = [staff["id"] for staff in self.editor.data["staffs"]]
        if item_id in ids:
            index = ids.index(item_id)
            clef = next(
                (c for c in self.editor.data["clefs"] if c["staff_id"] == item_id), None
            )
            if clef is None or clef["state"] == "unknown":
                state, kind = "Pendente", "Desconhecida"
            elif clef["state"] == "absent":
                state, kind = "Revisada", "Nenhuma clave nesta pauta"
            else:
                state = "Revisada"
                kind = {
                    "treble": "Sol",
                    "bass": "Fá",
                    "alto": "Dó",
                    "other": "Outra",
                }.get(clef["kind"], "Desconhecida")
            prediction = self._current_prediction()
            if (
                state == "Pendente"
                and prediction
                and prediction.get("status") == "inconclusive"
            ):
                state = "Pendente (detector inconclusivo)"
            self.progress.set(
                f"Clave {index + 1} de {len(ids)} · {item_id}\n{state} · {kind}"
            )
            self.review_list.selection_clear(0, "end")
            self.review_list.selection_set(index)
            self.review_list.see(index)
            self.suggestion_button.configure(
                state="normal"
                if self.editor.editable
                and prediction
                and prediction.get("status") == "detected"
                and prediction.get("region")
                else "disabled"
            )
            self.correct_button.configure(
                state="normal" if self.editor.editable else "disabled"
            )
            self.apply_correction_button.configure(
                state="normal"
                if self.editor.editable
                and self.pending_box
                and self.clef_kind.get() in ("Sol", "Fá", "Dó", "Outra")
                else "disabled"
            )
            self.next_button.configure(
                state="normal"
                if next_pending_clef(self.editor.data, item_id)
                else "disabled"
            )
        else:
            self.progress.set("Selecione uma clave da lista")
            self.suggestion_button.configure(state="disabled")
            self.correct_button.configure(state="disabled")
            self.apply_correction_button.configure(state="disabled")
            self.next_button.configure(state="disabled")

    def _previous_clef(self):
        if not self.editor or not self.editor.data["staffs"]:
            return
        ids = [staff["id"] for staff in self.editor.data["staffs"]]
        current = self._current_clef_id()
        index = ids.index(current) if current in ids else 0
        self._select("clefs", ids[(index - 1) % len(ids)])

    def _next_pending(self):
        if self.editor:
            item_id = next_pending_clef(self.editor.data, self._current_clef_id())
            if item_id:
                self._select("clefs", item_id)

    def _confirm_suggestion(self):
        item_id = self._current_clef_id()
        if not item_id or not self.editor:
            return
        if (
            self._try(
                lambda: self.editor.confirm_treble_suggestion(
                    item_id, self._current_prediction()
                )
            )
            is not False
        ):
            self.clef_kind.set("Sol")
            self.pending_box = None
            self._refresh()

    def _start_correction(self):
        if self._current_clef_id() and self.editor and self.editor.editable:
            self.tool.set("Caixa de clave")
            self.status.set(
                "Desenhe ou arraste a caixa; escolha o tipo e confirme. Esc cancela."
            )

    def _confirm_correction(self):
        item_id = self._current_clef_id()
        if not item_id or not self.pending_box or not self.editor:
            return
        if self.clef_kind.get() not in ("Sol", "Fá", "Dó", "Outra"):
            messagebox.showinfo(
                "Tipo de clave", "Escolha o tipo visto antes de confirmar."
            )
            return
        kind = {"Sol": "treble", "Fá": "bass", "Dó": "alto", "Outra": "other"}[
            self.clef_kind.get()
        ]
        if (
            self._try(lambda: self.editor.review_clef(item_id, kind, self.pending_box))
            is not False
        ):
            self.pending_box = None
            self.tool.set("Selecionar")
            self._refresh()

    def _not_treble(self):
        item_id = self._current_clef_id()
        if not item_id or not self.editor:
            return
        answer = messagebox.askyesnocancel(
            "Não é clave de sol",
            "Existe outra clave nesta pauta?\n"
            "Sim: desenhe sua região e escolha Fá, Dó ou Outra.\n"
            "Não: marque ausência confirmada de qualquer clave.\n"
            "Cancelar: não alterar.",
        )
        if answer is None:
            return
        if answer:
            self.clef_kind.set("Outra")
            self._start_correction()
        elif (
            self._try(
                lambda: self.editor.update_clef(
                    item_id, state="absent", kind=None, region=None
                )
            )
            is not False
        ):
            self._refresh()

    def _mark_unknown(self):
        item_id = self._current_clef_id()
        if (
            item_id
            and self.editor
            and self._try(
                lambda: self.editor.update_clef(
                    item_id, state="unknown", kind=None, region=None
                )
            )
            is not False
        ):
            self.pending_box = None
            self._refresh()
            self._next_pending()

    def _cancel_edit(self, _event=None):
        self.drag_start = self.drag_original = self.preview = self.pending_box = None
        self.tool.set("Selecionar")
        self._update_review()
        self._render()

    def _tree_selection(self, _event=None):
        selection = self.tree.selection()
        if not selection or selection[0].startswith("group:"):
            return
        self.selected = tuple(selection[0].split(":", 1))
        self._update_review()
        self._properties()
        self._render()

    def _select(self, kind: str, item_id: str, *, focus: bool = True):
        if self.selected != (kind, item_id):
            self.pending_box = None
            if kind == "clefs" and self.editor:
                clef = next(
                    (
                        item
                        for item in self.editor.data["clefs"]
                        if item["staff_id"] == item_id
                    ),
                    None,
                )
                names = {"treble": "Sol", "bass": "Fá", "alto": "Dó", "other": "Outra"}
                self.clef_kind.set(names.get(clef["kind"], "") if clef else "")
        self.selected = kind, item_id
        iid = f"{kind}:{item_id}"
        self.tree.selection_set(iid)
        self.tree.see(iid)
        self._properties()
        self._update_review()
        if focus and kind == "clefs" and self.review_mode:
            self._focus_selected()
            return
        self._render()

    def _field(self, parent, label: str, value: str, *, choices=None):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, width=14).pack(side="left")
        variable = tk.StringVar(value=value)
        if choices:
            widget = ttk.Combobox(
                row, textvariable=variable, values=choices, state="readonly"
            )
        else:
            widget = ttk.Entry(row, textvariable=variable)
        widget.pack(side="left", fill="x", expand=True)
        return variable

    def _properties(self):
        for child in self.properties.winfo_children():
            child.destroy()
        if self.editor is None or self.selected is None:
            return
        kind, item_id = self.selected
        item = self.editor.item(kind, item_id)
        ttk.Label(self.properties, text=f"{kind} / {item_id}").pack(anchor="w")
        values = {}
        box = self.editor.box(kind, item_id)
        if kind != "systems":
            for edge in ("left", "top", "right", "bottom"):
                values[edge] = self._field(
                    self.properties, edge, "" if box is None else str(box[edge])
                )
        else:
            ttk.Label(
                self.properties, text="Região derivada das pautas; edite membros."
            ).pack(anchor="w")
        if kind == "staffs":
            values["state"] = self._field(
                self.properties,
                "Revisão",
                item["review_state"],
                choices=("unknown", "partial", "confirmed"),
            )
            ttk.Label(
                self.properties, text="Linhas: x_inicio,x_fim,y (uma por linha)"
            ).pack()
            lines = tk.Text(self.properties, height=5, width=34)
            lines.pack(fill="x")
            if item["lines"] is not None:
                lines.insert(
                    "1.0",
                    "\n".join(
                        f"{line['x_start']},{line['x_end']},{line['y']}"
                        for line in item["lines"]
                    ),
                )
            values["lines"] = lines
        elif kind == "systems":
            values["members"] = self._field(
                self.properties, "Pautas", ",".join(item["staff_ids"])
            )
            values["state"] = self._field(
                self.properties,
                "Revisão",
                item["review_state"],
                choices=("uncertain", "confirmed"),
            )
            values["partial"] = self._field(
                self.properties,
                "Parcial",
                str(item["partial_visible"]).lower(),
                choices=("false", "true"),
            )
        else:
            values["state"] = self._field(
                self.properties,
                "Presença",
                item["state"],
                choices=("unknown", "absent", "present"),
            )
            values["kind"] = self._field(
                self.properties,
                "Tipo",
                item["kind"] or "treble",
                choices=("treble", "bass", "alto", "other"),
            )
            ttk.Label(
                self.properties,
                text="absent = nenhuma clave; outra clave presente: escolha o tipo.",
                wraplength=270,
            ).pack(anchor="w")
        ttk.Button(
            self.properties,
            text="Aplicar propriedades",
            command=lambda: self._apply_item(kind, item_id, values),
        ).pack(fill="x", pady=8)

    @staticmethod
    def _parse_box(values):
        entries = [
            values[key].get().strip() for key in ("left", "top", "right", "bottom")
        ]
        if not any(entries):
            return None
        if not all(entries):
            raise ValueError("preencha as quatro coordenadas ou deixe todas vazias")
        numbers = [float(value) for value in entries]
        if not all(math.isfinite(number) for number in numbers):
            raise ValueError("coordenadas devem ser finitas")
        left, top, right, bottom = numbers
        if right <= left or bottom <= top:
            raise ValueError("largura e altura devem ser positivas")
        return dict(zip(("left", "top", "right", "bottom"), numbers, strict=True))

    def _apply_item(self, kind: str, item_id: str, values):
        if self.editor is None:
            return

        def update():
            if kind == "staffs":
                raw = values["lines"].get("1.0", "end").strip()
                lines = None
                if raw:
                    lines = []
                    for text in raw.splitlines():
                        coords = [float(part.strip()) for part in text.split(",")]
                        if len(coords) != 3:
                            raise ValueError("cada linha exige x_inicio,x_fim,y")
                        lines.append(
                            dict(zip(("x_start", "x_end", "y"), coords, strict=True))
                        )
                self.editor.update_staff(
                    item_id,
                    region=self._parse_box(values),
                    lines=lines,
                    review_state=values["state"].get(),
                )
            elif kind == "systems":
                self.editor.update_system(
                    item_id,
                    staff_ids=[
                        part.strip()
                        for part in values["members"].get().split(",")
                        if part.strip()
                    ],
                    review_state=values["state"].get(),
                    partial_visible=values["partial"].get() == "true",
                )
            else:
                state = values["state"].get()
                self.editor.update_clef(
                    item_id,
                    state=state,
                    kind=values["kind"].get() if state == "present" else None,
                    region=self._parse_box(values) if state == "present" else None,
                )

        if self._try(update) is not False:
            self._refresh()

    def _refresh(self):
        selected = self.selected
        self._populate_tree()
        self._populate_review()
        if selected and self.tree.exists(f"{selected[0]}:{selected[1]}"):
            self._select(*selected)
        else:
            self.selected = None
            self._update_review()
            self._render()
        self._load_page_properties()
        self._update_status()

    def _add_system(self):
        if self.editor is None:
            return
        members = simpledialog.askstring(
            "Novo sistema", "IDs de pautas separados por vírgula:"
        )
        if members:
            result = self._try(
                lambda: self.editor.add_system(
                    [part.strip() for part in members.split(",") if part.strip()]
                )
            )
            if result:
                self._refresh()
                self._select("systems", result)

    def _add_clef(self):
        if self.editor is None:
            return
        staff_id = simpledialog.askstring("Nova clave", "ID da pauta:")
        if staff_id and self._try(lambda: self.editor.add_clef(staff_id)) is not False:
            self._refresh()

    def _delete(self):
        if (
            self.editor
            and self.selected
            and messagebox.askyesno(
                "Excluir", f"Excluir {self.selected[0]} {self.selected[1]}?"
            )
        ):
            if self._try(lambda: self.editor.delete(*self.selected)) is not False:
                self.selected = None
                self._refresh()

    def _change_zoom(self, factor: float):
        if self.image is None:
            return
        self._zoom_at(
            factor, self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2
        )

    def _zoom_at(self, factor: float, x: float, y: float):
        if self.image is None:
            return
        cx = self.canvas.canvasx(x) / self.zoom
        cy = self.canvas.canvasy(y) / self.zoom
        self.zoom = max(0.05, min(5.0, self.zoom * factor))
        self.canvas.configure(
            scrollregion=(
                0,
                0,
                self.image.width * self.zoom,
                self.image.height * self.zoom,
            )
        )
        self.canvas.xview_moveto(
            max(
                0,
                (cx * self.zoom - x) / (self.image.width * self.zoom),
            )
        )
        self.canvas.yview_moveto(
            max(
                0,
                (cy * self.zoom - y) / (self.image.height * self.zoom),
            )
        )
        self._render()

    def _fit_width(self):
        if self.image is None:
            return
        self.root.update_idletasks()
        self.zoom = self.canvas.winfo_width() / self.image.width
        self.canvas.configure(
            scrollregion=(
                0,
                0,
                self.image.width * self.zoom,
                self.image.height * self.zoom,
            )
        )
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self._render()

    def _focus_selected(self):
        if self.image is None or self.editor is None or not self.selected:
            return
        kind, item_id = self.selected
        box = self.editor.box(kind, item_id)
        if kind == "clefs":
            staff = self.editor.box("staffs", item_id)
            if staff is None:
                return self._fit_width()
            spacing = max(8, (staff["bottom"] - staff["top"]) / 4)
            target = box or (self._current_prediction() or {}).get("region")
            cx = (
                (target["left"] + target["right"]) / 2
                if target
                else staff["left"] + 4 * spacing
            )
            cy = (
                (target["top"] + target["bottom"]) / 2
                if target
                else (staff["top"] + staff["bottom"]) / 2
            )
            width, height = (
                max(
                    14 * spacing,
                    (target["right"] - target["left"]) * 3 if target else 0,
                ),
                max(
                    11 * spacing,
                    (target["bottom"] - target["top"]) * 1.8 if target else 0,
                ),
            )
        elif box:
            cx, cy = (box["left"] + box["right"]) / 2, (box["top"] + box["bottom"]) / 2
            width, height = (
                (box["right"] - box["left"]) * 1.25,
                (box["bottom"] - box["top"]) * 2,
            )
        else:
            return
        self.root.update_idletasks()
        self.zoom = max(
            0.05,
            min(
                5,
                self.canvas.winfo_width() / width,
                self.canvas.winfo_height() / height,
            ),
        )
        self.canvas.configure(
            scrollregion=(
                0,
                0,
                self.image.width * self.zoom,
                self.image.height * self.zoom,
            )
        )
        self.canvas.xview_moveto(
            max(
                0,
                (cx * self.zoom - self.canvas.winfo_width() / 2)
                / (self.image.width * self.zoom),
            )
        )
        self.canvas.yview_moveto(
            max(
                0,
                (cy * self.zoom - self.canvas.winfo_height() / 2)
                / (self.image.height * self.zoom),
            )
        )
        self._render()

    def _fit(self):
        if self.image is None:
            return
        self.root.update_idletasks()
        self.zoom = min(
            self.canvas.winfo_width() / self.image.width,
            self.canvas.winfo_height() / self.image.height,
        )
        self.canvas.configure(
            scrollregion=(
                0,
                0,
                self.image.width * self.zoom,
                self.image.height * self.zoom,
            )
        )
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self._render()

    def _xview(self, *args):
        self.canvas.xview(*args)
        self._render()

    def _yview(self, *args):
        self.canvas.yview(*args)
        self._render()

    def _scroll(self, units: int):
        self.canvas.yview_scroll(units, "units")
        self._render()

    def _wheel(self, event):
        self._zoom_at(1.2 if event.delta > 0 else 1 / 1.2, event.x, event.y)

    def _horizontal_wheel(self, event):
        self.canvas.xview_scroll(-3 if event.delta > 0 else 3, "units")
        self._render()

    def _render(self):
        if self.image is None:
            return
        self.canvas.delete("all")
        x0 = max(0, math.floor(self.canvas.canvasx(0) / self.zoom))
        y0 = max(0, math.floor(self.canvas.canvasy(0) / self.zoom))
        x1 = min(
            self.image.width,
            math.ceil(self.canvas.canvasx(self.canvas.winfo_width()) / self.zoom),
        )
        y1 = min(
            self.image.height,
            math.ceil(self.canvas.canvasy(self.canvas.winfo_height()) / self.zoom),
        )
        if x1 <= x0 or y1 <= y0:
            return
        crop = self.image.crop((x0, y0, x1, y1))
        view = crop.resize(
            (
                max(1, round(crop.width * self.zoom)),
                max(1, round(crop.height * self.zoom)),
            ),
            Image.Resampling.LANCZOS,
        )
        self.photo = ImageTk.PhotoImage(view)
        self.canvas.create_image(
            x0 * self.zoom, y0 * self.zoom, image=self.photo, anchor="nw"
        )
        if self.suggestions is not None and self.show_suggestions.get():
            for index, prediction in enumerate(self.suggestions.get("clefs", [])):
                if self.review_mode and (
                    not self.selected
                    or self.selected
                    != (
                        "clefs",
                        self.suggestion_staff_ids[index]
                        if index < len(self.suggestion_staff_ids)
                        else None,
                    )
                ):
                    continue
                box = prediction.get("region")
                if box is None:
                    continue
                sx0, sy0 = image_to_canvas(box["left"], box["top"], self.zoom)
                sx1, sy1 = image_to_canvas(
                    box["right"] + 1, box["bottom"] + 1, self.zoom
                )
                self.canvas.create_rectangle(
                    sx0, sy0, sx1, sy1, outline="#00a050", width=2, dash=(4, 3)
                )
        for kind, color in (
            ("systems", "#8030a0"),
            ("staffs", "#177dc0"),
            ("clefs", "#168a29"),
        ):
            if not {
                "systems": self.show_systems,
                "staffs": self.show_staffs,
                "clefs": self.show_clefs,
            }[kind].get():
                continue
            for item in self.editor.data[kind]:
                item_id = item["staff_id"] if kind == "clefs" else item["id"]
                if self.review_mode and self.selected and self.selected[0] == "clefs":
                    if (
                        kind == "systems"
                        or (kind == "staffs" and item_id != self.selected[1])
                        or (kind == "clefs" and item_id != self.selected[1])
                    ):
                        continue
                box = self.editor.box(kind, item_id)
                if box is None:
                    continue
                selected = self.selected == (kind, item_id)
                x_left, y_top = image_to_canvas(box["left"], box["top"], self.zoom)
                x_right, y_bottom = image_to_canvas(
                    box["right"] + 1, box["bottom"] + 1, self.zoom
                )
                self.canvas.create_rectangle(
                    x_left,
                    y_top,
                    x_right,
                    y_bottom,
                    outline="#ffb000" if selected else color,
                    width=3 if selected else 2,
                )
                if selected:
                    self.canvas.create_text(
                        x_left + 3,
                        max(3, y_top - 14),
                        text=item_id,
                        fill="#9a5b00",
                        anchor="nw",
                    )
                if selected and kind != "systems":
                    self.canvas.create_rectangle(
                        x_right - 5,
                        y_bottom - 5,
                        x_right + 5,
                        y_bottom + 5,
                        fill="#ffb000",
                        outline="black",
                    )
        if self.pending_box:
            box = self.pending_box
            x_left, y_top = image_to_canvas(box["left"], box["top"], self.zoom)
            x_right, y_bottom = image_to_canvas(
                box["right"] + 1, box["bottom"] + 1, self.zoom
            )
            self.canvas.create_rectangle(
                x_left,
                y_top,
                x_right,
                y_bottom,
                outline="#d06000",
                width=3,
                dash=(6, 3),
            )

    def _point(self, event):
        return canvas_to_image(
            self.canvas.canvasx(event.x),
            self.canvas.canvasy(event.y),
            self.zoom,
            *self.editor.size,
        )

    def _hit(self, point):
        boxes = []
        for kind in ("clefs", "staffs", "systems"):
            for item in reversed(self.editor.data[kind]):
                item_id = item["staff_id"] if kind == "clefs" else item["id"]
                box = self.editor.box(kind, item_id)
                if box and (not self.review_mode or kind == "clefs"):
                    boxes.append((kind, item_id, box))
        return hit_box(point, boxes)

    def _press(self, event):
        if self.editor is None:
            return
        point = self._point(event)
        mode = self.tool.get()
        if mode == "Navegar":
            self.canvas.scan_mark(event.x, event.y)
            return
        if mode in ("Selecionar", "Mover/redimensionar"):
            hit = self._hit(point)
            if hit:
                self._select(*hit, focus=False)
                if mode == "Mover/redimensionar" and hit[0] != "systems":
                    self.drag_original = self.editor.box(*hit).copy()
                    self.drag_start = point
                    corner = self.drag_original
                    self.drag_resize = abs(point[0] - corner["right"]) <= max(
                        2, 8 / self.zoom
                    ) and abs(point[1] - corner["bottom"]) <= max(2, 8 / self.zoom)
            return
        if mode == "Caixa de clave" and (
            self.selected is None or self.selected[0] != "clefs"
        ):
            messagebox.showinfo(
                "Clave", "Selecione uma clave da lista antes de desenhar."
            )
            return
        if mode == "Caixa de clave":
            existing = self.pending_box or self.editor.box("clefs", self.selected[1])
            if existing and hit_box(point, [("clefs", self.selected[1], existing)]):
                self.drag_original = existing.copy()
                self.drag_start = point
                self.drag_resize = abs(point[0] - existing["right"]) <= max(
                    2, 8 / self.zoom
                ) and abs(point[1] - existing["bottom"]) <= max(2, 8 / self.zoom)
                return
        self.drag_start = point
        self.drag_original = None

    def _motion(self, event):
        if self.tool.get() == "Navegar":
            self.canvas.scan_dragto(event.x, event.y, gain=1)
            self._render()
            return
        if self.drag_start is None or self.editor is None:
            return
        point = self._point(event)
        mode = self.tool.get()
        try:
            if mode in ("Mover/redimensionar", "Caixa de clave") and self.drag_original:
                box = (
                    resize_box(self.drag_original, *point, *self.editor.size)
                    if self.drag_resize
                    else move_box(
                        self.drag_original,
                        point[0] - self.drag_start[0],
                        point[1] - self.drag_start[1],
                        *self.editor.size,
                    )
                )
            else:
                box = drag_box(self.drag_start, point)
        except AnnotationError:
            return
        if self.preview is not None:
            self.canvas.delete(self.preview)
        x0, y0 = image_to_canvas(box["left"], box["top"], self.zoom)
        x1, y1 = image_to_canvas(box["right"] + 1, box["bottom"] + 1, self.zoom)
        self.preview = self.canvas.create_rectangle(
            x0, y0, x1, y1, outline="#ffb000", width=2, dash=(5, 3)
        )

    def _release(self, event):
        if self.tool.get() == "Navegar":
            return
        if self.drag_start is None or self.editor is None:
            return
        start, original, resize = self.drag_start, self.drag_original, self.drag_resize
        self.drag_start = self.drag_original = None
        self.drag_resize = False
        if self.preview is not None:
            self.canvas.delete(self.preview)
            self.preview = None
        point = self._point(event)
        if point == start:
            self._render()
            return
        mode = self.tool.get()

        def change():
            if mode == "Mover/redimensionar" and original and self.selected:
                box = (
                    resize_box(original, *point, *self.editor.size)
                    if resize
                    else move_box(
                        original,
                        point[0] - start[0],
                        point[1] - start[1],
                        *self.editor.size,
                    )
                )
                self.editor.set_box(*self.selected, box, move=not resize)
            elif mode == "Nova pauta":
                item_id = self.editor.add_staff(drag_box(start, point))
                self._refresh()
                self._select("staffs", item_id)
                self.tool.set("Selecionar")
            elif mode == "Caixa de clave" and self.selected:
                if original:
                    self.pending_box = (
                        resize_box(original, *point, *self.editor.size)
                        if resize
                        else move_box(
                            original,
                            point[0] - start[0],
                            point[1] - start[1],
                            *self.editor.size,
                        )
                    )
                else:
                    self.pending_box = drag_box(start, point)
                self._update_review()
                self._render()
                return

        if self._try(change) is not False:
            self._refresh()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation", type=Path, help="reference-draft.json")
    parser.add_argument("--images-dir", type=Path, help="pasta do PNG/JPEG")
    args = parser.parse_args()
    if (args.annotation is None) != (args.images_dir is None):
        parser.error("informe --annotation e --images-dir juntos")
    if tk is None:
        print(
            "Tkinter indisponível. Instale o pacote leve python3-tk para o Python "
            "do sistema e recrie o venv, se necessário.",
            file=sys.stderr,
        )
        return 3
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Não foi possível abrir a janela Tk: {exc}", file=sys.stderr)
        return 3
    app = Annotator(root)
    if args.annotation is not None:
        app._try(lambda: app.open(args.annotation, args.images_dir))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
