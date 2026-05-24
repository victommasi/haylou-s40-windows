"""Rasteriza o logomark (mesmo design de assets/icon.svg) em PNG + ICO via Pillow.
Sem dependência de renderizador SVG. Gera icon.png, icon.ico e sobrescreve s30.ico
(usado pelo build_exe.ps1 como --icon do .exe)."""
import os, math
from PIL import Image, ImageDraw

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
S = 512
RED = (255, 74, 82, 255)     # accent sólido (meio do gradiente da arte)
WHITE = (254, 254, 254, 255)

def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# 1) tile com gradiente vertical (#17171F -> #0A0A10) recortado em cantos arredondados
grad = Image.new("RGBA", (S, S))
gp = grad.load()
top, bot = (0x17, 0x17, 0x1F), (0x0A, 0x0A, 0x10)
for y in range(S):
    c = lerp(top, bot, y / (S - 1))
    row = (c[0], c[1], c[2], 255)
    for x in range(S):
        gp[x, y] = row
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=112, fill=255)
img.paste(grad, (0, 0), mask)

# 2) glow vermelho radial atrás do fone
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
lp = glow.load()
cx, cy, rad = 256, 312, 190
for y in range(cy - rad, cy + rad):
    for x in range(cx - rad, cx + rad):
        d = math.hypot(x - cx, y - cy)
        if d < rad:
            lp[x, y] = (255, 59, 92, int(0.20 * 255 * (1 - d / rad)))
clipped = Image.new("RGBA", (S, S), (0, 0, 0, 0))
clipped.paste(glow, (0, 0), mask)
img = Image.alpha_composite(img, clipped)

draw = ImageDraw.Draw(img)
# 3) headband (arco superior espesso)
draw.arc([148, 170, 364, 402], start=180, end=360, fill=RED, width=40)
# 4) conchas over-ear
draw.rounded_rectangle([108, 264, 188, 392], radius=34, fill=RED)
draw.rounded_rectangle([324, 264, 404, 392], radius=34, fill=RED)
# 5) onda do ANC: caótica -> plana (a "história" do cancelamento)
pts = [(200, 330), (207, 314), (215, 308), (223, 314), (230, 330),
       (238, 346), (245, 352), (253, 346), (260, 330), (312, 330)]
draw.line(pts, fill=WHITE, width=13, joint="curve")
for (x, y) in (pts[0], pts[-1]):
    draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill=WHITE)

sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(os.path.join(ASSETS, "icon.png"))
img.save(os.path.join(ASSETS, "icon.ico"), sizes=sizes)
img.save(os.path.join(ASSETS, "s30.ico"), sizes=sizes)  # build usa s30.ico
print("OK: icon.png, icon.ico, s30.ico gerados em", ASSETS)
