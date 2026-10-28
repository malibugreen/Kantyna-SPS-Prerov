#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Oficialny Freenove RFID test pre FNK0054 / Raspberry Pi so zvukovym pipnutim.
Pri kazdom prilozeni cipu nacita UID a aktivuje bzuciak na doske.
"""
import sys
import os
import time

# Pre Raspberry Pi 5 explicitne nastavime spravny gpiochip (RP1 = gpiochip4),
# aby kniznica nehladala neexistujuci chip 0 a nevypisovala Fallback warning.
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "rpigpio" if not os.path.exists("/dev/gpiochip4") else "lgpio")

# Zaistenie importu z priecinka utilities
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utilities"))

# 1. Priprava bzuciaka s podporou RPi 5 aj starsich modelov
# Na doske Freenove Projects Board v1.1 je Active Buzzer pripojeny na GPIO 12 (prepinac c. 3)
BUZZER_PIN = 12

buzzer_device = None
try:
    from gpiozero import Buzzer
    buzzer_device = Buzzer(BUZZER_PIN)
except Exception:
    pass

def beep():
    """Kratke pipnutie pri uspesnom nacitani cipu."""
    global buzzer_device
    if buzzer_device:
        try:
            buzzer_device.on()
            time.sleep(0.12)
            buzzer_device.off()
            return
        except Exception:
            pass

    # Priamy pokus cez lgpio (RPi 5 native)
    try:
        import lgpio
        # Na RPi 5 je 40-pin konektor na gpiochip 4, na starsich RPi na gpiochip 0
        for chip_num in [4, 0]:
            try:
                h = lgpio.gpiochip_open(chip_num)
                lgpio.gpio_claim_output(h, BUZZER_PIN)
                lgpio.gpio_write(h, BUZZER_PIN, 1)
                time.sleep(0.12)
                lgpio.gpio_write(h, BUZZER_PIN, 0)
                lgpio.gpiochip_close(h)
                return
            except Exception:
                continue
    except Exception:
        pass

    # Zalozny sposob pre starsie RPi 3/4 cez RPi.GPIO
    try:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUZZER_PIN, GPIO.OUT)
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        time.sleep(0.12)
        GPIO.output(BUZZER_PIN, GPIO.LOW)
    except Exception:
        pass


try:
    import spidev
    from utilities.MFRC522 import MFRC522
    reader = MFRC522(bus=0, dev=0, spd=1000000)
    print("=======================================================")
    print("  RFID CTECKA + BZUCIAK PRIPRAVENE! ")
    print("=======================================================")
    print("Tip: Uistite sa, ze na cervenom prepinaci (Function Selection)")
    print("     je packa c. 3 (Active Buzzer) prepnuta HORE (ON)!\n")
    print(">>> PRILOZTE KARTU ALEBO MODRY PRIVESOK K CTECCE <<<")
    print("(Pre ukoncenie stlacte Ctrl + C)\n")
except Exception as e:
    print(f"[CHYBA] Inicializacia zlyhala: {e}")
    sys.exit(1)

try:
    while True:
        # Hladanie cipu v dosahu
        (status, TagType) = reader.MFRC522_Request(reader.PICC_REQIDL)
        if status == reader.MI_OK:
            # Nacitanie UID
            (status, uid) = reader.MFRC522_Anticoll()
            if status == reader.MI_OK:
                # Formatovanie UID
                uid_str = "".join([f"{x:02X}" for x in uid[:4]])
                uid_dec = "-".join([str(x) for x in uid[:4]])
                
                print("--------------------------------------------------")
                print(f" [BINGO!] NACTEN CIP! -> PIP!")
                print(f" -> HEX UID : {uid_str}")
                print(f" -> DEC UID : {uid_dec}")
                print("--------------------------------------------------\n")
                
                # Pipnutie
                beep()
                
                # Ochrana proti zbesilemu opakovaniu
                time.sleep(1.5)
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nTest ukonceny.")
