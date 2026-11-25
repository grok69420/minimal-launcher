#!/usr/bin/env python3
"""Tiny UI driver for the release build: find a node by text or content description and tap it.
usage: ui.py tap "Cases" | ui.py has "Offline" | ui.py dump"""
import re, subprocess, sys, time, xml.etree.ElementTree as ET

def dump():
    for _ in range(4):
        subprocess.run(["adb", "shell", "uiautomator", "dump", "/sdcard/ui.xml"], capture_output=True)
        out = subprocess.run(["adb", "exec-out", "cat", "/sdcard/ui.xml"], capture_output=True).stdout
        try:
            return ET.fromstring(out)
        except ET.ParseError:
            time.sleep(1)
    return None

def find(root, label):
    if root is None:
        return None
    best = None
    for n in root.iter("node"):
        t, d = n.get("text", ""), n.get("content-desc", "")
        if label in (t, d) or (label.endswith("*") and (t.startswith(label[:-1]) or d.startswith(label[:-1]))):
            b = [int(v) for v in re.findall(r"\d+", n.get("bounds", ""))]
            if len(b) == 4 and b[2] > b[0] and b[3] > b[1]:
                best = b
                if n.get("clickable") == "true":
                    return b
    return best

cmd, label = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
root = dump()
if cmd == "dump":
    for n in (root.iter("node") if root is not None else []):
        if n.get("text") or n.get("content-desc"):
            print(repr(n.get("text")), repr(n.get("content-desc")), n.get("bounds"))
    sys.exit(0)
b = find(root, label)
if b is None:
    sys.exit(1)
if cmd == "tap":
    subprocess.run(["adb", "shell", "input", "tap", str((b[0] + b[2]) // 2), str((b[1] + b[3]) // 2)])
sys.exit(0)
