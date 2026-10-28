import os
import base64
import io
import unicodedata
import re
from PIL import Image, ImageDraw
import customtkinter as ctk

# Cesta k hlavní kořenové složce projektu (rodič složky utilities)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES_DIR = os.path.join(BASE_DIR, "product_images")
os.makedirs(IMAGES_DIR, exist_ok=True)

def sanitize_filename(name: str) -> str:
    """
    Převede název na bezpečný název souboru bez diakritiky,
    malými písmeny a s podtržítky místo mezer.
    Např.: "Šunková bageta 0.5l" -> "sunkova_bageta_0_5l"
    """
    nfkd = unicodedata.normalize('NFKD', name)
    clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = clean.lower().strip()
    clean = re.sub(r'[^a-z0-9]+', '_', clean)
    clean = clean.strip('_')
    return clean or "produkt"

def apply_rounded_corners(img: Image.Image, radius_ratio: float = 0.12) -> Image.Image:
    """
    Zaoblí rohy obrázku s vyhlazením hran (anti-aliasing) pomocí masky.
    """
    img = img.convert("RGBA")
    w, h = img.size
    radius = int(min(w, h) * radius_ratio)

    scale = 4
    mask = Image.new("L", (w * scale, h * scale), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, w * scale, h * scale), radius=radius * scale, fill=255)
    mask = mask.resize((w, h), Image.Resampling.LANCZOS)

    img.putalpha(mask)
    return img

def crop_and_resize_square(image_path: str, size: int = 250) -> Image.Image:
    """Ořeže obrázek na poměr 1:1 (střed), zmenší a zaoblí rohy."""
    with Image.open(image_path) as img:
        img = img.convert("RGBA")
        w, h = img.size
        min_dim = min(w, h)

        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        right = left + min_dim
        bottom = top + min_dim
        cropped = img.crop((left, top, right, bottom))
        resized = cropped.resize((size, size), Image.Resampling.LANCZOS)
        return apply_rounded_corners(resized, radius_ratio=0.14)

def process_and_save_product_image(source_path: str, product_name: str) -> tuple[str, str]:
    """
    Zpracuje vybraný obrázek:
    1. Vytvoří název souboru z názvu produktu (bez diakritiky s podtržítky).
    2. Uloží ořezaný a zaoblený čtverec 250x250 px do složky product_images.
    3. Vrátí (relativní_cesta, base64_řetězec) pro ukládání do DB.
    """
    img_square = crop_and_resize_square(source_path, size=250)
    safe_name = sanitize_filename(product_name)
    filename = f"{safe_name}.png"
    target_path = os.path.join(IMAGES_DIR, filename)
    img_square.save(target_path, format="PNG", optimize=True)

    buffer = io.BytesIO()
    img_square.save(buffer, format="PNG", optimize=True)
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return f"product_images/{filename}", b64_str

def load_ctk_image(item_data: dict, display_size: tuple[int, int]) -> ctk.CTkImage | None:
    """
    Načte obrázek jako CTkImage se zaoblenými rohy.
    """
    local_rel = item_data.get("image_path")
    pil_img = None

    if local_rel:
        full_path = os.path.join(BASE_DIR, local_rel)
        if os.path.exists(full_path):
            try:
                pil_img = Image.open(full_path)
            except Exception:
                pass

    if pil_img is None:
        b64_str = item_data.get("image_base64")
        if b64_str:
            try:
                raw_data = base64.b64decode(b64_str)
                pil_img = Image.open(io.BytesIO(raw_data))
                target_rel = local_rel or f"product_images/{sanitize_filename(item_data.get('name', 'item'))}.png"
                save_p = os.path.join(BASE_DIR, target_rel)
                pil_img.save(save_p, format="PNG")
            except Exception:
                pass

    if pil_img:
        pil_img = apply_rounded_corners(pil_img, radius_ratio=0.14)
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=display_size)

    return None

def create_badge_image(count: int, diameter: int = 18) -> ctk.CTkImage:
    """
    Vygeneruje dokonale kulatý červený odznak s bílým číslem
    a 100% průhledným pozadím (žádné černé rohy ani rámečky).
    """
    scale = 4
    size = diameter * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Červený vyhlazený kruh (#dc3545)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(220, 53, 69, 255))

    # Zmenšení pro dokonalé vyhlazení hran (anti-aliasing)
    img = img.resize((diameter, diameter), Image.Resampling.LANCZOS)
    draw_small = ImageDraw.Draw(img)

    # Vykreslení čísla doprostřed
    text = str(count)
    # Zjednodušené centrování
    bbox = draw_small.textbbox((0, 0), text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (diameter - tw) / 2
    ty = (diameter - th) / 2 - 1

    draw_small.text((tx, ty), text, fill=(255, 255, 255, 255))

    return ctk.CTkImage(light_image=img, dark_image=img, size=(diameter, diameter))
