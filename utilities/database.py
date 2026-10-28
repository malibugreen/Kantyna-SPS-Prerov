import requests
import json
import certifi
import urllib3
import time
import hashlib
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FIREBASE_URL = "https://sps-prerov-kantyna-kiosk-default-rtdb.europe-west1.firebasedatabase.app"

session = requests.Session()
try:
    session.verify = certifi.where()
except Exception:
    session.verify = False

def _req(method, url, **kwargs):
    """Pomocná funkce pro bezpečné odeslání HTTP požadavku."""
    kwargs.setdefault("timeout", 5)
    try:
        return session.request(method, url, **kwargs)
    except requests.exceptions.SSLError:
        session.verify = False
        return session.request(method, url, **kwargs)

class Database:
    @staticmethod
    def _url(endpoint: str) -> str:
        return f"{FIREBASE_URL}/{endpoint}.json"

    # --- ZBOŽÍ & SKLAD ---
    @staticmethod
    def get_products():
        """Vrátí slovník všech produktů."""
        try:
            res = _req("GET", Database._url("products"))
            data = res.json()
            if not data:
                return {}
            if isinstance(data, list):
                return {str(i): item for i, item in enumerate(data) if item is not None}
            return data
        except Exception as e:
            print(f"Chyba při stahování produktů: {e}")
            return {}

    @staticmethod
    def save_product(product_id: str, data: dict):
        """Uloží nebo aktualizuje jeden produkt."""
        try:
            _req("PUT", Database._url(f"products/{product_id}"), json=data)
            return True
        except Exception as e:
            print(f"Chyba při ukládání produktu {product_id}: {e}")
            return False

    @staticmethod
    def update_stock(product_id: str, new_stock: int):
        """Aktualizuje pouze počet kusů skladem."""
        try:
            _req("PATCH", Database._url(f"products/{product_id}"), json={"stock": new_stock})
            return True
        except Exception as e:
            print(f"Chyba při změně skladu: {e}")
            return False

    @staticmethod
    def delete_product(product_id: str):
        """Smaže produkt z Firebase."""
        try:
            _req("DELETE", Database._url(f"products/{product_id}"))
            return True
        except Exception as e:
            print(f"Chyba při mazání produktu {product_id}: {e}")
            return False

    # --- UŽIVATELÉ & ČIPY ---
    @staticmethod
    def get_user_by_chip(chip_uid: str):
        """Vrátí data uživatele podle UID čipu."""
        try:
            res = _req("GET", Database._url(f"users/{chip_uid}"))
            return res.json()
        except Exception as e:
            print(f"Chyba při načítání uživatele: {e}")
            return None

    @staticmethod
    def update_user_balance(chip_uid: str, new_balance: int, name: str = None):
        """Aktualizuje kredit uživatele."""
        try:
            data = {"balance": new_balance}
            if name:
                data["name"] = name
            _req("PATCH", Database._url(f"users/{chip_uid}"), json=data)
            return True
        except Exception as e:
            print(f"Chyba při změně kreditu: {e}")
            return False

    # --- OBJEDNÁVKY ---
    @staticmethod
    def get_active_orders():
        """Vrátí aktivní objednávky čekající na výdej."""
        try:
            res = _req("GET", Database._url("orders"))
            data = res.json()
            if not data:
                return {}
            return {k: v for k, v in data.items() if isinstance(v, dict) and v.get("status") == "pending"}
        except Exception as e:
            print(f"Chyba při načítání objednávek: {e}")
            return {}

    @staticmethod
    def create_order(order_data: dict):
        """Vytvoří novou objednávku ve Firebase."""
        try:
            res = _req("POST", Database._url("orders"), json=order_data)
            return res.json().get("name")
        except Exception as e:
            print(f"Chyba při vytváření objednávky: {e}")
            return None

    @staticmethod
    def complete_order(order_id: str, cashier_user: str = "obsluha"):
        """Označí objednávku za dokončenou/vydanou."""
        try:
            _req("PATCH", Database._url(f"orders/{order_id}"), json={
                "status": "completed",
                "completed_by": cashier_user
            })
            return True
        except Exception as e:
            print(f"Chyba při dokončování objednávky: {e}")
            return False

    # --- HISTORIE & STATISTIKY ---
    @staticmethod
    def log_credit_topup(chip_uid: str, student_name: str, amount: int, cashier_user: str = "admin"):
        """Zaznamená dobití kreditu do historie."""
        try:
            record = {
                "chip_uid": chip_uid,
                "student": student_name,
                "amount": amount,
                "created_by": cashier_user,
                "timestamp": int(time.time()),
                "datetime_str": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            }
            _req("POST", Database._url("credit_history"), json=record)
            return True
        except Exception as e:
            print(f"Chyba při logování kreditu: {e}")
            return False

    @staticmethod
    def get_credit_history():
        """Vrátí všechny záznamy o dobití kreditu."""
        try:
            res = _req("GET", Database._url("credit_history"))
            data = res.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def log_stock_replenishment(product_name: str, added_quantity: int, cashier_user: str = "admin"):
        """Zaznamená naskladnění zboží do historie."""
        try:
            record = {
                "product_name": product_name,
                "quantity": added_quantity,
                "created_by": cashier_user,
                "timestamp": int(time.time()),
                "datetime_str": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            }
            _req("POST", Database._url("stock_history"), json=record)
            return True
        except Exception as e:
            print(f"Chyba při logování skladu: {e}")
            return False

    @staticmethod
    def get_stock_history():
        """Vrátí všechny záznamy o naskladnění zboží."""
        try:
            res = _req("GET", Database._url("stock_history"))
            data = res.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def get_all_orders():
        """Vrátí veškeré objednávky pro statistiky."""
        try:
            res = _req("GET", Database._url("orders"))
            data = res.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # --- POKLADNÍ & PŘIHLAŠOVÁNÍ ---
    @staticmethod
    def hash_password(password: str) -> str:
        """Zahašuje heslo pomocí SHA-256."""
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_cashier_login(username: str, password: str) -> dict | None:
        """
        Ověří přihlašovací údaje pokladní.
        Vrátí slovník s údaji pokladní nebo None při neúspěchu.
        """
        try:
            uname = username.strip().lower()
            res = _req("GET", Database._url(f"cashiers/{uname}"))
            user_data = res.json()
            if not user_data:
                return None

            pwd_hash = Database.hash_password(password)
            if user_data.get("password_hash") == pwd_hash:
                return user_data
            return None
        except Exception as e:
            print(f"Chyba při ověřování pokladní: {e}")
            return None

    @staticmethod
    def create_cashier(username: str, password: str, display_name: str, role: str = "pokladni"):
        """Vytvoří nového uživatele pokladny s hašovaným heslem."""
        try:
            uname = username.strip().lower()
            data = {
                "name": display_name,
                "password_hash": Database.hash_password(password),
                "role": role
            }
            _req("PUT", Database._url(f"cashiers/{uname}"), json=data)
            return True
        except Exception as e:
            print(f"Chyba při zakládání pokladní: {e}")
            return False

    # --- KATEGORIE ---
    @staticmethod
    def get_categories():
        """Vrátí seznam všech dostupných kategorií."""
        try:
            res = _req("GET", Database._url("categories"))
            data = res.json()
            if not data:
                return ["Slané", "Sladké", "Nápoje"]
            if isinstance(data, list):
                return [c for c in data if c]
            if isinstance(data, dict):
                return list(data.values())
            return ["Slané", "Sladké", "Nápoje"]
        except Exception:
            return ["Slané", "Sladké", "Nápoje"]

    @staticmethod
    def add_category(category_name: str):
        """Přidá novou kategorii do Firebase, pokud ještě neexistuje."""
        try:
            cat = category_name.strip()
            if not cat:
                return False
            current = Database.get_categories()
            if any(c.lower() == cat.lower() for c in current):
                return True
            current.append(cat)
            _req("PUT", Database._url("categories"), json=current)
            return True
        except Exception as e:
            print(f"Chyba při ukládání kategorie: {e}")
            return False

    @staticmethod
    def delete_category(category_name: str):
        """Smaže kategorii ze seznamu kategorií ve Firebase."""
        try:
            current = Database.get_categories()
            new_list = [c for c in current if c.lower() != category_name.strip().lower()]
            _req("PUT", Database._url("categories"), json=new_list)
            return True
        except Exception as e:
            print(f"Chyba při mazání kategorie: {e}")
            return False

    @staticmethod
    def rename_category(old_name: str, new_name: str):
        """Přejmenuje kategorii v seznamu a aktualizuje i všechny produkty s touto kategorií."""
        try:
            old_n = old_name.strip()
            new_n = new_name.strip()
            if not new_n:
                return False

            # 1. Přejmenování v categories
            current = Database.get_categories()
            updated_list = []
            for c in current:
                if c.lower() == old_n.lower():
                    updated_list.append(new_n)
                else:
                    updated_list.append(c)
            _req("PUT", Database._url("categories"), json=updated_list)

            # 2. Přejmenování u existujících produktů
            prods = Database.get_products()
            for pid, prod in prods.items():
                if prod.get("category", "").strip().lower() == old_n.lower():
                    _req("PATCH", Database._url(f"products/{pid}"), json={"category": new_n})

            return True
        except Exception as e:
            print(f"Chyba při přejmenování kategorie: {e}")
            return False

    # --- INICIALIZACE VÝCHOZÍCH DAT ---
    @staticmethod
    def init_default_data():
        """Nahraje počáteční data do Firebase, pokud je prázdná."""
        current_prods = Database.get_products()
        if not current_prods:
            default_products = {
                "prod_sunkova_bageta": {"name": "Šunková bageta", "price": 45, "stock": 10, "category": "Slané"},
                "prod_kureci_tortilla": {"name": "Kuřecí tortilla", "price": 55, "stock": 6, "category": "Slané"},
                "prod_cokoladovy_donut": {"name": "Čokoládový donut", "price": 28, "stock": 5, "category": "Sladké"},
                "prod_croissant_s_maslem": {"name": "Croissant s máslem", "price": 25, "stock": 12, "category": "Sladké"},
                "prod_mineralka_mattoni": {"name": "Minerálka Mattoni 0.5l", "price": 20, "stock": 15, "category": "Nápoje"},
                "prod_kofola_plech": {"name": "Kofola plech 0.33l", "price": 26, "stock": 10, "category": "Nápoje"},
            }
            _req("PUT", Database._url("products"), json=default_products)

        # Inicializace výchozích kategorií
        res_cats = _req("GET", Database._url("categories"))
        if not res_cats.json():
            default_cats = ["Slané", "Sladké", "Nápoje"]
            _req("PUT", Database._url("categories"), json=default_cats)

        student = Database.get_user_by_chip("UID_12345")
        if not student:
            Database.update_user_balance("UID_12345", 250, name="Jan Novák")

        # Výchozí účet pokladní (admin / kantyna123)
        res = _req("GET", Database._url("cashiers/admin"))
        if not res.json():
            Database.create_cashier("admin", "kantyna123", "Hlavní pokladní", role="admin")
            print("Výchozí účet pokladní 'admin' vytvořen!")
