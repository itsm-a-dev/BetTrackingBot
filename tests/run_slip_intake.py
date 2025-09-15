# tests/run_slip_intake.py
import os, json, glob, logging
from ocr_advanced import ocr_image_multi
from format_router import detect_format

logging.basicConfig(level=logging.INFO)

SLIPS_DIR = os.getenv("SLIPS_DIR", "tests/slips")
MANIFEST = [
    {"file": "HRLSGPBoost2.png", "label": "Hard Rock – MLB/NFL parlay w/ boost"},
    {"file": "HRDParlay.png", "label": "Hard Rock – NFL player SGP"},
    {"file": "HRSingleCashes.png", "label": "Hard Rock – Finished tab (settled bets)"},
    {"file": "HRLCrop.png", "label": "Hard Rock – Cowboys moneyline tile"},
    {"file": "HRGCash.png", "label": "Hard Rock – Jaguars first drive prop"},
    {"file": "HRLParlay.png", "label": "Hard Rock – multi moneyline listings"},
    {"file": "HRLSGPBoost.png", "label": "Hard Rock – Jaguars parlay w/ props"},
]

def summarize(text: str, n=200):
    return text[:n].replace("\n", "\\n")

def main():
    results = []
    for item in MANIFEST:
        path = os.path.join(SLIPS_DIR, item["file"])
        with open(path, "rb") as f:
            data = f.read()
        ocr = ocr_image_multi(data)
        text = ocr["text"]
        fmt = detect_format(text) if text else "unknown"
        ok = bool(text and fmt != "unknown")
        results.append({
            "file": item["file"],
            "label": item["label"],
            "ok": ok,
            "format": fmt,
            "len": len(text),
            "mode": ocr["mode"],
            "config": ocr["config"],
            "scoreboard": sorted(ocr["candidates"], key=lambda x: (-x[3], -x[4]))[:5],
            "preview": summarize(text),
        })
        print(f"[{ 'OK' if ok else 'FAIL' }] {item['label']} -> fmt={fmt}, len={len(text)}, mode={ocr['mode']}, cfg={ocr['config']}")
        if not ok:
            print(f"  Preview: {summarize(text, 260)}")

    # Simple pass/fail summary
    passed = sum(1 for r in results if r["ok"])
    print(f"\n== Summary: {passed}/{len(results)} recognized ==")

    # Optional: dump detailed JSON for diffing
    os.makedirs("tests/output", exist_ok=True)
    with open("tests/output/ocr_results.json", "w") as fp:
        json.dump(results, fp, indent=2)

if __name__ == "__main__":
    main()
