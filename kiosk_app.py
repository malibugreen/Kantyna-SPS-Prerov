import customtkinter as ctk
import threading
import time
from datetime import datetime
from utilities.database import Database
from utilities.image_utils import load_ctk_image
from utilities.rfid_hardware import RFIDHardwareReader

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def format_price(val, with_currency: bool = True) -> str:
    """Naformátuje číslo/cenu do českého tvaru s desetinnou čárkou (např. 45,90 Kč nebo 45 Kč)."""
    if val is None or val == "":
        return "0,00 Kč" if with_currency else "0,00"
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return f"{val} Kč" if with_currency else str(val)

    if abs(f_val - round(f_val)) > 1e-6:
        formatted = f"{f_val:.2f}".replace(".", ",")
    else:
        formatted = f"{int(round(f_val))}"

    return f"{formatted} Kč" if with_currency else formatted

class KioskApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Školní Kantýna - Objednávkový Kiosek")
        self.geometry("1150x720")
        self.minsize(950, 600)

        self.products = {}      # dict {pid: {name, price, stock, icon, image_path, category, ...}}
        self.cart = {}          # {pid: count}
        self.user_chip = None
        self.user_data = None
        self.selected_category = "Vše"
        self._image_cache = {}  # Cache pro CTkImage

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_catalog_panel()
        self._build_sidebar()

        # Prvotní načtení dat
        self._refresh_products_from_db()

        # Pravidelná aktualizace skladu z Firebase na pozadí (každé 3 sekundy)
        self._start_background_sync()

        # Inicializace a spuštění čtečky RFID čipů (Freenove RC522)
        self.rfid_reader = RFIDHardwareReader(on_chip_scanned_callback=self._on_hardware_chip_scanned)
        self.rfid_reader.start_listening()

    def _build_catalog_panel(self):
        self.catalog_frame = ctk.CTkFrame(self, corner_radius=15)
        self.catalog_frame.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")

        title_frame = ctk.CTkFrame(self.catalog_frame, fg_color="transparent")
        title_frame.pack(fill="x", padx=20, pady=(15, 6))

        title_label = ctk.CTkLabel(
            title_frame, 
            text="Vyberte si z nabídky", 
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(side="left")

        self.sync_label = ctk.CTkLabel(title_frame, text="Online (Firebase)", text_color="#28a745", font=ctk.CTkFont(size=12))
        self.sync_label.pack(side="right")

        # Lišta kategorií (přepínací tlačítka)
        self.category_bar = ctk.CTkScrollableFrame(self.catalog_frame, height=45, orientation="horizontal", fg_color="transparent")
        self.category_bar.pack(fill="x", padx=15, pady=(0, 10))

        self._render_category_bar()

        self.scroll_products = ctk.CTkScrollableFrame(self.catalog_frame, corner_radius=10)
        self.scroll_products.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.scroll_products.grid_columnconfigure((0, 1, 2), weight=1)

    def _render_category_bar(self):
        for w in self.category_bar.winfo_children():
            w.destroy()

        # Zjistíme unikátní kategorie, které aktuálně používá alespoň jeden produkt
        active_cats = set()
        for prod in self.products.values():
            cat = prod.get("category", "").strip()
            if cat:
                active_cats.add(cat)

        # Seřadíme je podle definovaného pořadí v databázi, případně abecedně
        db_cats = Database.get_categories()
        ordered_cats = [c for c in db_cats if c in active_cats]
        # Pokud by nějaký produkt měl kategorii mimo db_cats, přidáme ji také
        for c in sorted(active_cats):
            if c not in ordered_cats:
                ordered_cats.append(c)

        # Výsledný seznam tlačítek: Vše + pouze ty aktivně používané
        categories = ["Vše"] + ordered_cats

        # Pokud dříve vybraná kategorie už mezi aktivními není, přepneme na Vše
        if self.selected_category not in categories:
            self.selected_category = "Vše"

        for cat in categories:
            is_active = (cat == self.selected_category)
            btn = ctk.CTkButton(
                self.category_bar,
                text=cat,
                width=100,
                height=32,
                corner_radius=16,
                fg_color="#1f6aa5" if is_active else "#2b2b2b",
                hover_color="#144870" if is_active else "#3a3a3a",
                font=ctk.CTkFont(size=13, weight="bold" if is_active else "normal"),
                command=lambda c=cat: self._set_category(c)
            )
            btn.pack(side="left", padx=4, pady=2)

    def _set_category(self, cat):
        self.selected_category = cat
        self._render_category_bar()
        self._render_catalog()

    def _render_catalog(self):
        for w in self.scroll_products.winfo_children():
            w.destroy()
        self._image_cache.clear()

        # Filtrování podle zvolené kategorie
        filtered_products = {}
        for pid, item in self.products.items():
            if self.selected_category == "Vše" or item.get("category") == self.selected_category:
                filtered_products[pid] = item

        if not filtered_products:
            lbl_empty = ctk.CTkLabel(
                self.scroll_products,
                text=f"V kategorii '{self.selected_category}' zatím není žádné zboží.",
                font=ctk.CTkFont(size=15),
                text_color="#888"
            )
            lbl_empty.pack(pady=50)
            return

        row = 0
        col = 0
        for pid, item in filtered_products.items():
            stock = item.get("stock", 0)
            is_available = stock > 0
            card = ctk.CTkFrame(
                self.scroll_products, 
                corner_radius=12,
                fg_color="#2b2b2b" if is_available else "#1c1c1c"
            )
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

            # Fotka (čtverec 1:1, velikost 110x110)
            ctk_img = load_ctk_image(item, (110, 110))
            if ctk_img:
                self._image_cache[pid] = ctk_img
                img_lbl = ctk.CTkLabel(card, text="", image=ctk_img)
                img_lbl.pack(pady=(12, 6))
            else:
                img_lbl = ctk.CTkLabel(card, text="[Bez fotky]", font=ctk.CTkFont(size=14), text_color="#777")
                img_lbl.pack(pady=(45, 45))

            name_label = ctk.CTkLabel(card, text=item.get("name", "Produkt"), font=ctk.CTkFont(size=15, weight="bold"), wraplength=170)
            name_label.pack(padx=10, pady=2)

            price_label = ctk.CTkLabel(card, text=format_price(item.get('price', 0)), font=ctk.CTkFont(size=14, weight="bold"), text_color="#4da6ff")
            price_label.pack(pady=2)

            # Sklad
            if not is_available:
                stock_text = "VYPRODÁNO"
                stock_color = "#e57373"
            elif 1 <= stock <= 5:
                stock_text = f"Poslední kusy: {stock} ks"
                stock_color = "#f0ad4e"
            else:
                stock_text = f"Skladem: {stock} ks"
                stock_color = "#888888"

            stock_label = ctk.CTkLabel(card, text=stock_text, font=ctk.CTkFont(size=12), text_color=stock_color)
            stock_label.pack(pady=2)

            btn = ctk.CTkButton(
                card, 
                text="Přidat" if is_available else "Nedostupné",
                state="normal" if is_available else "disabled",
                fg_color="#1f6aa5" if is_available else "#444444",
                command=lambda p_id=pid: self._add_to_cart(p_id)
            )
            btn.pack(padx=15, pady=(8, 12), fill="x")

            col += 1
            if col > 2:
                col = 0
                row += 1

    def _build_sidebar(self):
        self.side_frame = ctk.CTkFrame(self, corner_radius=15)
        self.side_frame.grid(row=0, column=1, padx=(0, 15), pady=15, sticky="nsew")

        # Sekce čip
        self.chip_frame = ctk.CTkFrame(self.side_frame, fg_color="#1e2229", corner_radius=10)
        self.chip_frame.pack(fill="x", padx=15, pady=15)

        self.chip_status_label = ctk.CTkLabel(
            self.chip_frame, 
            text="Přiložte svůj čip...", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#f0ad4e"
        )
        self.chip_status_label.pack(pady=(12, 4))

        self.balance_label = ctk.CTkLabel(self.chip_frame, text="Zůstatek: -- Kč", font=ctk.CTkFont(size=14))
        self.balance_label.pack(pady=(0, 12))

        # Košík
        cart_title = ctk.CTkLabel(self.side_frame, text="Váš Košík", font=ctk.CTkFont(size=18, weight="bold"))
        cart_title.pack(anchor="w", padx=15, pady=(10, 5))

        self.cart_scroll = ctk.CTkScrollableFrame(self.side_frame, height=250)
        self.cart_scroll.pack(fill="both", expand=True, padx=15, pady=5)

        self.empty_cart_label = ctk.CTkLabel(self.cart_scroll, text="Košík je prázdný", text_color="#777777")
        self.empty_cart_label.pack(pady=30)

        self.total_label = ctk.CTkLabel(self.side_frame, text="Celkem: 0 Kč", font=ctk.CTkFont(size=20, weight="bold"), text_color="#4da6ff")
        self.total_label.pack(pady=10)

        self.order_btn = ctk.CTkButton(
            self.side_frame, 
            text="Objednat a zaplatit", 
            height=45,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#28a745",
            hover_color="#218838",
            command=self._submit_order
        )
        self.order_btn.pack(fill="x", padx=15, pady=(0, 8))

        self.clear_btn = ctk.CTkButton(
            self.side_frame, 
            text="Vysypat košík", 
            height=30,
            fg_color="#dc3545",
            hover_color="#c82333",
            command=self._clear_cart
        )
        self.clear_btn.pack(fill="x", padx=15, pady=(0, 15))

    def _refresh_products_from_db(self):
        new_prods = Database.get_products()
        if new_prods:
            self.products = new_prods
            self._render_category_bar()
            self._render_catalog()

    def _start_background_sync(self):
        def loop():
            while True:
                time.sleep(3)
                try:
                    new_prods = Database.get_products()
                    if new_prods and new_prods != self.products:
                        self.products = new_prods
                        self.after(0, self._render_category_bar)
                        self.after(0, self._render_catalog)

                    if self.user_chip:
                        user = Database.get_user_by_chip(self.user_chip)
                        if user and user.get("balance") != self.user_data.get("balance"):
                            self.user_data = user
                            self.after(0, lambda u=user: self.balance_label.configure(text=f"Zůstatek: {format_price(u.get('balance', 0))}"))
                except Exception:
                    pass
        threading.Thread(target=loop, daemon=True).start()

    def _on_hardware_chip_scanned(self, chip_uid: str):
        """Voláno na pozadí při fyzickém přiložení čipu k RFID čtečce."""
        self.after(0, lambda: self._process_scanned_chip(chip_uid))

    def _process_scanned_chip(self, chip_id: str):
        RFIDHardwareReader.beep_success()
        user = Database.get_user_by_chip(chip_id)
        if user:
            self.user_chip = chip_id
            self.user_data = user
            name = user.get("name", "Student")
            balance = user.get("balance", 0)
            self.chip_status_label.configure(text=f"Přihlášen: {name}", text_color="#28a745")
            self.balance_label.configure(text=f"Zůstatek: {format_price(balance)}", text_color="#ffffff")
        else:
            self.chip_status_label.configure(text=f"Neznámý čip ({chip_id[:8]})", text_color="#e06c75")

    def _add_to_cart(self, pid):
        product = self.products.get(pid)
        if not product:
            return
        curr_in_cart = self.cart.get(pid, 0)
        if curr_in_cart < product.get("stock", 0):
            self.cart[pid] = curr_in_cart + 1
            self._update_cart_ui()

    def _clear_cart(self):
        self.cart.clear()
        self._update_cart_ui()

    def _update_cart_ui(self):
        for w in self.cart_scroll.winfo_children():
            w.destroy()

        if not self.cart:
            self.empty_cart_label = ctk.CTkLabel(self.cart_scroll, text="Košík je prázdný", text_color="#777777")
            self.empty_cart_label.pack(pady=30)
            self.total_label.configure(text="Celkem: 0 Kč")
            return

        total = 0.0
        for pid, count in self.cart.items():
            product = self.products.get(pid, {})
            price = round(float(product.get("price", 0)), 2)
            subtotal = round(price * count, 2)
            total += subtotal

            row = ctk.CTkFrame(self.cart_scroll, fg_color="#252525", corner_radius=6)
            row.pack(fill="x", pady=3, padx=2)

            info = f"{product.get('name', 'Položka')}\n{count}x {format_price(price)} = {format_price(subtotal)}"
            lbl = ctk.CTkLabel(row, text=info, justify="left", font=ctk.CTkFont(size=12))
            lbl.pack(side="left", padx=8, pady=4)

        total = round(total, 2)
        self.total_label.configure(text=f"Celkem: {format_price(total)}")

    def _submit_order(self):
        if not self.cart:
            return
        if not self.user_chip:
            self.chip_status_label.configure(text="⚠️ Nejdříve přiložte čip!", text_color="#e06c75")
            return

        total = round(sum(float(self.products[pid].get("price", 0)) * count for pid, count in self.cart.items() if pid in self.products), 2)
        user_balance = round(float(self.user_data.get("balance", 0)), 2)

        if user_balance < total:
            self.balance_label.configure(text=f"Nedostatek kreditu! ({format_price(user_balance)})", text_color="#e06c75")
            return

        new_balance = round(user_balance - total, 2)
        Database.update_user_balance(self.user_chip, new_balance)
        self.user_data["balance"] = new_balance

        order_items_text = []
        items_detail = []
        for pid, count in self.cart.items():
            prod = self.products[pid]
            p_name = prod.get("name", "Produkt")
            p_price = round(float(prod.get("price", 0)), 2)
            p_cat = prod.get("category", "Slané")
            p_subtotal = round(p_price * count, 2)

            new_stock = max(0, prod.get("stock", 0) - count)
            Database.update_stock(pid, new_stock)
            self.products[pid]["stock"] = new_stock

            order_items_text.append(f"{count}x {p_name}")
            items_detail.append({
                "product_id": pid,
                "name": p_name,
                "count": count,
                "price": p_price,
                "category": p_cat,
                "subtotal": p_subtotal
            })

        now = datetime.now()
        order_data = {
            "chip_uid": self.user_chip,
            "student": self.user_data.get("name", "Student"),
            "items": ", ".join(order_items_text),
            "items_detail": items_detail,
            "total": total,
            "status": "pending",
            "timestamp": int(now.timestamp()),
            "datetime_str": now.strftime("%d.%m.%Y %H:%M:%S")
        }
        Database.create_order(order_data)

        self.balance_label.configure(text=f"Zůstatek: {format_price(new_balance)}", text_color="#ffffff")
        self.chip_status_label.configure(text="Objednávka odeslána!", text_color="#28a745")
        self.cart.clear()
        self._update_cart_ui()
        self._render_category_bar()
        self._render_catalog()

if __name__ == "__main__":
    app = KioskApp()
    app.mainloop()
