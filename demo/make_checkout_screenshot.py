"""Draw the synthetic customer screenshot for the checkout incident (demo/screenshots/checkout-customer.png).

It is the only place the incident's specifics appear: the cart, the coupon and the wrong discount.
Run with any Python that has Pillow:  python demo/make_checkout_screenshot.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "screenshots" / "checkout-customer.png"
W, H = 900, 640
INK, MUTED, LINE, ACCENT, GREEN = "#1d2433", "#6b7385", "#e4e7ee", "#3b5bdb", "#2f9e44"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    im = Image.new("RGB", (W, H), "#f4f5f8")
    d = ImageDraw.Draw(im)
    # browser chrome
    d.rectangle((0, 0, W, 44), fill="#e9ebf0")
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        d.ellipse((16 + i * 20, 16, 28 + i * 20, 28), fill=c)
    d.rounded_rectangle((90, 10, W - 20, 34), radius=8, fill="white")
    d.text((104, 14), "shop.lumen-co.example/checkout", fill=MUTED, font=font(14))
    # card
    d.rounded_rectangle((60, 70, W - 60, H - 30), radius=14, fill="white", outline=LINE)
    d.text((90, 92), "Lumen & Co.", fill=INK, font=font(24, True))
    d.text((90, 126), "Checkout  ·  Quote Q-20417  ·  27 Oct 2026, 18:42", fill=MUTED, font=font(14))
    y = 168
    d.line((90, y, W - 90, y), fill=LINE, width=1)
    rows = [("Arc desk lamp", "LAMP-20", "2", "$20.00", "$40.00"), ("Stoneware mug", "MUG-08", "1", "$8.00", "$8.00")]
    d.text((90, y + 14), "Item", fill=MUTED, font=font(14, True))
    for x, label in ((470, "Qty"), (560, "Price"), (700, "Amount")):
        d.text((x, y + 14), label, fill=MUTED, font=font(14, True))
    y += 46
    for name, sku, qty, price, amount in rows:
        d.text((90, y), name, fill=INK, font=font(17, True))
        d.text((90, y + 24), sku, fill=MUTED, font=font(13))
        d.text((478, y + 4), qty, fill=INK, font=font(17))
        d.text((560, y + 4), price, fill=INK, font=font(17))
        d.text((700, y + 4), amount, fill=INK, font=font(17))
        y += 62
    d.line((90, y, W - 90, y), fill=LINE, width=1)
    y += 18
    d.rounded_rectangle((90, y, 300, y + 34), radius=17, fill="#edf2ff")
    d.text((106, y + 7), "Coupon  SAVE10  (10% off)", fill=ACCENT, font=font(14, True))
    d.text((330, y + 8), "Applied", fill=GREEN, font=font(14, True))
    y += 56
    for label, value, bold in (("Subtotal", "$48.00", False), ("Discount (SAVE10)", "-$2.80", False), ("Total", "$45.20", True)):
        d.text((470, y), label, fill=INK if bold else MUTED, font=font(19 if bold else 16, bold))
        d.text((700, y), value, fill=INK, font=font(19 if bold else 16, bold))
        y += 34
    d.rounded_rectangle((470, y + 10, W - 90, y + 58), radius=10, fill=ACCENT)
    d.text((600, y + 22), "Place order", fill="white", font=font(17, True))
    OUT.parent.mkdir(exist_ok=True)
    im.save(OUT, optimize=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
