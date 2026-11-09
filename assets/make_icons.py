"""Draws the integration's icon: a 24-hour dial whose rim is split into tariff windows.

    python3 assets/make_icons.py   # writes icon.svg, dark_icon.svg and the brand PNGs

Needs rsvg-convert (brew install librsvg).
"""
import math
import pathlib
import subprocess

HERE = pathlib.Path(__file__).parent
BRAND = HERE.parent / 'custom_components' / 'globird_zerohero' / 'brand'

CX = CY = 256
RING_R, RING_W = 196, 64
GAP_DEG = 4  # transparent gap between windows, so the segments read as separate rates

# (start hour, end hour, colour): free at midday, peak in the evening, off-peak otherwise.
WINDOWS = [
    (11, 14, '#43A047'),  # free
    (14, 16, '#1E88E5'),  # off-peak
    (16, 23, '#FB8C00'),  # peak
    (23, 35, '#1E88E5'),  # off-peak, through midnight
]


def point(hour, r):
    a = math.radians(hour / 24 * 360 - 90)  # midnight at the top
    return CX + r * math.cos(a), CY + r * math.sin(a)


def arc(start, end, colour):
    pad = GAP_DEG / 2 / 360 * 24
    s, e = start + pad, end - pad
    x1, y1 = point(s, RING_R)
    x2, y2 = point(e, RING_R)
    large = 1 if (e - s) > 12 else 0
    return (f'<path d="M{x1:.1f},{y1:.1f} A{RING_R},{RING_R} 0 {large} 1 {x2:.1f},{y2:.1f}" '
            f'stroke="{colour}"/>')


def svg(face, bolt):
    arcs = ''.join(arc(*w) for w in WINDOWS)
    # Lightning bolt, centred on the dial.
    bolt_path = 'M282,118 L170,276 L246,276 L224,394 L342,226 L264,226 Z'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <g fill="none" stroke-width="{RING_W}">{arcs}</g>
  <circle cx="{CX}" cy="{CY}" r="{RING_R - RING_W / 2 - 14}" fill="{face}"/>
  <path d="{bolt_path}" fill="{bolt}" stroke="{bolt}" stroke-width="10" stroke-linejoin="round"/>
</svg>
'''


VARIANTS = {
    '': svg(face='#ECEFF1', bolt='#263238'),
    'dark_': svg(face='#37474F', bolt='#FFCA28'),
}
BRAND.mkdir(exist_ok=True)
for prefix, text in VARIANTS.items():
    source = HERE / f'{prefix}icon.svg'
    source.write_text(text)
    for suffix, size in (('', 256), ('@2x', 512)):
        subprocess.run(['rsvg-convert', '-w', str(size), '-h', str(size), '-o',
                        BRAND / f'{prefix}icon{suffix}.png', source], check=True)
print('wrote', sorted(p.name for p in BRAND.iterdir()))
