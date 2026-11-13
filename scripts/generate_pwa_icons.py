"""
Generate high-fidelity PWA icons and web manifest for RescueNet Offline Emergency Response.
"""

import os
from PIL import Image, ImageDraw, ImageFont

PUBLIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web", "public"))
os.makedirs(PUBLIC_DIR, exist_ok=True)


def draw_icon(size: int, is_maskable: bool = False) -> Image.Image:
    # High-resolution canvas
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background
    bg_color = (27, 67, 50, 255)  # #1B4332 - Forest Green
    border_color = (0, 229, 255, 255)  # #00E5FF - Cyan accent
    
    if is_maskable:
        # Full bleed for maskable icon
        draw.rectangle([0, 0, size, size], fill=bg_color)
        margin = int(size * 0.18)  # Safe zone for adaptive/maskable icons
    else:
        # Rounded squircle or pill for standard icon
        corner_r = int(size * 0.22)
        draw.rounded_rectangle([2, 2, size - 3, size - 3], radius=corner_r, fill=bg_color, outline=border_color, width=max(2, size // 64))
        margin = int(size * 0.14)

    inner_box = [margin, margin, size - margin, size - margin]
    center_x = size // 2
    center_y = size // 2
    icon_w = size - 2 * margin

    # Draw Emergency Cross + Radio Mesh Emblem
    cross_width = int(icon_w * 0.28)
    cross_len = int(icon_w * 0.8)
    
    # White emergency cross in center
    white = (255, 255, 255, 255)
    orange = (255, 107, 0, 255)  # Emergency orange
    cyan = (0, 229, 255, 255)

    # Vertical bar of cross
    draw.rounded_rectangle(
        [center_x - cross_width // 2, center_y - cross_len // 2, center_x + cross_width // 2, center_y + cross_len // 2],
        radius=max(2, size // 64),
        fill=white
    )
    # Horizontal bar of cross
    draw.rounded_rectangle(
        [center_x - cross_len // 2, center_y - cross_width // 2, center_x + cross_len // 2, center_y + cross_width // 2],
        radius=max(2, size // 64),
        fill=white
    )

    # Radio mesh broadcast rings around the cross
    ring_radius_1 = int(cross_len * 0.48)
    ring_radius_2 = int(cross_len * 0.64)
    line_w = max(2, size // 75)

    # Concentric radar / mesh arcs
    draw.arc(
        [center_x - ring_radius_1, center_y - ring_radius_1, center_x + ring_radius_1, center_y + ring_radius_1],
        start=210, end=330, fill=cyan, width=line_w
    )
    draw.arc(
        [center_x - ring_radius_1, center_y - ring_radius_1, center_x + ring_radius_1, center_y + ring_radius_1],
        start=30, end=150, fill=cyan, width=line_w
    )

    draw.arc(
        [center_x - ring_radius_2, center_y - ring_radius_2, center_x + ring_radius_2, center_y + ring_radius_2],
        start=220, end=320, fill=orange, width=line_w
    )
    draw.arc(
        [center_x - ring_radius_2, center_y - ring_radius_2, center_x + ring_radius_2, center_y + ring_radius_2],
        start=40, end=140, fill=orange, width=line_w
    )

    # Center pulse node
    node_r = max(3, size // 32)
    draw.ellipse(
        [center_x - node_r, center_y - node_r, center_x + node_r, center_y + node_r],
        fill=orange
    )

    return img


def main():
    print(f"Generating PWA icons into {PUBLIC_DIR}...")
    
    # 192x192
    img192 = draw_icon(192, is_maskable=False)
    img192.save(os.path.join(PUBLIC_DIR, "icon-192.png"))

    # 512x512
    img512 = draw_icon(512, is_maskable=False)
    img512.save(os.path.join(PUBLIC_DIR, "icon-512.png"))

    # Maskable 192
    img_mask_192 = draw_icon(192, is_maskable=True)
    img_mask_192.save(os.path.join(PUBLIC_DIR, "icon-maskable-192.png"))

    # Maskable 512
    img_mask_512 = draw_icon(512, is_maskable=True)
    img_mask_512.save(os.path.join(PUBLIC_DIR, "icon-maskable-512.png"))

    # SVG Icon
    svg_content = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="112" fill="#1B4332" stroke="#00E5FF" stroke-width="8"/>
  <rect x="216" y="106" width="80" height="300" rx="16" fill="#FFFFFF"/>
  <rect x="106" y="216" width="300" height="80" rx="16" fill="#FFFFFF"/>
  <circle cx="256" cy="256" r="16" fill="#FF6B00"/>
  <path d="M 136 186 A 150 150 0 0 1 376 186" fill="none" stroke="#00E5FF" stroke-width="8" stroke-linecap="round"/>
  <path d="M 136 326 A 150 150 0 0 0 376 326" fill="none" stroke="#00E5FF" stroke-width="8" stroke-linecap="round"/>
  <path d="M 96 156 A 200 200 0 0 1 416 156" fill="none" stroke="#FF6B00" stroke-width="8" stroke-linecap="round"/>
  <path d="M 96 356 A 200 200 0 0 0 416 356" fill="none" stroke="#FF6B00" stroke-width="8" stroke-linecap="round"/>
</svg>'''
    with open(os.path.join(PUBLIC_DIR, "icon.svg"), "w", encoding="utf-8") as f:
        f.write(svg_content)

    print("PWA icons generated successfully.")


if __name__ == "__main__":
    main()
