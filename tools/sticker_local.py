#!/usr/bin/env python3
"""Local, free cut-paper "sticker" props for story styles (same idea as the paper-cutout skill's FAL sticker.mjs).

FLUX.1-schnell (Apache-2.0, via mflux on Apple Silicon) draws the subject as layered construction paper on
white, rembg removes the background, the PNG is trimmed to the subject. Nothing leaves this machine.

  <image-env>/bin/python tools/sticker_local.py --subject "a girl holding a pencil, smiling" --out assets/jiwoo-pencil.png \
      --character "Jiwoo: 8-year-old Korean girl, short black bob, yellow T-shirt, blue shorts" --seed 7
  <image-env>/bin/python tools/sticker_local.py --batch stickers.json      # loads the model once

stickers.json: {"character": "...", "style_note": "...", "palette": "#..,#..",
                "items": [{"subject": "...", "out": "assets/a.png", "seed": 7, "init": "assets/base.png", "strength": 0.55}]}

Consistency: keep one --character description and one seed per character; for pose variants pass the
character's first sticker as --init with --strength 0.25-0.4 (mflux image strength: higher = closer to the
reference, so high values freeze the pose). The untrimmed square original (<name>.raw.png) is what is fed
as the reference, so a trimmed tall sticker is never stretched into a square.
Same prompt + seed + size is cached (<out>.json), so re-running only draws what changed.
Model: $FLUX_MODEL or ~/.edu-video/models/FLUX.1-schnell-mflux-4bit (setup: tools/setup_image_gen.sh).
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

MODEL_DIR = Path(os.environ.get("FLUX_MODEL", Path.home() / ".edu-video" / "models" / "FLUX.1-schnell-mflux-4bit"))
PALETTE = "#5FAE55, #3D7D43, #F3B63E, #E25B4B, #2E8C7C, #27406E, #FBF7EE, #A8744A"


def build_prompt(subject: str, character: str = "", style_note: str = "", palette: str = PALETTE) -> str:
    parts = [
        f"A single {subject}, made as a children's paper-cut collage craft: flat pieces of matte construction paper "
        "layered on top of each other, each piece with a clean scissor-cut edge and a very soft shadow underneath.",
        "Simple, rounded, friendly shapes like a picture-book illustration; no outlines, no gradients except a faint "
        "paper fibre texture; tiny cut-paper details only where they help recognition.",
    ]
    if character:
        parts.append(f"The character is always drawn the same way: {character}.")
    if style_note:
        parts.append(f"Art direction: {style_note}.")
    parts.append(f"Colour palette: {palette}.")
    parts.append("Centred, whole subject visible, generous margin, on a plain pure white background. "
                 "No text, no letters, no logos, no frame, no scene, no ground shadow.")
    return " ".join(parts)


class Studio:
    def __init__(self, steps: int, size: int, matting: str, width: int = 0, height: int = 0, plain: bool = False):
        self.steps, self.size, self.matting = steps, size, matting
        self.w, self.h, self.plain = width or size, height or size, plain   # plain: whole scene image, subject = full prompt
        self.flux = self.rembg = None

    def model(self):
        if self.flux is None:
            if not (MODEL_DIR / "transformer").exists() and not any(MODEL_DIR.glob("*.safetensors")):
                sys.exit(f"FLUX model not found in {MODEL_DIR} — run tools/setup_image_gen.sh")
            from mflux.models.common.config.model_config import ModelConfig
            from mflux.models.flux.variants.txt2img.flux import Flux1
            t = time.time()
            self.flux = Flux1(model_path=str(MODEL_DIR), model_config=ModelConfig.schnell())
            print(f"model loaded in {time.time() - t:.0f}s ({MODEL_DIR.name})", flush=True)
        return self.flux

    def cutout(self, img):
        if self.matting == "none":
            return img
        if self.rembg is None:
            from rembg import new_session
            self.rembg = new_session(self.matting)
        from rembg import remove
        out = remove(img, session=self.rembg, post_process_mask=True)
        box = out.getchannel("A").point(lambda a: 255 if a > 24 else 0).getbbox()
        if box:   # trim to the subject with a small margin
            pad = 16
            box = (max(0, box[0] - pad), max(0, box[1] - pad), min(out.width, box[2] + pad), min(out.height, box[3] + pad))
            out = out.crop(box)
        return out

    def make(self, item: dict, shared: dict, i: int, n: int) -> None:
        out = Path(item["out"])
        if self.plain:
            note = item.get("style_note", shared.get("style_note", ""))
            prompt = item["subject"] + (f" Art direction: {note}." if note else "") + " No text, no letters, no logos."
        else:
            prompt = build_prompt(item["subject"], item.get("character", shared.get("character", "")),
                                  item.get("style_note", shared.get("style_note", "")), item.get("palette", shared.get("palette", PALETTE)))
        seed = int(item.get("seed", shared.get("seed", 7)))
        init = item.get("init")
        strength = float(item.get("strength", 0.3)) if init else None
        key = hashlib.sha1(json.dumps([prompt, seed, self.w, self.h, self.steps, init, strength, self.matting]).encode()).hexdigest()[:12]
        meta = out.with_suffix(out.suffix + ".json")
        if out.exists() and meta.exists() and json.loads(meta.read_text()).get("key") == key:
            print(f"sticker {i}/{n} cached  {out}", flush=True)
            return
        if init:   # use the untrimmed square original of the reference sticker (no stretching)
            raw_init = Path(init).with_name(Path(init).stem + ".raw.png")
            init = str(raw_init) if raw_init.exists() else init
            if not Path(init).exists():
                sys.exit(f"--init image not found: {init} (make the base sticker first)")
        t = time.time()
        res = self.model().generate_image(seed=seed, prompt=prompt, num_inference_steps=self.steps, width=self.w,
                                          height=self.h, image_path=init, image_strength=strength)
        raw = res.image.convert("RGB")
        out.parent.mkdir(parents=True, exist_ok=True)
        raw.save(out.with_name(out.stem + ".raw.png"))   # square original: reference for pose variants
        img = self.cutout(raw)
        img.save(out)
        meta.write_text(json.dumps({"key": key, "subject": item["subject"], "seed": seed, "init": init, "strength": strength,
                                    "prompt": prompt, "model": MODEL_DIR.name}, ensure_ascii=False, indent=2))
        print(f"sticker {i}/{n} made {time.time() - t:4.0f}s  {out}  ({img.width}x{img.height})", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject")
    ap.add_argument("--out")
    ap.add_argument("--batch", type=Path)
    ap.add_argument("--character", default="")
    ap.add_argument("--style-note", default="")
    ap.add_argument("--palette", default=PALETTE)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--init", help="reference image for a pose variant of the same character")
    ap.add_argument("--strength", type=float, default=0.3, help="with --init: how much of the reference to keep (0.25-0.4)")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--width", type=int, default=0, help="with --height: non-square output, e.g. 1344x768 for 16:9")
    ap.add_argument("--height", type=int, default=0)
    ap.add_argument("--plain", action="store_true", help="whole scene image: subject is the full prompt, no paper-cut template "
                    "(use with --matting none)")
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--matting", default="isnet-general-use", help="rembg model, or 'none' to keep the white background")
    a = ap.parse_args()

    if a.batch:
        spec = json.loads(a.batch.read_text(encoding="utf-8"))
        items = spec["items"]
        base = a.batch.resolve().parent
        for it in items:   # paths in the batch file are relative to it
            it["out"] = str((base / it["out"]).resolve())
            if it.get("init"):
                it["init"] = str((base / it["init"]).resolve())
    elif a.subject and a.out:
        spec = {"character": a.character, "style_note": a.style_note, "palette": a.palette, "seed": a.seed}
        items = [{"subject": a.subject, "out": a.out, **({"init": a.init, "strength": a.strength} if a.init else {})}]
    else:
        ap.error("give --subject and --out, or --batch file.json")
    st = Studio(a.steps, a.size, a.matting, a.width, a.height, a.plain)
    for i, it in enumerate(items, 1):
        st.make(it, spec, i, len(items))


if __name__ == "__main__":
    main()
