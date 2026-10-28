# 🥪 Školní Samoobslužný Systém Kantýny (Kiosek & Pokladna)

Komplexní systém pro školní bufet / kantýnu navržený pro **Raspberry Pi 5** a výukovou desku **Freenove Projects Board v1.1** (FNK0054).

Systém umožňuje studentům a učitelům samoobslužný nákup svačin pomocí RFID čipů/karet a obsluze kantýny přehlednou správu skladu, dobíjení kreditu a registraci nových uživatelů.

---

<!-- ZDE VLOŽ FOTKU CELÉHO PROJEKTU NEBO HLAVNÍ OBRAZOVKY -->
<!-- Příklad: ![Náhled projektu](img/hlavni_nahled.png) -->
> 📸 *[MÍSTO PRO FOTKU: Celkový pohled na zapojené Raspberry Pi s deskou Freenove a displejem]*

---

## ✨ Hlavní funkce

### 1. Samoobslužný Kiosek (`kiosk_app.py`)
- **Dotykové rozhraní:** Velké, přehledné dlaždice kategorií a produktů s obrázky a cenami.
- **Košík a objednávka:** Jednoduché přidávání, změna počtu kusů a okamžitý přehled celkové ceny.
- **Platba RFID čipem:** Okamžité zaplacení pouhým přiložením karty nebo klíčenky k RFID čtečce.
- **Zvuková odezva:** Pípnutí aktivním bzučákem na desce při úspěšném načtení a platbě.
- **Kontrola zůstatku:** Upozornění v případě nedostatku kreditu na účtu.

<!-- ZDE VLOŽ SCREENSHOT KIOSKU -->
> 📸 *[MÍSTO PRO OBRÁZEK: Screenshot spuštěného samoobslužného kiosku s nabídkou jídel]*

---

### 2. Pokladna pro obsluhu (`cashier_app.py`)
- **Dobíjení kreditu:** Rychlé přiložení čipu a dobití hotovosti (předvolená tlačítka +50, +100, +200 Kč nebo vlastní částka).
- **Automatická registrace nového čipu:** Pokud systém načte neznámý čip, okamžitě otevře dialog pro založení nového zákazníka (jméno, příjmení, počáteční vklad).
- **Správa skladu a produktů:** Přidávání nových položek, úprava cen, stavu zásob a nahrávání obrázků.
- **Přehled historie:** Záznamy o provedených platbách a dobitích kreditu.

<!-- ZDE VLOŽ SCREENSHOT POKLADNY -->
> 📸 *[MÍSTO PRO OBRÁZEK: Screenshot rozhraní pokladny / dobíjení kreditu]*

---

## 🛠️ Použitý hardware

- **Počítač:** Raspberry Pi 5 (podporováno i Raspberry Pi 4 / 3)
- **Výuková deska:** Freenove Projects Board v1.1
- **RFID čtečka:** RC522 (komunikace po sběrnici SPI `/dev/spidev0.0`)
- **Zvuková signalizace:** Integrovaný aktivní bzučák na desce (GPIO 12, přepínač č. 3)
- **Identifikátory:** 13.56 MHz RFID karty a klíčenky (Mifare Classic)

> ⚠️ **Důležité nastavení desky Freenove:**  
> Na červeném přepínači funkcí (*Function Selection*) přepněte páčku **č. 3 (Active Buzzer)** nahoru do polohy **ON**.

---

## 🚀 Instalace a první nastavení

### Krok 1: Povolení rozhraní SPI na Raspberry Pi
Aby deska mohla komunikovat s RFID čtečkou, musí být v systému zapnutá sběrnice SPI:
1. V terminálu Raspberry Pi spusťte konfiguraci:
   ```bash
   sudo raspi-config
   ```
2. Zvolte **Interface Options** -> **SPI**.
3. Na dotaz pro zapnutí vyberte **Yes** a potvrďte **Finish**.

---

### Krok 2: Automatická instalace závislostí
Ve složce `install/` jsou připravené automatické skripty, které samy nainstalují vše potřebné (systémový Tkinter, PIL i knihovny pro Python):

- **Na Raspberry Pi / Linuxu:**
  V terminálu přejděte do složky projektu a spusťte:
  ```bash
  bash install/install_linux.sh
  ```

- **Na počítači s Windows (pro testování):**
  Stačí dvakrát kliknout na soubor:
  ```text
  install/install_windows.bat
  ```

---

## 🎮 Spuštění aplikací

### 1. Rychlé spuštění přes připravené skripty (Doporučeno)
V kořenové složce jsou nachystané spouštěcí skripty, které si samy ohlídají správnou cestu i prostředí:
- **Samoobslužný kiosek:**
  ```bash
  ./spustit_kiosek.sh
  ```
- **Pokladna / Správa:**
  ```bash
  ./spustit_pokladna.sh
  ```
*(Případně na ně můžete na Raspberry Pi v grafickém správci souborů jen dvakrát kliknout a zvolit „Spustit v terminálu“).*

---

### 2. Spuštění přímo přes Python
- **Samoobslužný kiosek:**
  ```bash
  python3 kiosk_app.py
  ```
- **Pokladna / Správa:**
  ```bash
  python3 cashier_app.py
  ```
- **Rychlý test RFID čtečky a bzučáku:**
  ```bash
  python3 test_rfid.py
  ```

---

### 3. Spouštění přes ikony na Ploše
Ve složce `utilities/` jsou připravené zástupci pro plochu:
- `Spustit_Kiosek.desktop`
- `Spustit_Pokladna.desktop`

Stačí je zkopírovat na plochu Raspberry Pi a aplikace lze spouštět přímo dvojklikem.

---

## 🧪 Testovací režim (bez připojeného HW na PC)
Pokud chcete aplikaci vyzkoušet na běžném notebooku/PC bez připojeného Raspberry Pi:
- **Testovací kiosek:** `python TEST_kiosk_app.py`
- **Testovací pokladna:** `python TEST_cashier_app.py`

Tyto verze obsahují tlačítka pro simulaci přiložení RFID čipu a nevyžadují žádný fyzický hardware.
