#!/usr/bin/env python3
"""Cut the main subject out of an image (transparent PNG) for parallax layers in motion graphics.

  <image-env>/bin/python tools/cutout.py assets/images/s01.png assets/images/s01-fg.png [--trim]

rembg (MIT, isnet-general-use model, local). Without --trim the output keeps the source size and position,
so the cut-out sits exactly over the original when both are stacked (background layer + foreground layer).
"""
import argparse
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--trim", action="store_true", help="crop to the subject (loses the alignment with the source)")
    ap.add_argument("--model", default="isnet-general-use")
    a = ap.parse_args()
    from PIL import Image
    from rembg import new_session, remove
    img = Image.open(a.src).convert("RGB")
    out = remove(img, session=new_session(a.model), post_process_mask=True)
    if a.trim:
        box = out.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
        out = out.crop(box) if box else out
    a.out.parent.mkdir(parents=True, exist_ok=True)
    out.save(a.out)
    print(f"{a.out}  {out.width}x{out.height}")


if __name__ == "__main__":
    main()
