# Rebuilds social-preview.png (1280x640) from the Test results screenshot. Needs Pillow and the Segoe UI fonts (Windows).
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.abspath(__file__))
W, H = 1280, 640
BG = (8, 12, 28)

card = Image.new("RGB", (W, H), BG)

# soft accent glow
glow = Image.new("RGB", (W, H), BG)
gd = ImageDraw.Draw(glow)
gd.ellipse((-200, -250, 700, 450), fill=(40, 60, 150))
gd.ellipse((700, 300, 1500, 900), fill=(70, 40, 140))
glow = glow.filter(ImageFilter.GaussianBlur(160))
card = Image.blend(card, glow, 0.55)

shot = Image.open(os.path.join(ROOT, "screenshots", "lab-test-results-dark.png")).convert("RGB")
sw = 640
sh = int(shot.height * sw / shot.width)
shot = shot.resize((sw, sh), Image.LANCZOS)
x, y = W - sw + 70, 190
shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(shadow).rounded_rectangle((x - 2, y - 2, x + sw + 2, y + sh + 2), 16, fill=(0, 0, 0, 200))
shadow = shadow.filter(ImageFilter.GaussianBlur(18))
card.paste(shadow, (0, 0), shadow)
mask = Image.new("L", shot.size, 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw, sh), 14, fill=255)
card.paste(shot, (x, y), mask)
ImageDraw.Draw(card).rounded_rectangle((x, y, x + sw, y + sh), 14, outline=(70, 90, 160), width=2)

d = ImageDraw.Draw(card)
f = lambda n, s: ImageFont.truetype(rf"C:\Windows\Fonts\{n}.ttf" if os.name == "nt" else f"/usr/share/fonts/truetype/segoe/{n}.ttf", s)
d.text((64, 70), "OPEN-SOURCE SAMPLE", font=f("segoeuib", 22), fill=(110, 200, 255))
d.text((64, 122), "Foundry Agent", font=f("segoeuib", 62), fill=(255, 255, 255))
d.text((64, 190), "Accelerator", font=f("segoeuib", 62), fill=(190, 170, 255))
tag = ["Try, test and build agents on", "Microsoft Foundry. A private Lab,", "sample agents, and Terraform."]
for i, line in enumerate(tag):
    d.text((64, 300 + i * 38), line, font=f("segoeuil", 28), fill=(205, 214, 235))
px = 64
pf = f("segoeui", 20)
for label, col in [("Hosted agents", (110, 200, 255)), ("Terraform", (190, 170, 255)), ("Private by design", (120, 220, 160))]:
    tw = int(d.textlength(label, font=pf))
    d.rounded_rectangle((px, 490, px + tw + 36, 534), 22, outline=col, width=2)
    d.text((px + 18, 499), label, font=pf, fill=col)
    px += tw + 36 + 14
card.save(os.path.join(ROOT, "social-preview.png"), optimize=True)
print(card.size)
