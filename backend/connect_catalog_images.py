"""
Connect Solar Brochure Product Images to Product Records
Copies 147 clean product photographs to media/products/, builds composite images
for multi-comb sets, and enriches Product records in the database with photo,
image_url, gallery_images, and color_images.
"""

import os
import sys
import shutil
import re
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'orderbot.settings')

import django
django.setup()

from apps.core.models import Product

SOURCE_DIR = BASE_DIR / "Solar Brochure Products"
TARGET_MEDIA_DIR = BASE_DIR / "media" / "products"
TARGET_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r'[\s\.\-]+', '_', s)
    s = re.sub(r'[^a-z0-9_]', '', s)
    return s.strip('_')

# Define helper to stitch vertical or horizontal images with transparent background
def create_side_by_side_composite(image_paths: list, output_path: Path, spacing: int = 15):
    images = [Image.open(p).convert("RGBA") for p in image_paths]
    max_height = max(im.height for im in images)
    total_width = sum(im.width for im in images) + spacing * (len(images) - 1)
    
    composite = Image.new("RGBA", (total_width, max_height), (0, 0, 0, 0))
    x_offset = 0
    for im in images:
        y_offset = (max_height - im.height) // 2
        composite.paste(im, (x_offset, y_offset), im)
        x_offset += im.width + spacing
        
    composite.save(output_path, "PNG")
    print(f"  [+] Created composite: {output_path.name} ({total_width}x{max_height})")
    return output_path

# Comprehensive mapping rules for all 147 files
PRIMARY_MAPPINGS = {
    '077 Red Gold 1.png': {'query': {'name__icontains': '077 RED GOLD'}, 'is_primary': True, 'color': 'RG'},
    '077 Red Gold 2.png': {'query': {'name__icontains': '077 RED GOLD'}, 'is_primary': False, 'color': 'BLACK'},
    '2020 Handle.png': {'query': {'name__icontains': '20-20 HANDLE'}, 'is_primary': True},
    '3 In 1.png': {'query': {'sku__icontains': '3-IN-1'}, 'is_primary': True},
    '4in Weston Opec 1.png': {'query': {'name__icontains': 'WESTON 4'}, 'is_primary': False, 'color': 'PL'},
    '4in Weston Opec 2.png': {'query': {'name__icontains': 'WESTON 4'}, 'is_primary': False, 'color': 'GW'},
    '4in Weston Opec 3.png': {'query': {'name__icontains': 'WESTON 4'}, 'is_primary': False, 'color': 'ALM'},
    '4in Weston Opec 4.png': {'query': {'name__icontains': 'WESTON 4'}, 'is_primary': False, 'color': 'ICE'},
    '50 50.png': {'query': {'name__icontains': '50-50'}, 'is_primary': True},
    '555.png': {'query': {'name__icontains': '501/555'}, 'is_primary': True},
    '5in Bunty.png': {'query': {'name__icontains': 'BUNTY'}, 'is_primary': True},
    '5in C4 Opec 1.png': {'query': {'name__icontains': 'C-4 OPEC'}, 'is_primary': False, 'color': 'PL'},
    '5in C4 Opec 2.png': {'query': {'name__icontains': 'C-4 OPEC'}, 'is_primary': False, 'color': 'GW'},
    '5in C4 Opec 3.png': {'query': {'name__icontains': 'C-4 OPEC'}, 'is_primary': False, 'color': 'ALM'},
    '5in Clip.png': {'query': {'name__icontains': '5" CLIP'}, 'is_primary': True},
    '5in Cross Handle.png': {'query': {'name__icontains': '5" CROSS HANDLE'}, 'is_primary': True},
    '5in D. Hole.png': {'query': {'name__icontains': 'SOLAR D.HOLE'}, 'is_primary': True},
    '5in Handle.png': {'query': {'name__icontains': 'SOLAR 5" HANDLE PL'}, 'is_primary': True},
    '5in Hole.png': {'query': {'name__icontains': 'SOLAR 5" HOLE PL'}, 'is_primary': True},
    '5in Lovely Handle.png': {'query': {'name__icontains': '5" LOVELY HANDLE'}, 'is_primary': True},
    '5in Maskachaska.png': {'query': {'name__icontains': '5" MXC'}, 'is_primary': True},
    '5in Pearl.png': {'query': {'name__icontains': 'SOLAR 5" PEARL'}, 'is_primary': True},
    '5in Purnima 2in1.png': {'query': {'name__icontains': 'PURNIMA 5" 2 IN 1'}, 'is_primary': True},
    '5in Purnima 555.png': {'query': {'name__icontains': 'PURNIMA 5" 555'}, 'is_primary': True},
    '5in Purnima Danby.png': {'query': {'name__icontains': 'PURNIMA 5" DANBY'}, 'is_primary': True},
    '5in Purnima Hole.png': {'query': {'name__icontains': 'PURNIMA 5" HOLE'}, 'is_primary': True},
    '5in Red Gold.png': {'query': {'name__icontains': 'SOLAR 5" REDGOLD'}, 'is_primary': True, 'color': 'RG'},
    '5in Rio.png': {'query': {'name__icontains': 'SOLAR 5" RIO'}, 'is_primary': True},
    '7 Inch.png': {'query': {'name__icontains': '7" PEARL'}, 'is_primary': True},
    '7in D. Hole.png': {'query': {'name__icontains': '7" D.HOLE'}, 'is_primary': True},
    '7in Lovely Handle.png': {'query': {'name__icontains': '7" LOVELY HANDLE'}, 'is_primary': True},
    '7in Red Gold.png': {'query': {'name__icontains': '7" REDGOLD'}, 'is_primary': True, 'color': 'RG'},
    '7in Wonder.png': {'query': {'name__icontains': '7" WONDER'}, 'is_primary': True},
    '888 Maharaja Pearl.png': {'query': {'name__icontains': '888 MAHARAJA PEARL'}, 'is_primary': True},
    '888 Prime.png': {'query': {'name__icontains': '888 PRIME'}, 'is_primary': True},
    '8in Wonder.png': {'query': {'name__icontains': '8" WONDER'}, 'is_primary': True},
    '9in Amazone.png': {'query': {'name__icontains': 'AMAZON'}, 'is_primary': True},
    '9in Best.png': {'query': {'name__icontains': '9" BEST'}, 'is_primary': True},
    '9in Bingo.png': {'query': {'name__icontains': '9" BINGO'}, 'is_primary': True},
    '9in Pearl Folder.png': {'query': {'name__icontains': '9" PEARL FOLDER'}, 'is_primary': True},
    '9in Pearl.png': {'query': {'name__icontains': '9" PEARL BOX'}, 'is_primary': True},
    '9in Red Gold.png': {'query': {'name__icontains': '9" REDGOLD'}, 'is_primary': True, 'color': 'RG'},
    'Aiwa.png': {'query': {'name__icontains': 'AIWA'}, 'is_primary': True},
    'Audi 1.png': {'query': {'name__icontains': 'AUDI', 'group_alias': 'SOLAR COMB'}, 'is_primary': True, 'color': 'FL'},
    'Audi 2.png': {'query': {'name__icontains': 'AUDI', 'group_alias': 'SOLAR COMB'}, 'is_primary': False, 'color': 'BKDC'},
    'Baby Zee.png': {'query': {'name__icontains': 'BABY ZEE'}, 'is_primary': True},
    'Badshah.png': {'query': {'name__icontains': 'BADSHAH'}, 'is_primary': True},
    'Barber.png': {'query': {'name': 'BARBER PL/ALM/GW'}, 'is_primary': True},
    'Big Cartier.png': {'query': {'name__icontains': 'BIG CARTER'}, 'is_primary': True},
    'Big Chapta 1.png': {'query': {'name__icontains': 'BIG-CHAPTA'}, 'is_primary': True, 'color': 'PL'},
    'Big Chapta 2.png': {'query': {'name__icontains': 'BIG-CHAPTA'}, 'is_primary': False, 'color': 'GW'},
    'Big Hearty.png': {'query': {'name__icontains': 'BIG HEARTY'}, 'is_primary': True},
    'Bigboss Print.png': {'query': {'name': 'BIG BOSS PRINT'}, 'is_primary': True},
    'Bigboss.png': {'query': {'name': 'BIG BOSS PL/SHELL/GW'}, 'is_primary': True},
    'Bullet.png': {'query': {'name__icontains': 'BULLET', 'group_alias': 'SOLAR COMB'}, 'is_primary': True},
    'C.C.999.png': {'query': {'name__icontains': 'C.C.999'}, 'is_primary': True},
    'Camel.png': {'query': {'name__icontains': 'CAMEL TOOTH'}, 'is_primary': True},
    'Charmi Jali.png': {'query': {'name__icontains': 'CHARMI JALI'}, 'is_primary': True},
    'Cosmo Handle.png': {'query': {'name__icontains': 'COSMO HANDLE'}, 'is_primary': True},
    'Cross Handle.png': {'query': {'name__icontains': 'CROSS HANDLE PL/ICE'}, 'is_primary': True},
    'Crown.png': {'query': {'name__icontains': 'CROWN PL/GW'}, 'is_primary': True},
    'Cutting.png': {'query': {'name__icontains': 'CUTTING PL/ICE'}, 'is_primary': True},
    'Delight.png': {'query': {'name__icontains': 'DELITE'}, 'is_primary': True},
    'Diamond.png': {'query': {'name__icontains': 'DAIMOND'}, 'is_primary': True},
    'Dollar Clip.png': {'query': {'name__icontains': 'DOLLAR CLIP COMBS'}, 'is_primary': True},
    'Dolly.png': {'query': {'name__icontains': 'DOLLY 9'}, 'is_primary': True},
    'Dolphin Handle.png': {'query': {'name__icontains': 'DOLPHINE HANDLE'}, 'is_primary': True},
    'Dressing Handle.png': {'query': {'name__icontains': 'DRESSING HANDLE'}, 'is_primary': True},
    'Elegant Handle.png': {'query': {'name__icontains': 'ELEGANT HANDLE'}, 'is_primary': True},
    'Ertiga.png': {'query': {'name__icontains': 'ERTIGA'}, 'is_primary': True},
    'Fancy Handle Print.png': {'query': {'name': 'FANCY HANDLE PRINT'}, 'is_primary': True},
    'Fancy Handle.png': {'query': {'name': 'FANCY HANDLE PL/SHELL/ICE'}, 'is_primary': True},
    'Flower Handle.png': {'query': {'name': 'FLOWER HANDLE PL/GW'}, 'is_primary': True},
    'Galaxy.png': {'query': {'name': 'GALAXY PEARL'}, 'is_primary': True},
    'H.P 999.png': {'query': {'name__icontains': 'H.P.999'}, 'is_primary': True},
    'Headline.png': {'query': {'name__icontains': 'HEADLINE'}, 'is_primary': True},
    'Honda.png': {'query': {'name__icontains': 'HONDA COMB 9'}, 'is_primary': True},
    'Indian Idol 1.png': {'query': {'name__icontains': 'INDIAN IDOL'}, 'is_primary': True, 'color': 'GW'},
    'Indian Idol 2.png': {'query': {'name__icontains': 'INDIAN IDOL'}, 'is_primary': False, 'color': 'BKDC'},
    'Indigo.png': {'query': {'name__icontains': 'INDIGO'}, 'is_primary': True},
    'Innova.png': {'query': {'name__icontains': 'INNOVA PL/MILKY'}, 'is_primary': True},
    'Ipl Handle.png': {'query': {'name__icontains': 'IPL HANDLE'}, 'is_primary': True},
    'Jio.png': {'query': {'name__icontains': 'JIO PEARL'}, 'is_primary': True},
    'Jumbo.png': {'query': {'name': 'JUMBO PL/GW/SHELL'}, 'is_primary': True},
    'Kia.png': {'query': {'name': 'KIA PL/GW/SHELL'}, 'is_primary': True},
    'King Cartier.png': {'query': {'name__icontains': 'KING CARTER'}, 'is_primary': True},
    'Kiran.png': {'query': {'name__icontains': 'KIRAN'}, 'is_primary': True},
    'Kit Kat.png': {'query': {'name__icontains': 'KIT-KAT'}, 'is_primary': True},
    'Lotus.png': {'query': {'name__icontains': 'LOTUS PL/GW'}, 'is_primary': True},
    'Maggie.png': {'query': {'name__icontains': 'MAGGIE'}, 'is_primary': True},
    'Maharaja 999 Mix 1.png': {'query': {'name__icontains': '999 MAHARAJA MIX'}, 'is_primary': True, 'color': 'RG'},
    'Maharaja 999 Mix 2.png': {'query': {'name__icontains': '999 MAHARAJA MIX'}, 'is_primary': False, 'color': 'BLACK'},
    'Maharaja 999 Pearl.png': {'query': {'name__icontains': '999 MAHARAJA PEARL'}, 'is_primary': True},
    'Maharaja Barber.png': {'query': {'name': 'MAHARAJA BARBER PL/GW/ALM'}, 'is_primary': True},
    'Maruti.png': {'query': {'name': 'MARUTI PL/ICE/SHELL'}, 'is_primary': True},
    'Maska Chaska Krt.png': {'query': {'name': 'MXC (MASKA-CHASKA) K.R.T'}, 'is_primary': True, 'color': 'KRT'},
    'Maska Chaska.png': {'query': {'name': 'MXC (MASKA-CHASKA) PL/GW/ALM'}, 'is_primary': True, 'color': 'PL'},
    'Maxx.png': {'query': {'name__icontains': 'MAXX PL/DC'}, 'is_primary': True},
    'Metro.png': {'query': {'name__icontains': 'METRO COMBS'}, 'is_primary': True},
    'New Barber.png': {'query': {'name': 'NEW BARBER PL/GW/SHELL'}, 'is_primary': True},
    'Ola.png': {'query': {'name': 'OLA PEARL/GW/ALM'}, 'is_primary': True},
    'Opel.png': {'query': {'name': 'OPEL TC PL/GW/TOM'}, 'is_primary': True},
    'Oppo Print.png': {'query': {'name': 'OPPO PRINT'}, 'is_primary': True},
    'Oppo.png': {'query': {'name': 'OPPO PEARL'}, 'is_primary': True},
    'Pushpa Set Pearl.png': {'query': {'name': 'PUSHPA SET PEARL'}, 'is_primary': True, 'color': 'PEARL'},
    'Pushpa Set Shell.png': {'query': {'name': 'PUSHPA SET SHELL'}, 'is_primary': True, 'color': 'SHELL'},
    'Queen.png': {'query': {'name__icontains': 'QUEEN PL/SHELL'}, 'is_primary': True},
    'Ring Handle.png': {'query': {'name__icontains': 'RING HANDLE'}, 'is_primary': True},
    'Rio.png': {'query': {'name': 'RIO PL/GW/MILKY'}, 'is_primary': True},
    'Royal.png': {'query': {'name': 'ROYAL PL/GW/SHELL/DC'}, 'is_primary': True},
    'Ruby Handle.png': {'query': {'name__icontains': 'RUBY HANDLE'}, 'is_primary': True},
    'Samsung.png': {'query': {'name__icontains': 'SAMSUNG PL/GW'}, 'is_primary': True},
    'Santro.png': {'query': {'name': 'SANTRO BLACK'}, 'is_primary': True},
    'Simbha.png': {'query': {'name__icontains': 'SIMBA PL/ICE'}, 'is_primary': True},
    'Small Cartier.png': {'query': {'name__icontains': 'SMALL CARTER'}, 'is_primary': True},
    'Small Chapta 1.png': {'query': {'name': 'SMALL CHAPTA'}, 'is_primary': True, 'color': 'PL'},
    'Small Chapta 2.png': {'query': {'name': 'SMALL CHAPTA'}, 'is_primary': False, 'color': 'FL'},
    'Solar Hair Brush 1.png': {'query': {'name': 'SOLAR HAIR BRUSH AL/M/TP'}, 'is_primary': False, 'color': 'ALM'},
    'Solar Hair Brush 2.png': {'query': {'name': 'SOLAR HAIR BRUSH C'}, 'is_primary': True, 'color': 'PL'},
    'Solar Hair Brush 3.png': {'query': {'name': 'SOLAR HAIR BRUSH AL/M/TP'}, 'is_primary': False, 'color': 'TP'},
    'Sony.png': {'query': {'name__icontains': 'SONY PL/GW'}, 'is_primary': True},
    'Star.png': {'query': {'name': 'STAR PL/GW/SHELL'}, 'is_primary': True},
    'Sultan 1.png': {'query': {'name': 'SULTAN K.R.T/G.W'}, 'is_primary': True, 'color': 'KRT'},
    'Sultan 2.png': {'query': {'name': 'SULTAN K.R.T/G.W'}, 'is_primary': False, 'color': 'GW'},
    'Sumo Handle.png': {'query': {'name__icontains': 'SUMO HANDLE'}, 'is_primary': True},
    'Sunflower.png': {'query': {'name__icontains': 'SUNFLOWER'}, 'is_primary': True},
    'Sunrise 1.png': {'query': {'name': 'SUNRISE IVRY/TM'}, 'is_primary': True, 'color': 'IVR'},
    'Sunrise 2.png': {'query': {'name': 'SUNRISE IVRY/TM'}, 'is_primary': False, 'color': 'TOM'},
    'Sunsilk Handle Print.png': {'query': {'name': 'SUNSILK HANDLE PRINT'}, 'is_primary': True},
    'Sunsilk Handle.png': {'query': {'name': 'SUNSILK HANDLE PL/ICE/SHELL'}, 'is_primary': True},
    'Superman.png': {'query': {'name__icontains': 'SUPERMAN'}, 'is_primary': True},
    'Surya.png': {'query': {'name__icontains': 'SURYA PL/GW'}, 'is_primary': True},
    'Tail Comb.png': {'query': {'name': 'TAIL PL/MILKY/AL/SHELL'}, 'is_primary': True},
    'Taj Print.png': {'query': {'name': 'TAJ PRINT'}, 'is_primary': True},
    'Taj.png': {'query': {'name': 'TAJ PL/ICE/GW'}, 'is_primary': True},
    'Tiger Handle.png': {'query': {'name__icontains': 'TIGER HANDLE'}, 'is_primary': True},
    'Tiptop 1.png': {'query': {'name__icontains': 'TIP TOP'}, 'is_primary': True, 'color': 'FL'},
    'Tiptop 2.png': {'query': {'name__icontains': 'TIP TOP'}, 'is_primary': False, 'color': 'ALM'},
    'Titan.png': {'query': {'name__icontains': 'TITAN COMB'}, 'is_primary': True},
    'Top10.png': {'query': {'name__icontains': 'TOP-TEN'}, 'is_primary': True},
    'Tridev.png': {'query': {'name__icontains': 'TRIDEV PL/GW'}, 'is_primary': True},
    'Vivo Handle.png': {'query': {'name__icontains': 'VIVO HANDLE'}, 'is_primary': True},
    'Yahoo.png': {'query': {'name__icontains': 'YAHOO PL/GW'}, 'is_primary': True},
    'Zamzam.png': {'query': {'name__icontains': 'ZAM ZAM PL/ALM'}, 'is_primary': True},
    'Zee Handle.png': {'query': {'name': 'ZEE HANDLE PL/SHELL'}, 'is_primary': True},
    'Zee Print.png': {'query': {'name': 'ZEE PRINT'}, 'is_primary': True},
    'Zee.png': {'query': {'name': 'ZEE PEARL'}, 'is_primary': True},
}

# Also map sibling products that share the same mold / comb model
SIBLING_MAPPINGS = [
    # 5" Hole
    ({'name': 'SOLAR 5" HOLE ACT'}, '5in Hole.png'),
    # 5" Handle
    ({'name': 'SOLAR 5" HANDLE ACT'}, '5in Handle.png'),
    # 5" Maskachaska pearl vs general
    ({'name': '5" MXC (MASKA CHASKA) PEARL'}, '5in Maskachaska.png'),
    # 5" Rio vs Rio 9"
    ({'name': 'SOLAR 5" RIO PL/TP'}, '5in Rio.png'),
    # 5" Lovely Handle
    ({'name': '5" LOVELY HANDLE PL/GW/ALM'}, '5in Lovely Handle.png'),
    # 5" Ola
    ({'name': '5" OLA PL/GW'}, 'Ola.png'),
    # 888 Prime variants
    ({'name': '888 PRIME PEARL BOX'}, '888 Prime.png'),
    ({'name': '888 PRIME PL/GW/ALM'}, '888 Prime.png'),
    # 999 Maharaja Pearl variants
    ({'name': '999 MAHARAJA SHELL'}, 'Maharaja 999 Pearl.png'),
    # 888 Maharaja TP
    ({'name': '888 MAHARAJA T.P'}, '888 Maharaja Pearl.png'),
    # Santro Pearl
    ({'name': 'SANTRO PEARL'}, 'Santro.png'),
    ({'name': 'MUAWAIYA SANTRO'}, 'Santro.png'),
    # Pushpa Set Almond
    ({'name': 'PUSHPA SET ALMOND'}, 'Pushpa Set Pearl.png'),
    # Opel TC Shell
    ({'name': 'OPEL TC SHELL'}, 'Opel.png'),
    # 2 IN 1 IN OPEC -> C4 OPEC
    ({'name': '2 IN 1 IN OPEC'}, '5in C4 Opec 1.png'),
    # Muawaiya Tail Combs
    ({'name': 'MUAWAIYA TAIL COMBS'}, 'Tail Comb.png'),
    # Solar Hair Brush AL/M/TP
    ({'name': 'SOLAR HAIR BRUSH AL/M/TP'}, 'Solar Hair Brush 1.png'),
]


def run_image_connection():
    print("[*] Starting Product Image Connection Pipeline...")
    
    # 1. Copy all 147 source images to media/products/
    copied_count = 0
    saved_paths = {}  # original_filename -> relative media path ("products/...")
    
    for src_file in SOURCE_DIR.glob("*.png"):
        clean_name = f"solar_{slugify(src_file.stem)}.png"
        target_file = TARGET_MEDIA_DIR / clean_name
        shutil.copy2(src_file, target_file)
        # Also copy with original name to guarantee 100% resolution either way
        target_orig = TARGET_MEDIA_DIR / src_file.name
        shutil.copy2(src_file, target_orig)
        
        saved_paths[src_file.name] = f"products/{clean_name}"
        copied_count += 1
        
    print(f"[+] Copied {copied_count} PNG assets to media/products/")

    # 2. Build Composite Showcase Images for Multi-piece Comb Sets
    composites = {}
    
    # 4" Weston Opec (4 colors)
    weston_files = [SOURCE_DIR / f"4in Weston Opec {i}.png" for i in range(1, 5)]
    weston_comp_file = TARGET_MEDIA_DIR / "solar_weston_4_inch_composite.png"
    create_side_by_side_composite(weston_files, weston_comp_file, spacing=14)
    composites["WESTON_4"] = f"products/{weston_comp_file.name}"
    
    # 5" C4 Opec (3 colors)
    c4_files = [SOURCE_DIR / f"5in C4 Opec {i}.png" for i in range(1, 4)]
    c4_comp_file = TARGET_MEDIA_DIR / "solar_c4_opec_composite.png"
    create_side_by_side_composite(c4_files, c4_comp_file, spacing=14)
    composites["C4_OPEC"] = f"products/{c4_comp_file.name}"

    # Solar Hair Brush (3 colors)
    brush_files = [SOURCE_DIR / f"Solar Hair Brush {i}.png" for i in range(1, 4)]
    brush_comp_file = TARGET_MEDIA_DIR / "solar_hair_brush_composite.png"
    create_side_by_side_composite(brush_files, brush_comp_file, spacing=16)
    composites["HAIR_BRUSH"] = f"products/{brush_comp_file.name}"

    # 3. Associate images with Database Products
    updated_products = set()
    
    for fn, rule in PRIMARY_MAPPINGS.items():
        q = rule['query']
        is_primary = rule.get('is_primary', True)
        color_code = rule.get('color')
        
        rel_path = saved_paths[fn]
        abs_url = f"/media/{rel_path}"
        
        prods = list(Product.objects.filter(**q, is_active=True, soft_deleted=False))
        if not prods:
            print(f"[!] Warning: No product found for query {q}")
            continue
            
        for prod in prods:
            gallery = list(prod.gallery_images or [])
            color_map = dict(prod.color_images or {})
            
            if abs_url not in gallery:
                gallery.append(abs_url)
                
            if color_code:
                color_map[color_code] = abs_url
                
            prod.gallery_images = gallery
            prod.color_images = color_map
            
            # Set primary photo
            if is_primary or not prod.photo:
                prod.photo.name = rel_path
                prod.image_url = abs_url
                
            prod.save()
            updated_products.add(prod.id)

    # 4. Attach Composites to Composite Products as Primary Showcase
    weston_prods = Product.objects.filter(name__icontains="WESTON 4", is_active=True, soft_deleted=False)
    for wp in weston_prods:
        wp.photo.name = composites["WESTON_4"]
        wp.image_url = f"/media/{composites['WESTON_4']}"
        gallery = [f"/media/{composites['WESTON_4']}"] + [g for g in wp.gallery_images if g != f"/media/{composites['WESTON_4']}"]
        wp.gallery_images = gallery
        wp.save()

    c4_prods = Product.objects.filter(name__icontains="C-4 OPEC", is_active=True, soft_deleted=False)
    for cp in c4_prods:
        cp.photo.name = composites["C4_OPEC"]
        cp.image_url = f"/media/{composites['C4_OPEC']}"
        gallery = [f"/media/{composites['C4_OPEC']}"] + [g for g in cp.gallery_images if g != f"/media/{composites['C4_OPEC']}"]
        cp.gallery_images = gallery
        cp.save()

    brush_prods = Product.objects.filter(name__icontains="SOLAR HAIR BRUSH", is_active=True, soft_deleted=False)
    for bp in brush_prods:
        if not bp.photo or bp.name == "SOLAR HAIR BRUSH C":
            bp.photo.name = composites["HAIR_BRUSH"]
            bp.image_url = f"/media/{composites['HAIR_BRUSH']}"
            gallery = [f"/media/{composites['HAIR_BRUSH']}"] + [g for g in bp.gallery_images if g != f"/media/{composites['HAIR_BRUSH']}"]
            bp.gallery_images = gallery
            bp.save()

    # 5. Connect Sibling Products
    for sib_query, img_filename in SIBLING_MAPPINGS:
        if img_filename in saved_paths:
            rel_path = saved_paths[img_filename]
            abs_url = f"/media/{rel_path}"
            sibs = Product.objects.filter(**sib_query, is_active=True, soft_deleted=False)
            for s in sibs:
                s.photo.name = rel_path
                s.image_url = abs_url
                if abs_url not in (s.gallery_images or []):
                    s.gallery_images = [abs_url] + (s.gallery_images or [])
                s.save()
                updated_products.add(s.id)

    print(f"\n[SUCCESS] Successfully enriched {len(updated_products)} Product records with high-res photos, gallery variants, and color mappings!")

if __name__ == '__main__':
    run_image_connection()
