"""Replace just the head region of existing rook/bishop/queen/king
sprites via PixelLab's inpaint endpoint. Keeps the AI-generated body
and asks the API to repaint the top with the iconic feature.

Run after tools/gen_sprites.py has produced bodies. 4 API calls total.

  python tools/inpaint_heads.py            # all 4 pieces
  python tools/inpaint_heads.py rook king  # only specified
"""
import sys
from pathlib import Path

# Reuse the client loader and inpaint helper from gen_sprites (sibling file)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_sprites import load_client, inpaint_head, HEAD_PROMPTS  # noqa: E402

DEFAULT_PIECES = ["rook", "bishop", "queen", "king"]


def main():
    args = sys.argv[1:]
    head_h = 14
    if args and args[0].startswith("--head-h="):
        head_h = int(args.pop(0).split("=", 1)[1])
    pieces = args if args else DEFAULT_PIECES
    client = load_client()
    print(f"PixelLab balance: {client.get_balance()}")
    for p in pieces:
        if p not in HEAD_PROMPTS:
            print(f"[skip] {p}: no inpaint prompt configured")
            continue
        inpaint_head(client, p, head_h=head_h)
    print(f"Final balance: {client.get_balance()}")


if __name__ == "__main__":
    main()
