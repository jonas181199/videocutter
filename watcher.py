#!/usr/bin/env python3
"""Ueberwacht einen Ordner und verarbeitet neue Videos automatisch mit clipper.process().

Struktur:  inbox/  -> neue Videos rein
           done/   -> verarbeitete Originale
           failed/ -> Videos, bei denen etwas schiefging (+ .error.txt)
           clips/<videoname>/  -> fertige Clips + captions.json
"""
import argparse, shutil, time, traceback
from pathlib import Path
import clipper

EXT = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}

def is_stable(p, wait=3):
    """Datei fertig kopiert/hochgeladen? Groesse muss sich ueber `wait` Sekunden gleich bleiben."""
    try:
        a = p.stat().st_size; time.sleep(wait); return a > 0 and a == p.stat().st_size
    except FileNotFoundError:
        return False

def unique(dest):
    if not dest.exists(): return dest
    i = 1
    while (c := dest.with_stem(f"{dest.stem}_{i}")).exists(): i += 1
    return c

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Basisordner fuer inbox/done/failed/clips")
    ap.add_argument("--interval", type=int, default=10, help="Pruefintervall in Sekunden")
    ap.add_argument("--n", type=int, default=5); ap.add_argument("--min", type=int, default=20)
    ap.add_argument("--max", type=int, default=60); ap.add_argument("--lang", default="de")
    ap.add_argument("--whisper", default="small"); ap.add_argument("--mode", choices=["crop", "blur"], default="crop")
    ap.add_argument("--once", action="store_true", help="Inbox einmal abarbeiten und beenden")
    a = ap.parse_args()

    root = Path(a.root)
    inbox, done, failed, clips = (root / d for d in ("inbox", "done", "failed", "clips"))
    for d in (inbox, done, failed, clips): d.mkdir(parents=True, exist_ok=True)
    print(f"👀 Beobachte {inbox.resolve()} (Strg+C zum Beenden)", flush=True)

    while True:
        for v in sorted(inbox.iterdir()):
            if v.suffix.lower() not in EXT or v.name.startswith(".") or not is_stable(v):
                continue
            print(f"▶ Verarbeite {v.name}", flush=True)
            try:
                clipper.process(v, unique(clips / v.stem), a.n, a.min, a.max, a.lang, a.whisper, a.mode)
                shutil.move(v, unique(done / v.name))
            except Exception:
                err = traceback.format_exc(); print(err, flush=True)
                dest = unique(failed / v.name)
                shutil.move(v, dest); dest.with_suffix(".error.txt").write_text(err)
        if a.once: break
        time.sleep(a.interval)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nBeendet.")
