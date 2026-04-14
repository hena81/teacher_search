"""
Generate PWA icons from the existing logo.
Run this script once to create all required icon sizes.
"""

import os
from PIL import Image

# Icon sizes needed for PWA
ICON_SIZES = [72, 96, 128, 144, 152, 192, 384, 512]
MASKABLE_SIZES = [192, 512]

def generate_icons():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(base_dir, 'static', 'logo.png')
    icons_dir = os.path.join(base_dir, 'static', 'icons')
    
    # Create icons directory
    os.makedirs(icons_dir, exist_ok=True)
    
    # Open the original logo
    logo = Image.open(logo_path)
    
    # Convert to RGBA if needed
    if logo.mode != 'RGBA':
        logo = logo.convert('RGBA')
    
    print(f"Original logo size: {logo.size}")
    
    # Generate standard icons
    for size in ICON_SIZES:
        icon = logo.copy()
        icon = icon.resize((size, size), Image.LANCZOS)
        output_path = os.path.join(icons_dir, f'icon-{size}x{size}.png')
        icon.save(output_path, 'PNG', optimize=True)
        print(f"✓ Generated: icon-{size}x{size}.png")
    
    # Generate maskable icons (with padding for safe zone)
    for size in MASKABLE_SIZES:
        # Maskable icons need a safe zone - the icon content should be within
        # the inner 80% circle. We add 10% padding on each side.
        padding = int(size * 0.1)
        inner_size = size - (padding * 2)
        
        # Create a new image with background color
        maskable = Image.new('RGBA', (size, size), (30, 64, 175, 255))  # Blue background matching theme
        
        # Resize logo to fit in the safe zone
        icon = logo.copy()
        icon = icon.resize((inner_size, inner_size), Image.LANCZOS)
        
        # Paste centered
        maskable.paste(icon, (padding, padding), icon)
        
        output_path = os.path.join(icons_dir, f'icon-maskable-{size}x{size}.png')
        maskable.save(output_path, 'PNG', optimize=True)
        print(f"✓ Generated: icon-maskable-{size}x{size}.png")
    
    # Generate Apple touch icon (180x180)
    apple_icon = logo.copy()
    apple_icon = apple_icon.resize((180, 180), Image.LANCZOS)
    apple_output = os.path.join(icons_dir, 'apple-touch-icon.png')
    apple_icon.save(apple_output, 'PNG', optimize=True)
    print(f"✓ Generated: apple-touch-icon.png (180x180)")
    
    # Generate favicon (32x32)
    favicon = logo.copy()
    favicon = favicon.resize((32, 32), Image.LANCZOS)
    favicon_output = os.path.join(icons_dir, 'favicon-32x32.png')
    favicon.save(favicon_output, 'PNG', optimize=True)
    print(f"✓ Generated: favicon-32x32.png")
    
    # Generate favicon (16x16)
    favicon16 = logo.copy()
    favicon16 = favicon16.resize((16, 16), Image.LANCZOS)
    favicon16_output = os.path.join(icons_dir, 'favicon-16x16.png')
    favicon16.save(favicon16_output, 'PNG', optimize=True)
    print(f"✓ Generated: favicon-16x16.png")
    
    print(f"\n✅ All icons generated successfully in: {icons_dir}")

if __name__ == '__main__':
    generate_icons()
