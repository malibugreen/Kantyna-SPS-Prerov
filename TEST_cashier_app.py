import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import time
from datetime import datetime, date, timedelta
import os
import re
import csv
from utilities.database import Database
from utilities.image_utils import process_and_save_product_image, load_ctk_image, sanitize_filename, create_badge_image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def bind_enter(widget, callback):
    """Naváže klávesu Enter (hlavní i na numerické klávesnici) na zadanou akci."""
    widget.bind("<Return>", lambda e: callback())
    widget.bind("<KP_Enter>", lambda e: callback())

def parse_price(val_str: str) -> float:
    """Převede textový řetězec na cenu (podporuje desetinnou tečku i čárku)."""
    cleaned = str(val_str).strip().replace(" ", "").replace(",", ".")
    val = float(cleaned)
    return round(val, 2)

def format_price(val, with_currency: bool = True) -> str:
    """
    Naformátuje číslo/cenu do českého tvaru s desetinnou čárkou.
    Celistvá čísla (např. 45) -> '45 Kč' (nebo '45,00 Kč' pokud desetinná).
    Pokud má desetinnou část (např. 45.9) -> '45,90 Kč'.
    """
    if val is None or val == "":
        return "0,00 Kč" if with_currency else "0,00"
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return f"{val} Kč" if with_currency else str(val)

    # Pokud má desetinnou část, zobrazíme s přesností na 2 desetinná místa a čárkou
    if abs(f_val - round(f_val)) > 1e-6:
        formatted = f"{f_val:.2f}".replace(".", ",")
    else:
        # I pro celá čísla můžeme použít buď celé číslo nebo 2 místa;
        # v českém formátu: 45 Kč nebo 45,90 Kč
        # Pokud uživatel zadal např. 45 -> 45 Kč, 45.9 -> 45,90 Kč
        # Ale pokud je to přímo float s .00, zobrazíme hezky buď celistvě nebo se zachováním standardu
        formatted = f"{int(round(f_val))}"

    return f"{formatted} Kč" if with_currency else formatted

def format_price_input(val) -> str:
    """Naformátuje cenu do textového pole (s čárkou, např. 45 nebo 45,90)."""
    if val is None or val == "":
        return "0"
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return str(val)
    if abs(f_val - round(f_val)) > 1e-6:
        return f"{f_val:.2f}".replace(".", ",")
    return str(int(round(f_val)))

class DateMaskEntry(ctk.CTkEntry):
    """
    Chytré datumové pole ve formátu DD.MM.RRRR.
    - Po kliknutí se předvyplní dnešní datum (pokud bylo prázdné) a automaticky se označí den.
    - Po napsání čísla automaticky přeskakuje na měsíc a rok bez nutnosti psát tečky.
    - Kliknutím na den, měsíc nebo rok se daná část rovnou označí a lze ji přímo přepsat.
    """
    def __init__(self, master, on_enter_callback=None, **kwargs):
        kwargs["placeholder_text"] = "DD.MM.RRRR"
        super().__init__(master, **kwargs)
        self._is_active = False
        self._on_enter_callback = on_enter_callback
        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<Button-1>", self._on_click)
        self._entry.bind("<Key>", self._on_key)

    def _on_focus_in(self, event=None):
        if not self._is_active or not self.get_date_str():
            today_str = date.today().strftime("%d.%m.%Y")
            self._entry.delete(0, "end")
            self._entry.insert(0, today_str)
            self._is_active = True
        self.after(20, self._select_day)

    def _select_day(self):
        self._entry.icursor(0)
        self._entry.select_range(0, 2)

    def _select_month(self):
        self._entry.icursor(3)
        self._entry.select_range(3, 5)

    def _select_year(self):
        self._entry.icursor(6)
        self._entry.select_range(6, 10)

    def _on_click(self, event):
        self.after(20, self._handle_click_cursor)

    def _handle_click_cursor(self):
        try:
            cur = self._entry.index("insert")
        except Exception:
            cur = 0
        if cur <= 2:
            self._select_day()
        elif cur <= 5:
            self._select_month()
        else:
            self._select_year()

    def get_date_str(self):
        if not self._is_active:
            return ""
        val = self._entry.get().strip()
        return val if val != "DD.MM.RRRR" else ""

    def set_date_str(self, val):
        self._entry.delete(0, "end")
        if val:
            self._entry.insert(0, val)
            self._is_active = True
        else:
            self._is_active = False
            if hasattr(self, "_activate_placeholder"):
                self._activate_placeholder()

    def _on_key(self, event):
        if event.keysym in ("Tab", "Escape"):
            return
        if event.keysym in ("Return", "KP_Enter"):
            if self._on_enter_callback:
                self._on_enter_callback()
            return "break"
        if event.keysym in ("Left", "Right", "Up", "Down"):
            return
        if event.keysym == "BackSpace":
            try:
                cur = self._entry.index("insert")
            except Exception:
                cur = 0
            if cur in (3, 6):
                self._entry.icursor(cur - 1)
            return

        if not event.char or not event.char.isdigit():
            return "break"

        digit = event.char
        text = list(self._entry.get())
        if len(text) != 10:
            text = list(date.today().strftime("%d.%m.%Y"))

        try:
            cur = self._entry.index("insert")
        except Exception:
            cur = 0

        if cur in (2, 5):
            cur += 1

        val = int(digit)

        # 1. ZADÁVÁNÍ DNE (pozice 0 a 1)
        if cur == 0:
            if val > 3:
                # Pokud uživatel zadá např. 5, automaticky se zformátuje na 05 a skočí na měsíc
                text[0] = "0"
                text[1] = digit
                next_cur = 3
            else:
                text[0] = digit
                next_cur = 1
        elif cur == 1:
            tentative = int(text[0] + digit)
            if tentative > 31:
                # Den nemůže být víc než 31
                text[0] = "3"
                text[1] = "1"
            elif tentative == 0:
                text[0] = "0"
                text[1] = "1"
            else:
                text[1] = digit
            next_cur = 3

        # 2. ZADÁVÁNÍ MĚSÍCE (pozice 3 a 4)
        elif cur == 3:
            if val > 1:
                # Pokud uživatel zadá např. 7, automaticky se zformátuje na 07 a skočí na rok
                text[3] = "0"
                text[4] = digit
                next_cur = 6
            else:
                text[3] = digit
                next_cur = 4
        elif cur == 4:
            tentative = int(text[3] + digit)
            if tentative > 12:
                # Měsíc nemůže být víc než 12
                text[3] = "1"
                text[4] = "2"
            elif tentative == 0:
                text[3] = "0"
                text[4] = "1"
            else:
                text[4] = digit
            next_cur = 6

        # 3. ZADÁVÁNÍ ROKU (pozice 6 až 9)
        elif 6 <= cur <= 9:
            text[cur] = digit
            current_year = date.today().year
            curr_yr_str = str(current_year)
            
            # Kontrola, zda zadávaný rok nebo jeho začátek nepřekračuje aktuální rok
            yr_prefix = "".join(text[6 : cur + 1])
            max_prefix = curr_yr_str[: len(yr_prefix)]
            if int(yr_prefix) > int(max_prefix):
                # Pokud překročí aktuální rok, nastavíme maximální možný (aktuální) rok
                for i, c in enumerate(curr_yr_str):
                    text[6 + i] = c
                next_cur = 10
            else:
                next_cur = cur + 1

        new_text = "".join(text)
        self._entry.delete(0, "end")
        self._entry.insert(0, new_text)

        if next_cur == 3:
            self._select_month()
        elif next_cur == 6:
            self._select_year()
        elif next_cur <= 9:
            self._entry.icursor(next_cur)
            self._entry.select_clear()
        else:
            self._entry.icursor(10)
            self._entry.select_clear()

        return "break"

class ConfirmDeleteDialog(ctk.CTkToplevel):
    def __init__(self, parent, product_name: str, on_confirm_callback):
        super().__init__(parent)
        self.on_confirm_callback = on_confirm_callback

        self.title("Potvrzení smazání")
        self.geometry("400x200")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui(product_name)

    def _build_ui(self, product_name: str):
        lbl_icon = ctk.CTkLabel(self, text="⚠️", font=ctk.CTkFont(size=36))
        lbl_icon.pack(pady=(20, 5))

        lbl_text = ctk.CTkLabel(
            self, 
            text=f"Opravdu chcete vymazat tento produkt?\n\n\"{product_name}\"", 
            font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=340
        )
        lbl_text.pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=30)

        btn_cancel = ctk.CTkButton(
            btn_frame, 
            text="Zrušit", 
            width=150, 
            fg_color="#3a3d45", 
            hover_color="#4f525c",
            command=self.destroy
        )
        btn_cancel.pack(side="left", padx=5)

        btn_confirm = ctk.CTkButton(
            btn_frame, 
            text="Ano, smazat", 
            width=150, 
            fg_color="#dc3545", 
            hover_color="#bd2130",
            command=self._confirm
        )
        btn_confirm.pack(side="right", padx=5)

    def _confirm(self):
        self.destroy()
        self.on_confirm_callback()


class RegisterCustomerDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_registered_callback):
        super().__init__(parent)
        self.parent = parent
        self.on_registered_callback = on_registered_callback
        self.scanned_chip_uid = None
        self._auto_close_job = None

        self.title("Registrace nového zákazníka")
        self.geometry("460x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Nastavíme v hlavní aplikaci odkaz na tento otevřený dialog pro směrování čipů
        self.parent.active_registration_dialog = self

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()

    def _build_ui(self):
        lbl_title = ctk.CTkLabel(self, text="Registrace nového zákazníka", font=ctk.CTkFont(size=18, weight="bold"))
        lbl_title.pack(pady=(15, 10))

        # Karta stavu čipu
        self.chip_card = ctk.CTkFrame(self, fg_color="#1e2229", corner_radius=10)
        self.chip_card.pack(fill="x", padx=30, pady=(5, 8))

        self.lbl_chip_icon = ctk.CTkLabel(self.chip_card, text="💳", font=ctk.CTkFont(size=24))
        self.lbl_chip_icon.pack(side="left", padx=(15, 8), pady=10)

        self.lbl_chip_status = ctk.CTkLabel(
            self.chip_card, 
            text="Čekám na přiložení nového čipu...", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#f0ad4e",
            anchor="w"
        )
        self.lbl_chip_status.pack(side="left", fill="x", expand=True, padx=5, pady=10)

        # Testovací tlačítko simulace čipu (pouze v testovací verzi)
        self.btn_sim_chip = ctk.CTkButton(
            self,
            text="Simulovat čip (UID_99999)",
            height=28,
            font=ctk.CTkFont(size=12),
            fg_color="#3a3d45",
            hover_color="#4f525c",
            command=lambda: self.on_chip_scanned("UID_99999")
        )
        self.btn_sim_chip.pack(padx=30, pady=(0, 10), fill="x")

        # Jméno a příjmení
        ctk.CTkLabel(self, text="Jméno a příjmení studenta / zákazníka:", anchor="w").pack(fill="x", padx=30, pady=(5, 2))
        self.entry_name = ctk.CTkEntry(self, width=380, placeholder_text="Např. Jan Novák")
        self.entry_name.pack(padx=30, pady=(0, 10))
        bind_enter(self.entry_name, self._register_action)

        self.lbl_msg = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_msg.pack(pady=5)

        self.btn_register = ctk.CTkButton(
            self,
            text="Zaregistrovat zákazníka",
            fg_color="#28a745",
            hover_color="#218838",
            height=40,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._register_action
        )
        self.btn_register.pack(fill="x", padx=30, pady=(10, 8))

        btn_cancel = ctk.CTkButton(
            self,
            text="Zavřít",
            fg_color="#3a3d45",
            hover_color="#4f525c",
            height=30,
            command=self._on_close
        )
        btn_cancel.pack(fill="x", padx=30, pady=(0, 15))

    def on_chip_scanned(self, chip_uid: str):
        """Voláno, když je k čtečce přiložen čip (nebo kliknuto na simulaci) během otevřeného registračního okna."""
        self.scanned_chip_uid = chip_uid
        existing_user = Database.get_user_by_chip(chip_uid)
        if existing_user:
            self.lbl_chip_status.configure(
                text=f"Pozor: Čip {chip_uid} už má {existing_user.get('name', 'zákazník')}!",
                text_color="#e06c75"
            )
        else:
            self.lbl_chip_status.configure(
                text=f"Čip načten: {chip_uid}",
                text_color="#28a745"
            )
        self.lbl_msg.configure(text="")
        self.entry_name.focus()

    def _register_action(self):
        if not self.scanned_chip_uid:
            self.lbl_msg.configure(text="Nejprve přiložte čip ke čtečce!", text_color="#e06c75")
            return

        name = self.entry_name.get().strip()
        if not name:
            self.lbl_msg.configure(text="Zadejte jméno a příjmení zákazníka!", text_color="#e06c75")
            return

        # Registrace do databáze (počáteční kredit 0)
        success = Database.update_user_balance(self.scanned_chip_uid, new_balance=0, name=name)
        if success:
            self.lbl_msg.configure(
                text=f"Registrace byla úspěšná! Zákazník: {name}\nOkno se automaticky zavře za 5 sekund...",
                text_color="#28a745"
            )
            self.btn_register.configure(state="disabled")
            self.entry_name.configure(state="disabled")
            if hasattr(self, 'btn_sim_chip'):
                self.btn_sim_chip.configure(state="disabled")
            if self.on_registered_callback:
                self.on_registered_callback(self.scanned_chip_uid, name)
            self._auto_close_job = self.after(5000, self._on_close)
        else:
            self.lbl_msg.configure(text="Chyba při ukládání do databáze!", text_color="#e06c75")

    def _on_close(self):
        if self._auto_close_job:
            try:
                self.after_cancel(self._auto_close_job)
            except Exception:
                pass
        self.parent.active_registration_dialog = None
        self.destroy()


class CategoryManagementDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_categories_changed_callback):
        super().__init__(parent)
        self.parent = parent
        self.on_categories_changed_callback = on_categories_changed_callback

        self.title("Správa kategorií")
        self.geometry("450x480")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        lbl_title = ctk.CTkLabel(self, text="Správa kategorií zboží", font=ctk.CTkFont(size=18, weight="bold"))
        lbl_title.pack(pady=(15, 10))

        # Horní panel pro přidání nové kategorie
        add_frame = ctk.CTkFrame(self, fg_color="transparent")
        add_frame.pack(fill="x", padx=25, pady=(0, 10))

        self.entry_new_cat = ctk.CTkEntry(add_frame, placeholder_text="Název nové kategorie...", width=270, height=36)
        self.entry_new_cat.pack(side="left", padx=(0, 8))
        bind_enter(self.entry_new_cat, self._add_category)

        btn_add = ctk.CTkButton(
            add_frame, 
            text="Přidat", 
            width=100, 
            height=36, 
            fg_color="#28a745", 
            hover_color="#218838",
            font=ctk.CTkFont(weight="bold"),
            command=self._add_category
        )
        btn_add.pack(side="left")

        self.lbl_info = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_info.pack(pady=(0, 5))

        # Seznam existujících kategorií
        self.scroll_cats = ctk.CTkScrollableFrame(self, height=300)
        self.scroll_cats.pack(fill="both", expand=True, padx=25, pady=(0, 15))

        self._render_categories_list()

    def _render_categories_list(self):
        for w in self.scroll_cats.winfo_children():
            w.destroy()

        categories = Database.get_categories()
        if not categories:
            ctk.CTkLabel(self.scroll_cats, text="Žádné kategorie.", text_color="#777").pack(pady=30)
            return

        for cat in categories:
            row = ctk.CTkFrame(self.scroll_cats, fg_color="#252525", corner_radius=8)
            row.pack(fill="x", pady=4, padx=2)

            name_lbl = ctk.CTkLabel(row, text=cat, font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
            name_lbl.pack(side="left", padx=12, pady=8)

            btn_del = ctk.CTkButton(
                row, 
                text="Smazat", 
                width=65, 
                height=28, 
                fg_color="#dc3545", 
                hover_color="#bd2130",
                command=lambda c=cat: self._delete_category(c)
            )
            btn_del.pack(side="right", padx=(4, 10))

            btn_edit = ctk.CTkButton(
                row, 
                text="Upravit", 
                width=65, 
                height=28, 
                fg_color="#1f6aa5", 
                hover_color="#144870",
                command=lambda c=cat: self._open_rename_prompt(c)
            )
            btn_edit.pack(side="right", padx=4)

    def _add_category(self):
        new_name = self.entry_new_cat.get().strip()
        if not new_name:
            self.lbl_info.configure(text="Zadejte název kategorie!", text_color="#e06c75")
            return

        success = Database.add_category(new_name)
        if success:
            self.entry_new_cat.delete(0, "end")
            self.lbl_info.configure(text=f"Kategorie '{new_name}' byla přidána.", text_color="#28a745")
            self._render_categories_list()
            self.on_categories_changed_callback()
        else:
            self.lbl_info.configure(text="Tato kategorie již existuje!", text_color="#e06c75")

    def _delete_category(self, cat_name: str):
        # Potvrzení smazání kategorie
        ConfirmDeleteDialog(self, f"Kategorii '{cat_name}'", lambda: self._confirm_delete(cat_name))

    def _confirm_delete(self, cat_name: str):
        Database.delete_category(cat_name)
        self.lbl_info.configure(text=f"Kategorie '{cat_name}' byla smazána.", text_color="#28a745")
        self._render_categories_list()
        self.on_categories_changed_callback()

    def _open_rename_prompt(self, old_name: str):
        # Dialog pro přejmenování kategorie
        dialog = ctk.CTkInputDialog(text=f"Zadejte nový název pro kategorii '{old_name}':", title="Přejmenovat kategorii")
        new_name = dialog.get_input()
        if new_name and new_name.strip():
            new_name = new_name.strip()
            Database.rename_category(old_name, new_name)
            self.lbl_info.configure(text=f"Kategorie přejmenována na '{new_name}'.", text_color="#28a745")
            self._render_categories_list()
            self.on_categories_changed_callback()


class EditProductDialog(ctk.CTkToplevel):
    def __init__(self, parent, pid: str, product_data: dict, all_products: dict, on_save_callback):
        super().__init__(parent)
        self.pid = pid
        self.product_data = dict(product_data)
        self.all_products = all_products
        self.on_save_callback = on_save_callback
        self.selected_image_path = None

        self.title("Upravit produkt")
        self.geometry("480x560")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        lbl_title = ctk.CTkLabel(self, text="Úprava produktu", font=ctk.CTkFont(size=18, weight="bold"))
        lbl_title.pack(pady=(15, 10))

        # Název
        ctk.CTkLabel(self, text="Název produktu:", anchor="w").pack(fill="x", padx=30, pady=(5, 2))
        self.entry_name = ctk.CTkEntry(self, width=380)
        self.entry_name.insert(0, self.product_data.get("name", ""))
        self.entry_name.pack(padx=30, pady=(0, 10))
        bind_enter(self.entry_name, self._save)

        # Cena
        ctk.CTkLabel(self, text="Cena (Kč):", anchor="w").pack(fill="x", padx=30, pady=(5, 2))
        self.entry_price = ctk.CTkEntry(self, width=380)
        self.entry_price.insert(0, format_price_input(self.product_data.get("price", 0)))
        self.entry_price.pack(padx=30, pady=(0, 10))
        bind_enter(self.entry_price, self._save)

        # Kategorie
        ctk.CTkLabel(self, text="Kategorie:", anchor="w").pack(fill="x", padx=30, pady=(5, 2))
        cat_frame = ctk.CTkFrame(self, fg_color="transparent")
        cat_frame.pack(fill="x", padx=30, pady=(0, 10))

        self.categories_list = Database.get_categories()
        current_cat = self.product_data.get("category", self.categories_list[0] if self.categories_list else "Slané")
        if current_cat not in self.categories_list:
            self.categories_list.append(current_cat)

        self.category_opt = ctk.CTkOptionMenu(
            cat_frame, 
            values=self.categories_list + ["* Správa kategorií *"],
            command=self._on_category_select,
            width=280
        )
        self.category_opt.set(current_cat)
        self.category_opt.pack(side="left")

        # Fotka
        ctk.CTkLabel(self, text="Fotka produktu (volitelná):", anchor="w").pack(fill="x", padx=30, pady=(5, 2))
        photo_frame = ctk.CTkFrame(self, fg_color="transparent")
        photo_frame.pack(fill="x", padx=30, pady=(0, 15))

        self.preview_lbl = ctk.CTkLabel(photo_frame, text="", width=50, height=50)
        self.preview_lbl.pack(side="left", padx=(0, 10))
        self._update_preview()

        btn_pick = ctk.CTkButton(
            photo_frame,
            text="Vybrat novou fotku",
            fg_color="#f0f0f0",
            text_color="#1a1a1a",
            hover_color="#d0d0d0",
            font=ctk.CTkFont(weight="bold"),
            command=self._pick_photo
        )
        btn_pick.pack(side="left", fill="x", expand=True)

        self.lbl_info = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_info.pack(pady=5)

        btn_save = ctk.CTkButton(
            self,
            text="Uložit změny",
            fg_color="#28a745",
            hover_color="#218838",
            height=40,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._save
        )
        btn_save.pack(fill="x", padx=30, pady=(10, 15))

    def _on_category_select(self, choice):
        if choice == "* Správa kategorií *":
            CategoryManagementDialog(self, self._refresh_categories_in_dialog)

    def _refresh_categories_in_dialog(self):
        self.categories_list = Database.get_categories()
        cur = self.product_data.get("category", self.categories_list[0] if self.categories_list else "Slané")
        if cur not in self.categories_list and self.categories_list:
            cur = self.categories_list[0]
        self.category_opt.configure(values=self.categories_list + ["* Správa kategorií *"])
        self.category_opt.set(cur)

    def _update_preview(self):
        ctk_img = load_ctk_image(self.product_data, (45, 45))
        if ctk_img:
            self.preview_lbl.configure(image=ctk_img, text="")
        else:
            self.preview_lbl.configure(image=None, text="Bez fotky", text_color="#777")

    def _pick_photo(self):
        f = filedialog.askopenfilename(
            title="Vyberte obrázek produktu",
            filetypes=[("Obrázky", "*.png *.jpg *.jpeg *.webp *.bmp")]
        )
        if f:
            self.selected_image_path = f
            self.lbl_info.configure(text=f"Vybráno: {os.path.basename(f)}", text_color="#4da6ff")
            try:
                from PIL import Image
                pil_img = Image.open(f)
                new_ctk = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(45, 45))
                self.preview_lbl.configure(image=new_ctk, text="")
            except Exception:
                pass

    def _save(self):
        new_name = self.entry_name.get().strip()
        new_price_str = self.entry_price.get().strip()

        if not new_name or not new_price_str:
            self.lbl_info.configure(text="Vyplňte název i cenu!", text_color="#e06c75")
            return

        # Kategorie
        final_cat = self.category_opt.get()
        if not final_cat or final_cat == "* Správa kategorií *":
            self.lbl_info.configure(text="Vyberte platnou kategorii!", text_color="#e06c75")
            return

        for other_id, other_prod in self.all_products.items():
            if other_id != self.pid:
                if other_prod.get("name", "").strip().lower() == new_name.lower():
                    self.lbl_info.configure(text="Produkt s tímto názvem již existuje!", text_color="#e06c75")
                    return

        try:
            new_price = parse_price(new_price_str)
            if new_price < 0:
                self.lbl_info.configure(text="Cena nemůže být záporná!", text_color="#e06c75")
                return
        except ValueError:
            self.lbl_info.configure(text="Cena musí být platné číslo!", text_color="#e06c75")
            return

        self.product_data["name"] = new_name
        self.product_data["price"] = new_price
        self.product_data["category"] = final_cat

        # Stará cesta k fotce před úpravou
        old_image_rel = self.product_data.get("image_path")
        old_image_full = None
        if old_image_rel:
            old_image_full = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), old_image_rel)

        # 1. Vybrána nová fotka
        if self.selected_image_path:
            img_path, img_b64 = process_and_save_product_image(self.selected_image_path, new_name)
            self.product_data["image_path"] = img_path
            self.product_data["image_base64"] = img_b64

            # Smazání starého souboru, pokud existoval a je jiný než nově vytvořený
            new_image_full = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), img_path)
            if old_image_full and os.path.exists(old_image_full):
                if os.path.abspath(old_image_full) != os.path.abspath(new_image_full):
                    try:
                        os.remove(old_image_full)
                    except Exception:
                        pass

        # 2. Fotka se nemění, ale změnil se název produktu -> přejmenovat existující soubor
        elif self.product_data.get("image_base64") and old_image_full and os.path.exists(old_image_full):
            safe_fn = sanitize_filename(new_name)
            new_rel = f"product_images/{safe_fn}.png"
            new_full = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), new_rel)

            if os.path.abspath(old_image_full) != os.path.abspath(new_full):
                try:
                    os.rename(old_image_full, new_full)
                except Exception:
                    pass
            self.product_data["image_path"] = new_rel

        self.on_save_callback(self.pid, self.product_data)
        self.destroy()


class CashierApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("[TESTOVACÍ] Školní Kantýna - Rozhraní Pokladní")
        self.geometry("1240x780")
        self.minsize(1050, 680)

        self.current_user = None
        self.products = {}
        self.orders = {}
        self.new_product_image_path = None
        self._image_cache = {}
        self._sync_thread_running = False
        self.active_registration_dialog = None

        # Zobrazení přihlašovací obrazovky
        self._build_login_screen()

    # --- PŘIHLAŠOVACÍ OBRAZOVKA (LOGIN) ---
    def _build_login_screen(self):
        self.login_container = ctk.CTkFrame(self, fg_color="transparent")
        self.login_container.pack(fill="both", expand=True)

        card = ctk.CTkFrame(self.login_container, width=420, corner_radius=18, fg_color="#1e2229")
        card.place(relx=0.5, rely=0.5, anchor="center")

        lbl_icon = ctk.CTkLabel(card, text="🔒", font=ctk.CTkFont(size=44))
        lbl_icon.pack(pady=(35, 10))

        lbl_title = ctk.CTkLabel(card, text="Přihlášení obsluhy", font=ctk.CTkFont(size=22, weight="bold"))
        lbl_title.pack(pady=(0, 5))

        lbl_sub = ctk.CTkLabel(card, text="Školní kantýna - Rozhraní pokladny", text_color="#888", font=ctk.CTkFont(size=13))
        lbl_sub.pack(pady=(0, 25))

        # Uživatelské jméno
        ctk.CTkLabel(card, text="Uživatelské jméno:", anchor="w").pack(fill="x", padx=40, pady=(5, 2))
        self.login_username = ctk.CTkEntry(card, width=340, height=40, placeholder_text="Zadejte uživatelské jméno")
        self.login_username.pack(padx=40, pady=(0, 12))
        self.login_username.focus()

        # Heslo
        ctk.CTkLabel(card, text="Heslo:", anchor="w").pack(fill="x", padx=40, pady=(5, 2))
        self.login_password = ctk.CTkEntry(card, width=340, height=40, show="•", placeholder_text="Zadejte heslo")
        self.login_password.pack(padx=40, pady=(0, 15))

        # Klávesa Enter pro rychlé přihlášení (hlavní i numerický)
        bind_enter(self.login_username, self._attempt_login)
        bind_enter(self.login_password, self._attempt_login)

        self.login_status = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.login_status.pack(pady=(0, 10))

        btn_login = ctk.CTkButton(
            card,
            text="Přihlásit se do pokladny",
            width=340,
            height=44,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#007bff",
            hover_color="#0069d9",
            command=self._attempt_login
        )
        btn_login.pack(padx=40, pady=(0, 35))

    def _attempt_login(self):
        username = self.login_username.get().strip()
        password = self.login_password.get().strip()

        if not username or not password:
            self.login_status.configure(text="Zadejte uživatelské jméno i heslo!", text_color="#e06c75")
            return

        self.login_status.configure(text="Ověřuji údaje...", text_color="#4da6ff")
        self.update_idletasks()

        user_data = Database.verify_cashier_login(username, password)
        if user_data:
            user_data["username"] = username
            self.current_user = user_data
            self.login_container.destroy()
            self._build_main_app()
        else:
            self.login_status.configure(text="Neplatné uživatelské jméno nebo heslo!", text_color="#e06c75")

    def _logout(self):
        # Ukončení background synchronizace a zobrazení loginu
        self._sync_thread_running = False
        self.main_container.destroy()
        self.current_user = None
        self._build_login_screen()

    # --- HLAVNÍ APLIKACE (PO PŘIHLÁŠENÍ) ---
    def _build_main_app(self):
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True)

        # Horní záhlaví s informací o přihlášení a tlačítkem odhlásit
        header_bar = ctk.CTkFrame(self.main_container, height=45, fg_color="transparent")
        header_bar.pack(fill="x", padx=15, pady=(10, 0))

        user_name = self.current_user.get("name", "Pokladní")
        user_lbl = ctk.CTkLabel(
            header_bar,
            text=f"Přihlášen: {user_name} ({self.current_user.get('role', 'obsluha')})",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#98c379"
        )
        user_lbl.pack(side="left", padx=5)

        btn_logout = ctk.CTkButton(
            header_bar,
            text="Odhlásit se",
            width=90,
            height=28,
            fg_color="#3a3d45",
            hover_color="#dc3545",
            command=self._logout
        )
        btn_logout.pack(side="right", padx=5)

        # Hlavní rozvržení se 4 záložkami
        self.tabview = ctk.CTkTabview(self.main_container, corner_radius=15, command=self._on_tab_change)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        self.tab_orders = self.tabview.add("Živé objednávky")
        self.tab_credit = self.tabview.add("Dobíjení kreditu a Registrace")
        self.tab_stock = self.tabview.add("Správa zboží a Sklad")
        self.tab_stats = self.tabview.add("Statistiky a Historie")

        self._build_orders_tab()
        self._build_credit_tab()
        self._build_stock_tab()
        self._build_stats_tab()

        self._refresh_all_data()
        self._start_background_sync()

    def _on_tab_change(self):
        selected_tab = self.tabview.get()
        if "Statistiky" in selected_tab:
            # Obnovíme možnosti kategorií i data v tabulce statistik
            self._refresh_stats_filter_options()
            self._apply_stats_filter()
        elif "Sklad" in selected_tab:
            self.products = Database.get_products()
            self._render_stock_list()
        elif "Živé objednávky" in selected_tab:
            self.orders = Database.get_active_orders()
            self._render_orders()

    # --- 1. ZÁLOŽKA: ŽIVÉ OBJEDNÁVKY ---
    def _build_orders_tab(self):
        top = ctk.CTkFrame(self.tab_orders, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 10))

        title = ctk.CTkLabel(top, text="Aktivní objednávky čekající na výdej", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(side="left")

        self.badge_circle = ctk.CTkLabel(
            top, 
            text="", 
            width=36, 
            height=26, 
            corner_radius=13, 
            fg_color="#dc3545", 
            text_color="#ffffff", 
            font=ctk.CTkFont(size=14, weight="bold")
        )

        self.orders_scroll = ctk.CTkScrollableFrame(self.tab_orders)
        self.orders_scroll.pack(fill="both", expand=True, padx=10, pady=5)

    def _render_orders(self):
        for widget in self.orders_scroll.winfo_children():
            widget.destroy()

        count = len(self.orders)

        if count > 0:
            self.badge_circle.configure(text=f"{count}")
            self.badge_circle.pack(side="left", padx=12)
        else:
            self.badge_circle.pack_forget()

        try:
            tab_buttons = self.tabview._segmented_button._buttons_dict
            tab_btn = None
            for name, btn in tab_buttons.items():
                if "Živé objednávky" in name:
                    tab_btn = btn
                    break

            if tab_btn:
                if count > 0:
                    badge_img = create_badge_image(count, diameter=18)
                    tab_btn.configure(text="Živé objednávky  ", image=badge_img, compound="right")
                else:
                    tab_btn.configure(text="Živé objednávky", image=None)
        except Exception:
            pass

        if not self.orders:
            lbl = ctk.CTkLabel(self.orders_scroll, text="Žádné čekající objednávky. Vše vydáno!", text_color="#777777", font=ctk.CTkFont(size=15))
            lbl.pack(pady=40)
            return

        for order_id, order in self.orders.items():
            card = ctk.CTkFrame(self.orders_scroll, fg_color="#23272e", corner_radius=10)
            card.pack(fill="x", pady=6, padx=5)

            left_info = ctk.CTkFrame(card, fg_color="transparent")
            left_info.pack(side="left", padx=15, pady=10)

            short_id = order_id[-5:]
            ord_total_str = format_price(order.get('total', 0))
            ord_title = ctk.CTkLabel(
                left_info, 
                text=f"Objednávka #{short_id} - {order.get('student', 'Student')} ({ord_total_str})", 
                font=ctk.CTkFont(size=16, weight="bold"),
                anchor="w"
            )
            ord_title.pack(anchor="w")

            ord_items = ctk.CTkLabel(left_info, text=order.get("items", ""), font=ctk.CTkFont(size=13), text_color="#aaaaaa")
            ord_items.pack(anchor="w", pady=(3, 0))

            done_btn = ctk.CTkButton(
                card, 
                text="Vydat / Dokončit", 
                fg_color="#28a745", 
                hover_color="#218838",
                command=lambda o_id=order_id: self._complete_order_action(o_id)
            )
            done_btn.pack(side="right", padx=15, pady=10)

    def _complete_order_action(self, order_id):
        cashier_name = self.current_user.get("username", "obsluha") if self.current_user else "obsluha"
        Database.complete_order(order_id, cashier_user=cashier_name)
        if order_id in self.orders:
            del self.orders[order_id]
        self._render_orders()

    # --- 2. ZÁLOŽKA: DOBÍJENÍ KREDITU ---
    def _build_credit_tab(self):
        box = ctk.CTkFrame(self.tab_credit, corner_radius=12, width=500)
        box.pack(padx=20, pady=25, fill="x")

        lbl = ctk.CTkLabel(box, text="Dobití kreditu na čip", font=ctk.CTkFont(size=20, weight="bold"))
        lbl.pack(pady=(15, 10))

        self.chip_entry = ctk.CTkEntry(box, placeholder_text="Přiložte čip ke čtečce (nebo zadejte UID)...", width=380, height=38)
        self.chip_entry.pack(pady=6)
        bind_enter(self.chip_entry, self._check_chip_info)

        self.sim_chip_btn = ctk.CTkButton(
            box, 
            text="Simulovat čip (UID_12345)", 
            width=380, 
            height=32,
            fg_color="#3a3d45", 
            hover_color="#4f525c",
            font=ctk.CTkFont(size=13),
            command=self._sim_chip_action
        )
        self.sim_chip_btn.pack(pady=(2, 10))

        self.chip_info_label = ctk.CTkLabel(box, text="Čekám na přiložení čipu...", font=ctk.CTkFont(size=14), text_color="#aaaaaa")
        self.chip_info_label.pack(pady=4)

        self.amount_entry = ctk.CTkEntry(box, placeholder_text="Částka k dobití v Kč...", width=380, height=38)
        self.amount_entry.pack(pady=8)
        bind_enter(self.amount_entry, self._add_credit_action)

        quick_frame = ctk.CTkFrame(box, fg_color="transparent")
        quick_frame.pack(pady=6)

        for amt in [50, 100, 200, 500]:
            btn = ctk.CTkButton(
                quick_frame, 
                text=f"+{amt} Kč", 
                width=85,
                fg_color="#3a3d45",
                command=lambda a=amt: self._set_amount(a)
            )
            btn.pack(side="left", padx=4)

        submit_btn = ctk.CTkButton(
            box, 
            text="Připsat kredit hotově", 
            fg_color="#007bff", 
            hover_color="#0069d9",
            height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._add_credit_action
        )
        submit_btn.pack(pady=(15, 15))

        self.credit_status = ctk.CTkLabel(box, text="", font=ctk.CTkFont(size=14))
        self.credit_status.pack(pady=(0, 10))

        # Tlačítko pro registraci nového zákazníka
        btn_open_reg = ctk.CTkButton(
            box,
            text="+ Zaregistrovat nového zákazníka",
            fg_color="#1f6aa5",
            hover_color="#144870",
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._open_register_customer_dialog
        )
        btn_open_reg.pack(pady=(0, 15))

    def _open_register_customer_dialog(self):
        RegisterCustomerDialog(self, on_registered_callback=self._on_customer_registered)

    def _on_customer_registered(self, chip_uid: str, student_name: str):
        self.chip_entry.delete(0, "end")
        self.chip_entry.insert(0, chip_uid)
        self._check_chip_info()

    def _sim_chip_action(self):
        if self.active_registration_dialog and self.active_registration_dialog.winfo_exists():
            self.active_registration_dialog.on_chip_scanned("UID_12345")
            return

        self.chip_entry.delete(0, "end")
        self.chip_entry.insert(0, "UID_12345")
        self._check_chip_info()

    def _set_amount(self, amt):
        self.amount_entry.delete(0, "end")
        self.amount_entry.insert(0, str(amt))

    def _check_chip_info(self):
        chip = self.chip_entry.get().strip()
        if not chip:
            self.chip_info_label.configure(text="Čekám na přiložení čipu...", text_color="#aaaaaa")
            return
        user = Database.get_user_by_chip(chip)
        if user:
            self.chip_info_label.configure(text=f"Zákazník: {user.get('name')} | Aktuální zůstatek: {format_price(user.get('balance', 0))}", text_color="#28a745")
        else:
            self.chip_info_label.configure(text="Zákazník není registrován! (Použijte tlačítko níže pro registraci)", text_color="#e06c75")

    def _add_credit_action(self):
        chip = self.chip_entry.get().strip()
        amt_str = self.amount_entry.get().strip()

        if not chip or not amt_str:
            self.credit_status.configure(text="Vyplňte čip i částku!", text_color="#e06c75")
            return

        try:
            amt = int(amt_str)
        except ValueError:
            self.credit_status.configure(text="Částka musí být celé číslo!", text_color="#e06c75")
            return

        user = Database.get_user_by_chip(chip)
        if not user:
            self.credit_status.configure(text="Tento čip není registrován! Nejprve zákazníka zaregistrujte.", text_color="#e06c75")
            return

        student_name = user.get("name", "Student")
        old_balance = user.get("balance", 0)
        new_balance = old_balance + amt
        cashier_name = self.current_user.get("username", "admin") if self.current_user else "admin"
        Database.update_user_balance(chip, new_balance, name=student_name)
        Database.log_credit_topup(chip, student_name, amt, cashier_user=cashier_name)

        self.credit_status.configure(text=f"Úspěšně připsáno {format_price(amt)}! Nový zůstatek: {format_price(new_balance)}", text_color="#28a745")
        self.amount_entry.delete(0, "end")
        self._check_chip_info()

    # --- 3. ZÁLOŽKA: SPRÁVA ZBOŽÍ & SKLAD ---
    def _build_stock_tab(self):
        top_frame = ctk.CTkFrame(self.tab_stock, corner_radius=10)
        top_frame.pack(fill="x", padx=10, pady=10)

        # 1. řádek: vstupy
        row1 = ctk.CTkFrame(top_frame, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(row1, text="Přidat položku:", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(0, 10))

        self.prod_name = ctk.CTkEntry(row1, placeholder_text="Název produktu *", width=170)
        self.prod_name.pack(side="left", padx=4)
        bind_enter(self.prod_name, self._add_product)

        self.prod_price = ctk.CTkEntry(row1, placeholder_text="Cena (Kč) *", width=85)
        self.prod_price.pack(side="left", padx=4)
        bind_enter(self.prod_price, self._add_product)

        self.prod_stock = ctk.CTkEntry(row1, placeholder_text="Skladem (ks) *", width=95)
        self.prod_stock.pack(side="left", padx=4)
        bind_enter(self.prod_stock, self._add_product)

        # Výběr kategorie
        self.categories_list = Database.get_categories()
        default_cat = self.categories_list[0] if self.categories_list else "Slané"
        self.stock_cat_opt = ctk.CTkOptionMenu(
            row1, 
            values=self.categories_list + ["* Správa kategorií *"],
            command=self._on_new_product_cat_select,
            width=180
        )
        self.stock_cat_opt.set(default_cat)
        self.stock_cat_opt.pack(side="left", padx=4)

        # Tlačítko na fotku a přidání
        self.btn_pick_img = ctk.CTkButton(
            row1, 
            text="Vybrat fotku", 
            fg_color="#f0f0f0", 
            text_color="#1a1a1a",
            hover_color="#d0d0d0",
            font=ctk.CTkFont(weight="bold"),
            width=100,
            command=self._pick_new_product_image
        )
        self.btn_pick_img.pack(side="left", padx=6)

        add_btn = ctk.CTkButton(row1, text="Přidat produkt", fg_color="#28a745", hover_color="#218838", width=110, command=self._add_product)
        add_btn.pack(side="left", padx=6)

        self.stock_notification = ctk.CTkLabel(self.tab_stock, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.stock_notification.pack(pady=(0, 5))

        self.stock_scroll = ctk.CTkScrollableFrame(self.tab_stock)
        self.stock_scroll.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    def _on_new_product_cat_select(self, choice):
        if choice == "* Správa kategorií *":
            CategoryManagementDialog(self, self._refresh_categories_in_cashier)

    def _refresh_categories_in_cashier(self):
        self.categories_list = Database.get_categories()
        default_cat = self.categories_list[0] if self.categories_list else "Slané"
        self.stock_cat_opt.configure(values=self.categories_list + ["* Správa kategorií *"])
        self.stock_cat_opt.set(default_cat)
        # Obnovíme zobrazení seznamu produktů
        self.products = Database.get_products()
        self._render_stock_list()

    def _pick_new_product_image(self):
        f = filedialog.askopenfilename(
            title="Vyberte fotku produktu (1:1)",
            filetypes=[("Obrázky", "*.png *.jpg *.jpeg *.webp *.bmp")]
        )
        if f:
            self.new_product_image_path = f
            self.btn_pick_img.configure(text=f"✓ {os.path.basename(f)[:10]}...", fg_color="#d4edda")

    def _show_stock_error(self, msg: str):
        self.stock_notification.configure(text=msg, text_color="#e06c75")
        self.after(4000, lambda: self.stock_notification.configure(text=""))

    def _render_stock_list(self):
        for w in self.stock_scroll.winfo_children():
            w.destroy()
        self._image_cache.clear()

        for pid, item in self.products.items():
            row_frame = ctk.CTkFrame(self.stock_scroll, fg_color="#22252b")
            row_frame.pack(fill="x", pady=4, padx=5)

            ctk_img = load_ctk_image(item, (38, 38))
            if ctk_img:
                self._image_cache[pid] = ctk_img
                img_lbl = ctk.CTkLabel(row_frame, text="", image=ctk_img, width=42)
            else:
                img_lbl = ctk.CTkLabel(row_frame, text="[Foto]", font=ctk.CTkFont(size=10), text_color="#777", width=42)
            img_lbl.pack(side="left", padx=(8, 4), pady=4)

            name_lbl = ctk.CTkLabel(row_frame, text=item.get("name", ""), width=170, anchor="w", font=ctk.CTkFont(weight="bold"))
            name_lbl.pack(side="left", padx=6, pady=8)

            # Kategorie (štítek)
            cat_text = item.get("category", "Slané")
            cat_badge = ctk.CTkLabel(row_frame, text=cat_text, width=80, fg_color="#1e2229", corner_radius=6, text_color="#98c379", font=ctk.CTkFont(size=12))
            cat_badge.pack(side="left", padx=6)

            price_lbl = ctk.CTkLabel(row_frame, text=format_price(item.get('price', 0)), width=75, anchor="w")
            price_lbl.pack(side="left", padx=6)

            stock = item.get("stock", 0)
            stock_frame = ctk.CTkFrame(row_frame, fg_color="transparent", width=110)
            stock_frame.pack(side="left", padx=6)

            if 0 <= stock <= 5:
                warn_text = f"Pozor: {stock} ks"
                warn_color = "#e57373"
            else:
                warn_text = f"{stock} ks"
                warn_color = "#ffffff"

            stock_lbl = ctk.CTkLabel(stock_frame, text=f"Sklad: {warn_text}", font=ctk.CTkFont(weight="bold" if stock <= 5 else "normal"), text_color=warn_color)
            stock_lbl.pack(anchor="w")

            btn_minus = ctk.CTkButton(row_frame, text="-1", width=36, fg_color="#444444", hover_color="#555555", command=lambda p_id=pid: self._adjust_stock(p_id, -1))
            btn_minus.pack(side="left", padx=2)

            btn_plus = ctk.CTkButton(row_frame, text="+1", width=36, fg_color="#444444", hover_color="#555555", command=lambda p_id=pid: self._adjust_stock(p_id, 1))
            btn_plus.pack(side="left", padx=2)

            custom_entry = ctk.CTkEntry(row_frame, width=50, placeholder_text="±ks")
            custom_entry.pack(side="left", padx=3)
            bind_enter(custom_entry, lambda p_id=pid, ent=custom_entry: self._apply_custom_stock(p_id, ent))

            btn_apply = ctk.CTkButton(
                row_frame, 
                text="Použít", 
                width=48, 
                fg_color="#3a3d45", 
                hover_color="#4f525c",
                command=lambda p_id=pid, ent=custom_entry: self._apply_custom_stock(p_id, ent)
            )
            btn_apply.pack(side="left", padx=2)

            actions_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            actions_frame.pack(side="right", padx=10)

            btn_delete = ctk.CTkButton(
                actions_frame,
                text="Smazat",
                width=75,
                fg_color="#dc3545",
                hover_color="#bd2130",
                command=lambda p_id=pid: self._confirm_delete_product(p_id)
            )
            btn_delete.pack(side="right", padx=(5, 0))

            btn_edit = ctk.CTkButton(
                actions_frame,
                text="Upravit",
                width=75,
                fg_color="#1f6aa5",
                hover_color="#144870",
                command=lambda p_id=pid: self._open_edit_dialog(p_id)
            )
            btn_edit.pack(side="right", padx=(0, 5))

    def _adjust_stock(self, pid, delta):
        cur_stock = self.products[pid].get("stock", 0)
        target_stock = cur_stock + delta

        if target_stock < 0:
            self._show_stock_error("Skladové zásoby nemohou jít do mínusu, zadejte jinou částku.")
            return

        self.products[pid]["stock"] = target_stock
        Database.update_stock(pid, target_stock)

        if delta > 0:
            cashier_name = self.current_user.get("username", "admin") if self.current_user else "admin"
            Database.log_stock_replenishment(self.products[pid].get("name", "Neznámý"), delta, cashier_user=cashier_name)

        self._render_stock_list()

    def _apply_custom_stock(self, pid, entry_widget):
        val_str = entry_widget.get().strip()
        if not val_str:
            return

        try:
            delta = int(val_str)
        except ValueError:
            self._show_stock_error("Zadejte platné celé číslo (např. 10 nebo -5).")
            return

        cur_stock = self.products[pid].get("stock", 0)
        target_stock = cur_stock + delta

        if target_stock < 0:
            self._show_stock_error("Skladové zásoby nemohou jít do mínusu, zadejte jinou částku.")
            return

        self.products[pid]["stock"] = target_stock
        Database.update_stock(pid, target_stock)

        if delta > 0:
            cashier_name = self.current_user.get("username", "admin") if self.current_user else "admin"
            Database.log_stock_replenishment(self.products[pid].get("name", "Neznámý"), delta, cashier_user=cashier_name)

        entry_widget.delete(0, "end")
        self._render_stock_list()

    def _open_edit_dialog(self, pid):
        EditProductDialog(self, pid, self.products[pid], self.products, self._on_product_edited)

    def _on_product_edited(self, pid, updated_data):
        self.products[pid] = updated_data
        Database.save_product(pid, updated_data)
        self._render_stock_list()

    def _confirm_delete_product(self, pid):
        prod = self.products.get(pid, {})
        prod_name = prod.get("name", "tento produkt")
        ConfirmDeleteDialog(self, prod_name, lambda: self._execute_delete_product(pid))

    def _execute_delete_product(self, pid):
        prod = self.products.get(pid, {})
        local_rel = prod.get("image_path")
        if local_rel:
            full_p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), local_rel)
            if os.path.exists(full_p):
                try:
                    os.remove(full_p)
                except Exception:
                    pass

        Database.delete_product(pid)
        if pid in self.products:
            del self.products[pid]

        self._render_stock_list()
        self.stock_notification.configure(text="Produkt byl úspěšně smazán.", text_color="#28a745")
        self.after(3000, lambda: self.stock_notification.configure(text=""))

    def _add_product(self):
        name = self.prod_name.get().strip()
        price_str = self.prod_price.get().strip()
        stock_str = self.prod_stock.get().strip()

        if not name or not price_str or not stock_str:
            self._show_stock_error("Vyplňte prosím název, cenu i počáteční stav skladu!")
            return

        for existing_prod in self.products.values():
            if existing_prod.get("name", "").strip().lower() == name.lower():
                self._show_stock_error(f"Produkt s názvem '{name}' již existuje!")
                return

        try:
            price = parse_price(price_str)
            if price < 0:
                self._show_stock_error("Cena nemůže být záporná!")
                return
        except ValueError:
            self._show_stock_error("Cena musí být platné číslo!")
            return

        try:
            stock = int(stock_str)
            if stock < 0:
                self._show_stock_error("Skladové zásoby nemohou být záporné!")
                return
        except ValueError:
            self._show_stock_error("Skladové zásoby musí být celé číslo!")
            return

        # Validace kategorie
        final_cat = self.stock_cat_opt.get()
        if not final_cat or final_cat == "* Správa kategorií *":
            self._show_stock_error("Vyberte platnou kategorii produktu!")
            return

        safe_slug = sanitize_filename(name)
        pid = f"prod_{safe_slug}_{int(time.time())}"
        data = {
            "name": name,
            "price": price,
            "stock": stock,
            "category": final_cat
        }

        # Fotka je volitelná
        if self.new_product_image_path:
            img_path, img_b64 = process_and_save_product_image(self.new_product_image_path, name)
            data["image_path"] = img_path
            data["image_base64"] = img_b64
            self.new_product_image_path = None
            self.btn_pick_img.configure(text="Vybrat fotku", fg_color="#f0f0f0")

        Database.save_product(pid, data)
        self.products[pid] = data

        if stock > 0:
            cashier_name = self.current_user.get("username", "admin") if self.current_user else "admin"
            Database.log_stock_replenishment(name, stock, cashier_user=cashier_name)

        self.prod_name.delete(0, "end")
        self.prod_price.delete(0, "end")
        self.prod_stock.delete(0, "end")
        self._render_stock_list()

    # --- 4. ZÁLOŽKA: STATISTIKY & HISTORIE ---
    def _build_stats_tab(self):
        top_bar = ctk.CTkFrame(self.tab_stats, fg_color="transparent")
        top_bar.pack(fill="x", padx=10, pady=(10, 5))

        self.mode_selector = ctk.CTkSegmentedButton(
            top_bar,
            values=["Prodej zboží", "Doplnění kreditu", "Doplnění zboží"],
            command=self._on_stats_mode_change,
            height=38,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.mode_selector.set("Prodej zboží")
        self.mode_selector.pack(side="left")

        btn_export = ctk.CTkButton(
            top_bar,
            text="Export do CSV",
            height=38,
            width=140,
            fg_color="#28a745",
            hover_color="#218838",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._export_all_to_csv
        )
        btn_export.pack(side="right")

        filter_bar = ctk.CTkFrame(self.tab_stats, corner_radius=10)
        filter_bar.pack(fill="x", padx=10, pady=5)

        # 1. řádek filtrů: Datum a rychlé volby
        row_f1 = ctk.CTkFrame(filter_bar, fg_color="transparent")
        row_f1.pack(fill="x", padx=10, pady=(6, 4))

        ctk.CTkLabel(row_f1, text="Od:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(5, 5))
        self.date_from_entry = DateMaskEntry(row_f1, width=110, on_enter_callback=self._on_date_from_enter)
        self.date_from_entry.pack(side="left", padx=4)

        ctk.CTkLabel(row_f1, text="Do:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 5))
        self.date_to_entry = DateMaskEntry(row_f1, width=110, on_enter_callback=self._apply_stats_filter)
        self.date_to_entry.pack(side="left", padx=4)

        btn_filter = ctk.CTkButton(row_f1, text="Filtrovat", width=75, fg_color="#1f6aa5", command=self._apply_stats_filter)
        btn_filter.pack(side="left", padx=8)

        btn_today = ctk.CTkButton(row_f1, text="Dnes", width=60, fg_color="#3a3d45", command=self._set_filter_today)
        btn_today.pack(side="left", padx=2)

        btn_week = ctk.CTkButton(row_f1, text="7 dní", width=60, fg_color="#3a3d45", command=self._set_filter_week)
        btn_week.pack(side="left", padx=2)

        btn_month = ctk.CTkButton(row_f1, text="1 měsíc", width=65, fg_color="#3a3d45", command=self._set_filter_month)
        btn_month.pack(side="left", padx=2)

        btn_all = ctk.CTkButton(row_f1, text="Vše", width=60, fg_color="#3a3d45", command=self._set_filter_all)
        btn_all.pack(side="left", padx=2)

        self.stats_summary_lbl = ctk.CTkLabel(row_f1, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color="#4da6ff")
        self.stats_summary_lbl.pack(side="right", padx=10)

        # 2. řádek filtrů: Kategorie a Produkt
        self.prod_filter_row = ctk.CTkFrame(filter_bar, fg_color="transparent")
        self.prod_filter_row.pack(fill="x", padx=10, pady=(0, 6))

        ctk.CTkLabel(self.prod_filter_row, text="Kategorie:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(5, 5))
        self.stats_cat_filter = ctk.CTkOptionMenu(
            self.prod_filter_row,
            values=["Všechny kategorie"],
            command=self._on_stats_cat_filter_change,
            width=170
        )
        self.stats_cat_filter.pack(side="left", padx=4)

        ctk.CTkLabel(self.prod_filter_row, text="Produkt:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(15, 5))
        self.stats_prod_filter = ctk.CTkOptionMenu(
            self.prod_filter_row,
            values=["Všechny produkty"],
            command=self._on_stats_prod_filter_change,
            width=220
        )
        self.stats_prod_filter.pack(side="left", padx=4)

        # Štítek pro nejprodávanější zboží
        self.stats_top_prod_lbl = ctk.CTkLabel(
            self.prod_filter_row,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#98c379"
        )
        self.stats_top_prod_lbl.pack(side="right", padx=10)

        self._refresh_stats_filter_options()

        self.table_header_frame = ctk.CTkFrame(self.tab_stats, height=36, corner_radius=6, fg_color="#1c2026")
        self.table_header_frame.pack(fill="x", padx=10, pady=(8, 2))

        self.stats_scroll = ctk.CTkScrollableFrame(self.tab_stats)
        self.stats_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._set_filter_all()

    def _refresh_stats_filter_options(self):
        cats = ["Všechny kategorie"] + Database.get_categories()
        current_cat = self.stats_cat_filter.get()
        if current_cat not in cats:
            current_cat = "Všechny kategorie"
        self.stats_cat_filter.configure(values=cats)
        self.stats_cat_filter.set(current_cat)

        self._update_stats_products_options(current_cat)

    def _on_stats_cat_filter_change(self, selected_cat):
        self._update_stats_products_options(selected_cat)
        self._apply_stats_filter()

    def _on_stats_prod_filter_change(self, selected_prod):
        if selected_prod != "Všechny produkty":
            # Najdeme kategorii tohoto produktu a nastavíme ji v menu kategorie
            all_prods = Database.get_products()
            for p in all_prods.values():
                if p.get("name", "").strip().lower() == selected_prod.strip().lower():
                    cat = p.get("category")
                    if cat:
                        cats = ["Všechny kategorie"] + Database.get_categories()
                        if cat in cats:
                            self.stats_cat_filter.set(cat)
                            # Aktualizujeme nabídku produktů pro danou kategorii, ale zachováme vybraný produkt
                            self._update_stats_products_options(cat, preserve_prod=selected_prod)
                    break
        self._apply_stats_filter()

    def _update_stats_products_options(self, selected_cat, preserve_prod=None):
        all_prods = Database.get_products()
        prod_names = []

        for p in all_prods.values():
            p_cat = p.get("category", "")
            p_name = p.get("name", "")
            if selected_cat == "Všechny kategorie" or p_cat.lower() == selected_cat.lower():
                if p_name and p_name not in prod_names:
                    prod_names.append(p_name)

        prod_names.sort()
        values = ["Všechny produkty"] + prod_names

        current_prod = preserve_prod or self.stats_prod_filter.get()
        if current_prod not in values:
            current_prod = "Všechny produkty"

        self.stats_prod_filter.configure(values=values)
        self.stats_prod_filter.set(current_prod)

    def _set_filter_today(self):
        today_str = date.today().strftime("%d.%m.%Y")
        self.date_from_entry.set_date_str(today_str)
        self.date_to_entry.set_date_str(today_str)
        self._apply_stats_filter()

    def _set_filter_week(self):
        end_d = date.today()
        start_d = end_d - timedelta(days=7)
        self.date_from_entry.set_date_str(start_d.strftime("%d.%m.%Y"))
        self.date_to_entry.set_date_str(end_d.strftime("%d.%m.%Y"))
        self._apply_stats_filter()

    def _set_filter_month(self):
        end_d = date.today()
        start_d = end_d - timedelta(days=30)
        self.date_from_entry.set_date_str(start_d.strftime("%d.%m.%Y"))
        self.date_to_entry.set_date_str(end_d.strftime("%d.%m.%Y"))
        self._apply_stats_filter()

    def _set_filter_all(self):
        self.date_from_entry.set_date_str("")
        self.date_to_entry.set_date_str("")
        self._apply_stats_filter()

    def _on_date_from_enter(self):
        # Pokud pole 'Do:' není vyplněné, automaticky se doplní dnešní datum
        if not self.date_to_entry.get_date_str():
            today_str = date.today().strftime("%d.%m.%Y")
            self.date_to_entry.set_date_str(today_str)
        self._apply_stats_filter()

    def _on_stats_mode_change(self, mode_name):
        # Reset data na výchozí (od nepaměti)
        self.date_from_entry.set_date_str("")
        self.date_to_entry.set_date_str("")

        if mode_name == "Doplnění kreditu":
            self.prod_filter_row.pack_forget()
        else:
            self.prod_filter_row.pack(fill="x", padx=10, pady=(0, 6))
            # Reset filtrů kategorie a produktu na výchozí hodnoty
            cats = ["Všechny kategorie"] + Database.get_categories()
            self.stats_cat_filter.configure(values=cats)
            self.stats_cat_filter.set("Všechny kategorie")
            self._update_stats_products_options("Všechny kategorie", preserve_prod="Všechny produkty")

        self._apply_stats_filter()

    def _parse_filter_dates(self):
        from_str = self.date_from_entry.get_date_str()
        to_str = self.date_to_entry.get_date_str()
        d_from = None
        d_to = None

        if from_str:
            try:
                d_from = datetime.strptime(from_str, "%d.%m.%Y").date()
            except ValueError:
                pass

        if to_str:
            try:
                d_to = datetime.strptime(to_str, "%d.%m.%Y").date()
            except ValueError:
                pass

        return d_from, d_to

    def _apply_stats_filter(self):
        mode = self.mode_selector.get()
        d_from, d_to = self._parse_filter_dates()

        if hasattr(self, "stats_top_prod_lbl"):
            self.stats_top_prod_lbl.configure(text="")

        for w in self.table_header_frame.winfo_children():
            w.destroy()
        for w in self.stats_scroll.winfo_children():
            w.destroy()

        if mode == "Prodej zboží":
            self._render_sales_stats(d_from, d_to)
        elif mode == "Doplnění kreditu":
            self._render_credit_stats(d_from, d_to)
        elif mode == "Doplnění zboží":
            self._render_stock_stats(d_from, d_to)

    def _is_date_in_range(self, dt_val: datetime, d_from, d_to):
        if not dt_val:
            return True
        r_date = dt_val.date()
        if d_from and r_date < d_from:
            return False
        if d_to and r_date > d_to:
            return False
        return True

    def _parse_timestamp(self, record: dict) -> datetime:
        ts = record.get("timestamp")
        if ts:
            try:
                return datetime.fromtimestamp(int(ts))
            except Exception:
                pass
        dt_str = record.get("datetime_str")
        if dt_str:
            try:
                return datetime.strptime(dt_str, "%d.%m.%Y %H:%M:%S")
            except Exception:
                pass
        return datetime.now()

    # --- POHLED 1: PRODEJ ZBOŽÍ ---
    def _render_sales_stats(self, d_from, d_to):
        cat_filter = self.stats_cat_filter.get()
        prod_filter = self.stats_prod_filter.get()
        is_filtered = (cat_filter != "Všechny kategorie" or prod_filter != "Všechny produkty")

        if is_filtered:
            ctk.CTkLabel(self.table_header_frame, text="Číslo obj.", width=95, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 4))
            ctk.CTkLabel(self.table_header_frame, text="Zakoupené zboží", width=230, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)
            ctk.CTkLabel(self.table_header_frame, text="Celkem", width=85, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)
            ctk.CTkLabel(self.table_header_frame, text="Vyfiltrováno", width=105, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)
            ctk.CTkLabel(self.table_header_frame, text="Kdo zakoupil", width=145, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)
            ctk.CTkLabel(self.table_header_frame, text="Vydal", width=100, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)
            ctk.CTkLabel(self.table_header_frame, text="Datum a čas", width=150, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)
        else:
            ctk.CTkLabel(self.table_header_frame, text="Číslo obj.", width=100, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(12, 6))
            ctk.CTkLabel(self.table_header_frame, text="Zakoupené zboží", width=280, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8)
            ctk.CTkLabel(self.table_header_frame, text="Celková částka", width=110, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8)
            ctk.CTkLabel(self.table_header_frame, text="Kdo zakoupil", width=160, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8)
            ctk.CTkLabel(self.table_header_frame, text="Vydal", width=110, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8)
            ctk.CTkLabel(self.table_header_frame, text="Datum a čas", width=160, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8)

        all_orders = Database.get_all_orders()
        all_prods = Database.get_products()
        filtered = []
        total_sum = 0
        total_filtered_sum = 0
        best_sellers = {}  # prod_name -> count

        # Zjistíme mapování názvů produktů na jejich kategorie
        prod_to_cat = {
            p.get("name", "").strip().lower(): p.get("category", "").strip().lower()
            for p in all_prods.values()
            if p.get("name")
        }

        # Zjistíme produkty patřící do vybrané kategorie
        allowed_prods_for_cat = None
        if cat_filter != "Všechny kategorie":
            allowed_prods_for_cat = {
                p.get("name", "").strip().lower() 
                for p in all_prods.values() 
                if p.get("category", "").strip().lower() == cat_filter.lower()
            }

        for oid, ord_data in all_orders.items():
            dt = self._parse_timestamp(ord_data)
            if not self._is_date_in_range(dt, d_from, d_to):
                continue

            items_detail = ord_data.get("items_detail")
            items_str = ord_data.get("items", "")

            # Výpočet vyfiltrované částky a kontrola shody
            order_filtered_amount = 0
            has_matching_item = False

            if items_detail and isinstance(items_detail, list):
                for itm in items_detail:
                    itm_name = itm.get("name", "")
                    itm_cat = itm.get("category", "")
                    itm_cnt = itm.get("count", 1)
                    itm_subtotal = itm.get("subtotal", itm.get("price", 0) * itm_cnt)

                    match_cat = True
                    if cat_filter != "Všechny kategorie":
                        if itm_cat.strip().lower() != cat_filter.strip().lower():
                            if not (allowed_prods_for_cat and itm_name.strip().lower() in allowed_prods_for_cat):
                                match_cat = False

                    match_prod = True
                    if prod_filter != "Všechny produkty":
                        if itm_name.strip().lower() != prod_filter.strip().lower():
                            match_prod = False

                    if match_cat and match_prod:
                        has_matching_item = True
                        order_filtered_amount += itm_subtotal

                    # Počítadlo pro nejprodávanější zboží (pouze položky spadající do vybrané kategorie)
                    if match_cat and itm_name:
                        best_sellers[itm_name] = best_sellers.get(itm_name, 0) + itm_cnt
            else:
                # Zpětná kompatibilita pro starší objednávky bez items_detail (parsování textu)
                raw_parts = [p.strip() for p in items_str.split(",") if p.strip()]
                for p in raw_parts:
                    m = re.match(r"^(\d+)\s*x\s*(.*)$", p, re.IGNORECASE)
                    if m:
                        p_cnt = int(m.group(1))
                        p_name = m.group(2).strip()
                    else:
                        p_cnt = 1
                        p_name = p.strip()

                    p_name_lower = p_name.lower()
                    p_cat = prod_to_cat.get(p_name_lower, "")

                    match_cat = True
                    if cat_filter != "Všechny kategorie":
                        if p_cat != cat_filter.strip().lower():
                            if not (allowed_prods_for_cat and p_name_lower in allowed_prods_for_cat):
                                match_cat = False

                    match_prod = True
                    if prod_filter != "Všechny produkty":
                        if p_name_lower != prod_filter.strip().lower():
                            match_prod = False

                    if match_cat and match_prod:
                        has_matching_item = True

                    if match_cat and p_name:
                        best_sellers[p_name] = best_sellers.get(p_name, 0) + p_cnt

                if has_matching_item:
                    order_filtered_amount = ord_data.get("total", 0)

            # Pokud je zapnutý filtr, musí objednávka obsahovat vyhovující položku
            if is_filtered and not has_matching_item:
                continue

            filtered.append((dt, oid, ord_data, order_filtered_amount))
            total_sum += ord_data.get("total", 0)
            total_filtered_sum += order_filtered_amount

        # Určení a zobrazení nejprodávanějšího zboží
        # Pokud je vybrán konkrétní produkt, nejprodávanější zboží se nezobrazuje (byl by to logicky jen ten vybraný produkt)
        if prod_filter != "Všechny produkty" or not best_sellers:
            self.stats_top_prod_lbl.configure(text="")
        else:
            sorted_sellers = sorted(best_sellers.items(), key=lambda x: x[1], reverse=True)
            if cat_filter == "Všechny kategorie":
                top3 = sorted_sellers[:3]
                top_items_text = ", ".join([f"{name} ({cnt} ks)" for name, cnt in top3])
                self.stats_top_prod_lbl.configure(text=f"TOP 3: {top_items_text}")
            else:
                top1_name, top1_cnt = sorted_sellers[0]
                self.stats_top_prod_lbl.configure(text=f"Nejprodávanější ({cat_filter}): {top1_name} ({top1_cnt} ks)")

        filtered.sort(key=lambda x: x[0], reverse=True)

        if is_filtered:
            self.stats_summary_lbl.configure(
                text=f"Vyfiltrováno: {format_price(total_filtered_sum)} (z celkem {format_price(total_sum)}) | Objednávek: {len(filtered)}"
            )
        else:
            self.stats_summary_lbl.configure(
                text=f"Celková tržba: {format_price(total_sum)} | Objednávek: {len(filtered)}"
            )

        if not filtered:
            ctk.CTkLabel(self.stats_scroll, text="Žádné záznamy odpovídající filtrům.", text_color="#777").pack(pady=40)
            return

        for dt, oid, order, f_amount in filtered:
            row = ctk.CTkFrame(self.stats_scroll, fg_color="#22252b")
            row.pack(fill="x", pady=3, padx=2)

            short_id = f"#{oid[-6:]}" if len(oid) >= 6 else f"#{oid}"
            student_name = order.get("student", "Neznámý")
            chip_uid = order.get("chip_uid", "")
            student_label_str = f"{student_name} ({chip_uid})" if chip_uid else student_name
            completed_by = order.get("completed_by", "—")

            if is_filtered:
                ctk.CTkLabel(row, text=short_id, width=95, anchor="w", font=ctk.CTkFont(size=12, weight="bold"), text_color="#4da6ff").pack(side="left", padx=(10, 4), pady=8)
                ctk.CTkLabel(row, text=order.get("items", ""), width=230, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6)
                ctk.CTkLabel(row, text=format_price(order.get('total', 0)), width=85, anchor="w", text_color="#aaaaaa").pack(side="left", padx=6)
                ctk.CTkLabel(row, text=format_price(f_amount), width=105, anchor="w", font=ctk.CTkFont(weight="bold"), text_color="#4da6ff").pack(side="left", padx=6)
                ctk.CTkLabel(row, text=student_label_str, width=145, anchor="w").pack(side="left", padx=6)
                ctk.CTkLabel(row, text=completed_by, width=100, anchor="w", text_color="#98c379").pack(side="left", padx=6)
                ctk.CTkLabel(row, text=dt.strftime("%d.%m.%Y %H:%M:%S"), width=150, anchor="w", text_color="#aaaaaa").pack(side="left", padx=6)
            else:
                ctk.CTkLabel(row, text=short_id, width=100, anchor="w", font=ctk.CTkFont(size=12, weight="bold"), text_color="#4da6ff").pack(side="left", padx=(12, 6), pady=8)
                ctk.CTkLabel(row, text=order.get("items", ""), width=280, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8)
                ctk.CTkLabel(row, text=format_price(order.get('total', 0)), width=110, anchor="w", text_color="#4da6ff").pack(side="left", padx=8)
                ctk.CTkLabel(row, text=student_label_str, width=160, anchor="w").pack(side="left", padx=8)
                ctk.CTkLabel(row, text=completed_by, width=110, anchor="w", text_color="#98c379").pack(side="left", padx=8)
                ctk.CTkLabel(row, text=dt.strftime("%d.%m.%Y %H:%M:%S"), width=160, anchor="w", text_color="#aaaaaa").pack(side="left", padx=8)

    # --- POHLED 2: DOPLNĚNÍ KREDITU ---
    def _render_credit_stats(self, d_from, d_to):
        ctk.CTkLabel(self.table_header_frame, text="Přidaný kredit", width=160, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=12)
        ctk.CTkLabel(self.table_header_frame, text="Kdo zakoupil / Čip", width=220, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        ctk.CTkLabel(self.table_header_frame, text="Dobil (Účet)", width=130, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        ctk.CTkLabel(self.table_header_frame, text="Datum a čas", width=180, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)

        history = Database.get_credit_history()
        filtered = []
        total_credit = 0

        for hid, rec in history.items():
            dt = self._parse_timestamp(rec)
            if self._is_date_in_range(dt, d_from, d_to):
                filtered.append((dt, rec))
                total_credit += rec.get("amount", 0)

        filtered.sort(key=lambda x: x[0], reverse=True)
        self.stats_summary_lbl.configure(text=f"Celkem dobitý kredit: {total_credit} Kč | Počet dobití: {len(filtered)}")

        if not filtered:
            ctk.CTkLabel(self.stats_scroll, text="Žádné záznamy o dobití kreditu.", text_color="#777").pack(pady=40)
            return

        for dt, rec in filtered:
            row = ctk.CTkFrame(self.stats_scroll, fg_color="#22252b")
            row.pack(fill="x", pady=3, padx=2)

            ctk.CTkLabel(row, text=f"+{rec.get('amount', 0)} Kč", width=160, anchor="w", font=ctk.CTkFont(size=14, weight="bold"), text_color="#28a745").pack(side="left", padx=12, pady=8)
            student_str = f"{rec.get('student', 'Student')} ({rec.get('chip_uid', '')})"
            ctk.CTkLabel(row, text=student_str, width=220, anchor="w").pack(side="left", padx=10)
            created_by = rec.get("created_by", "admin")
            ctk.CTkLabel(row, text=created_by, width=130, anchor="w", text_color="#98c379").pack(side="left", padx=10)
            ctk.CTkLabel(row, text=dt.strftime("%d.%m.%Y %H:%M:%S"), width=180, anchor="w", text_color="#aaaaaa").pack(side="left", padx=10)

    # --- POHLED 3: DOPLNĚNÍ ZBOŽÍ ---
    def _render_stock_stats(self, d_from, d_to):
        ctk.CTkLabel(self.table_header_frame, text="Počet kusů", width=150, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=12)
        ctk.CTkLabel(self.table_header_frame, text="Produkt (Název)", width=260, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        ctk.CTkLabel(self.table_header_frame, text="Naskladnil (Účet)", width=140, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
        ctk.CTkLabel(self.table_header_frame, text="Datum a čas", width=180, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)

        history = Database.get_stock_history()
        all_prods = Database.get_products()
        filtered = []
        total_items = 0

        cat_filter = self.stats_cat_filter.get()
        prod_filter = self.stats_prod_filter.get()

        allowed_prods_for_cat = None
        if cat_filter != "Všechny kategorie":
            allowed_prods_for_cat = {
                p.get("name", "").strip().lower() 
                for p in all_prods.values() 
                if p.get("category", "").strip().lower() == cat_filter.lower()
            }

        for hid, rec in history.items():
            dt = self._parse_timestamp(rec)
            if not self._is_date_in_range(dt, d_from, d_to):
                continue

            p_name = rec.get("product_name", "").strip()

            if prod_filter != "Všechny produkty":
                if p_name.lower() != prod_filter.lower():
                    continue

            if allowed_prods_for_cat is not None:
                if p_name.lower() not in allowed_prods_for_cat:
                    continue

            filtered.append((dt, rec))
            total_items += rec.get("quantity", 0)

        filtered.sort(key=lambda x: x[0], reverse=True)
        self.stats_summary_lbl.configure(text=f"Celkem naskladněno: {total_items} ks | Záznamů: {len(filtered)}")

        if not filtered:
            ctk.CTkLabel(self.stats_scroll, text="Žádné záznamy o doplnění skladu odpovídající filtrům.", text_color="#777").pack(pady=40)
            return

        for dt, rec in filtered:
            row = ctk.CTkFrame(self.stats_scroll, fg_color="#22252b")
            row.pack(fill="x", pady=3, padx=2)

            ctk.CTkLabel(row, text=f"+{rec.get('quantity', 0)} ks", width=150, anchor="w", font=ctk.CTkFont(size=14, weight="bold"), text_color="#4da6ff").pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(row, text=rec.get("product_name", "Neznámý produkt"), width=260, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
            created_by = rec.get("created_by", "admin")
            ctk.CTkLabel(row, text=created_by, width=140, anchor="w", text_color="#98c379").pack(side="left", padx=10)
            ctk.CTkLabel(row, text=dt.strftime("%d.%m.%Y %H:%M:%S"), width=180, anchor="w", text_color="#aaaaaa").pack(side="left", padx=10)

    # --- EXPORT VŠECH HISTORICKÝCH DAT DO CSV ---
    def _export_all_to_csv(self):
        default_filename = f"kantyna_kompletni_export_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.csv"
        file_path = filedialog.asksaveasfilename(
            title="Uložit export všech dat do CSV",
            initialfile=default_filename,
            defaultextension=".csv",
            filetypes=[("CSV soubory (*.csv)", "*.csv"), ("Všechny soubory (*.*)", "*.*")]
        )
        if not file_path:
            return

        try:
            all_orders = Database.get_all_orders()
            credit_history = Database.get_credit_history()
            stock_history = Database.get_stock_history()

            # Seřazení záznamů od nejnovějších
            orders_list = []
            for oid, o in all_orders.items():
                dt = self._parse_timestamp(o)
                orders_list.append((dt, oid, o))
            orders_list.sort(key=lambda x: x[0], reverse=True)

            credit_list = []
            for cid, c in credit_history.items():
                dt = self._parse_timestamp(c)
                credit_list.append((dt, cid, c))
            credit_list.sort(key=lambda x: x[0], reverse=True)

            stock_list = []
            for sid, s in stock_history.items():
                dt = self._parse_timestamp(s)
                stock_list.append((dt, sid, s))
            stock_list.sort(key=lambda x: x[0], reverse=True)

            with open(file_path, "w", newline="", encoding="utf-8-sig") as csvfile:
                writer = csv.writer(csvfile, delimiter=";")

                # HLAVIČKA SOUBORU
                writer.writerow(["KOMPLETNÍ EXPORT DAT - ŠKOLNÍ KANTÝNA"])
                writer.writerow(["Datum a čas exportu", datetime.now().strftime("%d.%m.%Y %H:%M:%S")])
                writer.writerow(["Exportoval", f"{self.current_user.get('name', 'Pokladní')} ({self.current_user.get('role', 'obsluha')})"])
                writer.writerow([])

                # SEKCE 1: HISTORIE OBJEDNÁVEK (PRODEJ ZBOŽÍ)
                writer.writerow(["=== 1. HISTORIE PRODEJE ZBOŽÍ (OBJEDNÁVKY) ==="])
                writer.writerow(["Datum a čas", "Číslo objednávky", "Zákazník", "Čip UID", "Zakoupené položky", "Celková částka (Kč)", "Stav", "Vydal (Účet)"])
                total_sales_sum = 0
                for dt, oid, o in orders_list:
                    tot = o.get("total", 0)
                    total_sales_sum += tot
                    writer.writerow([
                        dt.strftime("%d.%m.%Y %H:%M:%S"),
                        oid[-8:],
                        o.get("student", "Neznámý"),
                        o.get("chip_uid", ""),
                        o.get("items", ""),
                        format_price(tot),
                        "Vydáno" if o.get("status") == "completed" else "Čekající",
                        o.get("completed_by", "—")
                    ])
                writer.writerow(["SOUHRN", f"Celkem objednávek: {len(orders_list)}", "", "", "", f"Celková tržba: {format_price(total_sales_sum)}", "", ""])
                writer.writerow([])
                writer.writerow([])

                # SEKCE 2: HISTORIE DOBÍJENÍ KREDITU
                writer.writerow(["=== 2. HISTORIE DOBÍJENÍ KREDITU ==="])
                writer.writerow(["Datum a čas", "Zákazník", "Čip UID", "Dobitá částka (Kč)", "Dobil (Účet)"])
                total_credit_sum = 0
                for dt, cid, c in credit_list:
                    amt = c.get("amount", 0)
                    total_credit_sum += amt
                    writer.writerow([
                        dt.strftime("%d.%m.%Y %H:%M:%S"),
                        c.get("student", "Neznámý"),
                        c.get("chip_uid", ""),
                        f"+{format_price(amt)}",
                        c.get("created_by", "admin")
                    ])
                writer.writerow(["SOUHRN", f"Celkem dobití: {len(credit_list)}", "", f"Celkem dobito: {format_price(total_credit_sum)}", ""])
                writer.writerow([])
                writer.writerow([])

                # SEKCE 3: HISTORIE DOPLŇOVÁNÍ SKLADU
                writer.writerow(["=== 3. HISTORIE DOPLŇOVÁNÍ SKLADU ==="])
                writer.writerow(["Datum a čas", "Produkt", "Doplněný počet kusů", "Naskladnil (Účet)"])
                total_stock_count = 0
                for dt, sid, s in stock_list:
                    qty = s.get("quantity", 0)
                    total_stock_count += qty
                    writer.writerow([
                        dt.strftime("%d.%m.%Y %H:%M:%S"),
                        s.get("product_name", "Neznámý"),
                        f"+{qty} ks",
                        s.get("created_by", "admin")
                    ])
                writer.writerow(["SOUHRN", f"Celkem naskladnění: {len(stock_list)}", f"Celkem kusů: {total_stock_count} ks", ""])

            messagebox.showinfo(
                "Export dokončen",
                f"Všechna data byla úspěšně vyexportována do souboru:\n{file_path}"
            )
        except Exception as e:
            messagebox.showerror(
                "Chyba při exportu",
                f"Při ukládání souboru došlo k chybě:\n{e}"
            )

    # --- SYNCHRONIZACE S CLOUDEM ---
    def _refresh_all_data(self):
        self.products = Database.get_products()
        self.orders = Database.get_active_orders()
        self._render_stock_list()
        self._render_orders()

    def _start_background_sync(self):
        self._sync_thread_running = True
        def loop():
            while self._sync_thread_running:
                time.sleep(2)
                try:
                    if not self._sync_thread_running:
                        break
                    new_orders = Database.get_active_orders()
                    if new_orders != self.orders:
                        self.orders = new_orders
                        self.after(0, self._render_orders)
                except Exception:
                    pass
        threading.Thread(target=loop, daemon=True).start()

if __name__ == "__main__":
    app = CashierApp()
    app.mainloop()

