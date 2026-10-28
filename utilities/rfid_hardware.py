"""
Oficiální ovladač RFID pro Freenove Projects Kit (FNK0054 / FNK0025) a Raspberry Pi.
Využívá přímo nízkoúrovňový Freenove MFRC522 driver přes SPI (/dev/spidev0.0).
Běží v samostatném vlákně a spolehlivě předává UID načteného čipu.
"""
import threading
import time
import os
import sys

# Pre Raspberry Pi 5 explicitne nastavime spravny gpiochip (RP1 = gpiochip4),
# aby kniznica nehladala neexistujuci chip 0 a nevypisovala Fallback warning.
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "rpigpio" if not os.path.exists("/dev/gpiochip4") else "lgpio")

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from utilities.MFRC522 import MFRC522
except ImportError:
    try:
        from MFRC522 import MFRC522
    except ImportError:
        MFRC522 = None


class RFIDHardwareReader:
    def __init__(self, on_chip_scanned_callback=None):
        self.on_chip_scanned = on_chip_scanned_callback
        self.is_running = False
        self.hardware_available = False
        self._reader = None
        self._last_uid = None
        self._last_scan_time = 0
        self._cooldown = 1.8

        self._init_hardware()

    def _init_hardware(self):
        if MFRC522 is None:
            self.hardware_available = False
            return

        try:
            self._reader = MFRC522(bus=0, dev=0, spd=1000000)
            self.hardware_available = True
        except Exception:
            self.hardware_available = False

    def start_listening(self):
        if not self.hardware_available or self.is_running:
            return False

        self.is_running = True
        thread = threading.Thread(target=self._scan_loop, daemon=True)
        thread.start()
        return True

    def stop_listening(self):
        self.is_running = False

    def _scan_loop(self):
        while self.is_running:
            try:
                status, _ = self._reader.MFRC522_Request(self._reader.PICC_REQIDL)
                if status == self._reader.MI_OK:
                    status, uid = self._reader.MFRC522_Anticoll()
                    if status == self._reader.MI_OK and uid and len(uid) >= 4:
                        uid_hex = "".join([f"{x:02X}" for x in uid[:4]])
                        now = time.time()

                        if uid_hex != self._last_uid or (now - self._last_scan_time) > self._cooldown:
                            self._last_uid = uid_hex
                            self._last_scan_time = now
                            if self.on_chip_scanned:
                                self.on_chip_scanned(uid_hex)

                time.sleep(0.08)
            except Exception:
                time.sleep(0.4)

    @staticmethod
    def beep_success():
        """Univerzální pípnutí bzučákem funkční na RPi 5, RPi 4 i starších kitech.
        Freenove Projects Board v1.1 má Active Buzzer na GPIO 12 (přepínač 3)."""
        buzzer_pin = 12

        # 1. gpiozero
        try:
            from gpiozero import Buzzer
            bz = Buzzer(buzzer_pin)
            bz.on()
            time.sleep(0.12)
            bz.off()
            bz.close()
            return
        except Exception:
            pass

        # 2. lgpio (nativní pro RPi 5 i RPi 4)
        try:
            import lgpio
            for chip in [4, 0]:
                try:
                    h = lgpio.gpiochip_open(chip)
                    lgpio.gpio_claim_output(h, buzzer_pin)
                    lgpio.gpio_write(h, buzzer_pin, 1)
                    time.sleep(0.12)
                    lgpio.gpio_write(h, buzzer_pin, 0)
                    lgpio.gpiochip_close(h)
                    return
                except Exception:
                    continue
        except Exception:
            pass

        # 3. RPi.GPIO záloha pro starší modely
        try:
            import RPi.GPIO as GPIO
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            for pin in [12, 17]:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.HIGH)
                time.sleep(0.1)
                GPIO.output(pin, GPIO.LOW)
        except Exception:
            pass
