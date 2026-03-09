import os
import random
from pathlib import Path

# Colors
C_BLUE = "#0033CC"
C_PAPER = "#F0EADC"

def create_svg_star(path):
    """Creates a jagged blue star sticker SVG"""
    content = f'''<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
      <polygon points="50,0 63,38 100,38 69,59 82,100 50,75 18,100 31,59 0,38 37,38" fill="{C_BLUE}" stroke="none"/>
    </svg>'''
    with open(path, 'w') as f:
        f.write(content)

def create_svg_barcode(path):
    """Creates a simple barcode SVG"""
    rects = ""
    x = 0
    import random
    r = random.Random(42)
    while x < 300:
        w = r.randint(2, 6)
        rects += f'<rect x="{x}" y="0" width="{w}" height="50" fill="black"/>'
        x += w + r.randint(2, 5)
        
    content = f'''<svg width="300" height="50" xmlns="http://www.w3.org/2000/svg">
      {rects}
    </svg>'''
    with open(path, 'w') as f:
        f.write(content)

def create_noise_texture(path):
    """Creates a simple grain texture simply by writing a PPM image (text based image format)"""
    # 100x100 texture
    width = 200
    height = 200
    
    # We want beige #F0EADC +/- noise
    # RGB: 240, 234, 220
    header = f"P3\n{width} {height}\n255\n"
    data = ""
    
    import random
    
    for _ in range(height * width):
        noise = random.randint(-10, 10)
        r = max(0, min(255, 240 + noise))
        g = max(0, min(255, 234 + noise))
        b = max(0, min(255, 220 + noise))
        data += f"{r} {g} {b} "
    
    with open(path, 'w') as f:
        f.write(header + data)

if __name__ == "__main__":
    assets_dir = Path(__file__).parent / "assets"
    assets_dir.mkdir(exist_ok=True)
    
    create_svg_star(assets_dir / "star.svg")
    create_svg_barcode(assets_dir / "barcode.svg")
    create_noise_texture(assets_dir / "paper.ppm")
    print(f"Assets created in {assets_dir}")
