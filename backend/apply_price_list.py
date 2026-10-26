"""
Solar Price List (01.08.2026) Importer & Synchronizer
Applies authentic GRS rates (Carton Price) and DZN rates (Loose Price)
directly to Product records in the database.
"""

import os
import sys
import re
from pathlib import Path
from decimal import Decimal

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'orderbot.settings')

import django
django.setup()

from apps.core.models import Product
import fitz

PDF_PATH = BASE_DIR / "Solar_Price_List_2026.pdf"

def extract_pdf_entries():
    doc = fitz.open(PDF_PATH)
    page = doc[0]
    tab_finder = page.find_tables()
    table = tab_finder.tables[0]
    raw_rows = table.extract()

    col_groups = [(0, 1, 2, 3, 4), (5, 6, 7, 8, 9), (10, 11, 12, 13, 14)]
    entries = []
    
    for r in raw_rows:
        for ref_i, it_i, col_i, grs_i, dzn_i in col_groups:
            it = r[it_i]
            if not it:
                continue
            it_clean = it.strip().replace('\n', ' ')
            if it_clean in ['ITEM', '5" & POCKET', '8" COLLECTION', '9" PREMIUM COLLECTION', 'HINDUSTAN PLAST', 'PRICE LIST 01.08.2026']:
                continue
            ref = (r[ref_i] or '').strip().replace('\n', '')
            col = (r[col_i] or '').strip().replace('\n', ' ')
            grs = (r[grs_i] or '').strip().replace('\n', '')
            dzn = (r[dzn_i] or '').strip().replace('\n', '')
            
            def to_f(v):
                c = re.sub(r'[^\d\.]', '', v)
                return float(c) if c else None
                
            g_val = to_f(grs)
            d_val = to_f(dzn)
            
            # Special case for HAIR BRUSH where DZN is 300 / GRS is 3600
            if 'HAIR BRUSH' in it_clean.upper():
                d_val = 300.0
                g_val = 3600.0
                
            if g_val or d_val:
                if g_val and not d_val:
                    d_val = round(g_val / 12.0, 2)
                elif d_val and not g_val:
                    g_val = round(d_val * 12.0, 2)
                entries.append({
                    'ref': ref,
                    'item': it_clean,
                    'colour': col,
                    'grs': Decimal(str(g_val)),
                    'dzn': Decimal(str(d_val))
                })
    return entries

# Explicit mapping dictionary for every Ref and item name in the PDF
# Each mapping defines queries to locate database products
EXPLICIT_RULES = [
    # 5" & POCKET
    {'ref': '1', 'names': ['SOLAR 5" REDGOLD', 'SOLAR 5" PL/BLACK'], 'grs': 162.0, 'dzn': 13.5},
    {'ref': '2', 'names': ['SOLAR 5" HOLE PL', 'SOLAR 5" HOLE ACT'], 'grs': 198.0, 'dzn': 16.5},
    {'ref': '3', 'names': ['SOLAR 5" BUNTY PL', '5" BUNTY'], 'grs': 198.0, 'dzn': 16.5},
    {'ref': '4', 'names': ['5" LOVELY HANDLE', '5" LOVELY'], 'grs': 198.0, 'dzn': 16.5},
    {'ref': '5', 'names': ['SOLAR 5" PEARL'], 'grs': 198.0, 'dzn': 16.5},
    {'ref': '6', 'names': ['SOLAR D.HOLE PL/GW', 'SOLAR 5" CLIP PL/GW/ALM', '7" D.HOLE'], 'grs': 228.0, 'dzn': 19.0},
    {'ref': '8', 'names': ['SOLAR 5" RIO PL/TP', 'RIO PL/GW/MILKY'], 'grs': 228.0, 'dzn': 19.0},
    {'ref': '9', 'names': ['SOLAR 5" HANDLE PL', 'SOLAR 5" HANDLE ACT'], 'grs': 234.0, 'dzn': 19.5},
    {'ref': '10', 'names': ['PURNIMA 5" 2 IN 1', 'PURNIMA 5" 555', 'PURNIMA 5" DANBY', 'PURNIMA 5" HOLE'], 'grs': 234.0, 'dzn': 19.5},
    {'ref': '11', 'names': ['C-5 PL/GW/ALM', 'C-5'], 'grs': 228.0, 'dzn': 19.0},
    {'ref': '12', 'names': ['5" MXC (MASKA CHASKA) PEARL', '5" CROSS HANDLE PL/GW/ALM'], 'grs': 270.0, 'dzn': 22.5},
    {'ref': '13', 'names': ['C-4 OPEC', '2 IN 1 IN OPEC'], 'grs': 102.0, 'dzn': 8.5},
    {'ref': '14', 'names': ['WESTON 4" OPEC', 'WESTON 4"'], 'grs': 72.0, 'dzn': 6.0},
    {'ref': '15', 'names': ['DOLLAR CLIP COMBS PL', 'DOLLAR CLIP'], 'grs': 444.0, 'dzn': 37.0},
    
    # TOOTH COMBS
    {'ref': '16', 'names': ['SUNRISE IVRY/TM'], 'grs': 192.0, 'dzn': 16.0},
    {'ref': '17', 'names': ['SMALL CARTER IVRY/PL/TOM', 'SMALL CARTER'], 'grs': 270.0, 'dzn': 22.5},
    {'ref': '18', 'names': ['CAMEL TOOTH COMB'], 'grs': 360.0, 'dzn': 30.0},
    {'ref': '19', 'names': ['CHARMI JALI PL/SHELL/TOM'], 'grs': 360.0, 'dzn': 30.0},
    {'ref': '20', 'names': ['AIWA PL/GW/TOM/IVR', 'AIWA SHELL/ K.R.T', 'QUEEN PL/SHELL/IVRY'], 'grs': 360.0, 'dzn': 30.0},
    {'ref': '21', 'names': ['NAIRA'], 'grs': 360.0, 'dzn': 30.0},
    {'ref': '22', 'names': ['BIG CARTER TOOTH COMB', 'BIG CARTER'], 'grs': 360.0, 'dzn': 30.0},
    {'ref': '23', 'names': ['TRIO SMALL TOOTH COMB', 'TRIO BIG TOOTH COMB'], 'grs': 360.0, 'dzn': 30.0},
    {'ref': '24', 'names': ['POLO TC', 'POLO'], 'grs': 390.0, 'dzn': 32.5},
    {'ref': '25', 'names': ['KING CARTER TOOTH COMB', 'KING CARTER'], 'grs': 444.0, 'dzn': 37.0},
    {'ref': '26', 'names': ['BIG HEARTY PL/GW/SHELL'], 'grs': 444.0, 'dzn': 37.0},
    {'ref': '27', 'names': ['KIT-KAT PL/SHELL/TOM', '501/555'], 'grs': 444.0, 'dzn': 37.0},
    {'ref': '28', 'names': ['SONY PL/GW/SHELL', 'JULIE PL/GW/SHELL'], 'grs': 444.0, 'dzn': 37.0},
    {'ref': '29', 'names': ['STAR PL/GW/SHELL', 'CASSETE TC'], 'grs': 444.0, 'dzn': 37.0},
    {'ref': '30', 'names': ['OPEL TC PL/GW/TOM', 'OPEL TC SHELL'], 'grs': 528.0, 'dzn': 44.0},
    {'ref': '31', 'names': ['JUMBO PL/GW/SHELL'], 'grs': 576.0, 'dzn': 48.0},
    {'ref': '32', 'names': ['TIP TOP FL/ALM/MILKY/TRI'], 'grs': 660.0, 'dzn': 55.0},
    {'ref': '32A', 'names': ['KRAMER'], 'grs': 528.0, 'dzn': 44.0},

    # 7" COLLECTION
    {'ref': '33', 'names': ['077 RED GOLD BOX', '077 RED GOLD'], 'grs': 180.0, 'dzn': 15.0},
    {'ref': '34', 'names': ['7" REDGOLD', '7"/777'], 'grs': 228.0, 'dzn': 19.0},
    {'ref': '35', 'names': ['BARBER PL/ALM/GW'], 'grs': 240.0, 'dzn': 20.0},
    {'ref': '36', 'names': ['7" D.HOLE PEARL'], 'grs': 348.0, 'dzn': 29.0},
    {'ref': '37', 'names': ['NEW BARBER PL/GW/SHELL'], 'grs': 348.0, 'dzn': 29.0},
    {'ref': '38', 'names': ['TAIL PL/MILKY/AL/SHELL', 'MUAWAIYA TAIL COMBS'], 'grs': 348.0, 'dzn': 29.0},
    {'ref': '39', 'names': ['7" LOVELY HANDLE PL/GW'], 'grs': 348.0, 'dzn': 29.0},
    {'ref': '40', 'names': ['7" WONDER PL/SHELL'], 'grs': 324.0, 'dzn': 27.0},
    {'ref': '41', 'names': ['7" PEARL/GW/FM/TOM'], 'grs': 348.0, 'dzn': 29.0},
    {'ref': '42', 'names': ['8" WONDER PL/SHELL', '9" WONDER PL/SHELL'], 'grs': 384.0, 'dzn': 32.0},

    # SET COLLECTION
    {'ref': '43', 'names': ['SOLAR 3PC PL SET', 'SOLAR CHUNA DABBI'], 'grs': 126.0, 'dzn': 10.5},
    {'ref': '44', 'names': ['PUSHPA SET SHELL'], 'grs': 162.0, 'dzn': 13.5},
    {'ref': '45', 'names': ['PUSHPA SET PEARL'], 'grs': 216.0, 'dzn': 18.0},
    {'ref': '46', 'names': ['PUSHPA SET ALMOND'], 'grs': 186.0, 'dzn': 15.5},

    # 8" COLLECTION
    {'ref': '47', 'names': ['SANTRO BLACK', 'MUAWAIYA SANTRO'], 'grs': 420.0, 'dzn': 35.0},
    {'ref': '48', 'names': ['YAHOO PL/GW/DC'], 'grs': 420.0, 'dzn': 35.0},
    {'ref': '49', 'names': ['VIRAT PL', 'VIRAT'], 'grs': 528.0, 'dzn': 44.0},
    {'ref': '50', 'names': ['OPPO PEARL', 'DELITE'], 'grs': 528.0, 'dzn': 44.0},
    {'ref': '51', 'names': ['TITAN COMB PL/MILKY', '8" ROLEX PL/MILKY'], 'grs': 528.0, 'dzn': 44.0},
    {'ref': '52', 'names': ['JIO PEARL/MILKY', 'CROMA PL/MILKY'], 'grs': 528.0, 'dzn': 44.0},
    {'ref': '54', 'names': ['888 PRIME (M) PEARL FOLDER', '888 PRIME(M) REDGOLD FOLDER'], 'grs': 600.0, 'dzn': 50.0},

    # 9" BOX COLLECTION
    {'ref': '55', 'names': ['9" REDGOLD/BLK MIX'], 'grs': 516.0, 'dzn': 43.0},
    {'ref': '56', 'names': ['9" BEST BOX', '9" BEST FOLDER'], 'grs': 600.0, 'dzn': 50.0},
    {'ref': '57', 'names': ['9" BINGO'], 'grs': 780.0, 'dzn': 65.0},
    {'ref': '58', 'names': ['9" PEARL BOX', '9" PEARL FOLDER'], 'grs': 780.0, 'dzn': 65.0},

    # MAHARAJA COLLECTION
    {'ref': '59', 'names': ['MAHARAJA BARBER PL/GW/ALM'], 'grs': 450.0, 'dzn': 37.5},
    {'ref': '60', 'names': ['888 MAHARAJA PEARL BOX', '888 MAHARAJA T.P'], 'grs': 804.0, 'dzn': 67.0},
    {'ref': '61', 'names': ['999 MAHARAJA MIX R/B BOX'], 'grs': 804.0, 'dzn': 67.0},
    {'ref': '62', 'names': ['999 MAHARAJA PEARL BOX', '999 MAHARAJA SHELL'], 'grs': 960.0, 'dzn': 80.0},

    # FINGER COMBS
    {'ref': '63', 'names': ['SMALL CHAPTA'], 'grs': 252.0, 'dzn': 21.0},
    {'ref': '64', 'names': ['BIG-CHAPTA G/W', 'BIG-CHAPTA'], 'grs': 360.0, 'dzn': 30.0},
    {'ref': '65', 'names': ['INDIAN IDOL GW/DC', 'INDIAN IDOL'], 'grs': 480.0, 'dzn': 40.0},
    {'ref': '66', 'names': ['SULTAN K.R.T/G.W', 'SULTAN'], 'grs': 672.0, 'dzn': 56.0},
    {'ref': '67', 'names': ['SHARK TANK'], 'grs': 672.0, 'dzn': 56.0},

    # HANDLE COLLECTION
    {'ref': '68', 'names': ['FLOWER HANDLE PL/GW'], 'grs': 624.0, 'dzn': 52.0},
    {'ref': '69', 'names': ['DOLPHINE HANDLE PL/ICE'], 'grs': 624.0, 'dzn': 52.0},
    {'ref': '70', 'names': ['DRESSING HANDLE PL/GW/SHELL'], 'grs': 624.0, 'dzn': 52.0},
    {'ref': '71', 'names': ['RUBY HANDLE PL/MILKY/ICE'], 'grs': 624.0, 'dzn': 52.0},
    {'ref': '72', 'names': ['COSMO HANDLE FL/MILKY'], 'grs': 744.0, 'dzn': 62.0},
    {'ref': '73', 'names': ['JOLLY HANDLE PL/GW/ICE/ALM'], 'grs': 744.0, 'dzn': 62.0},
    {'ref': '74', 'names': ['TIGER HANDLE PL/MILKY'], 'grs': 744.0, 'dzn': 62.0},
    {'ref': '75', 'names': ['VIVO HANDLE PL/ICE'], 'grs': 744.0, 'dzn': 62.0},
    {'ref': '76', 'names': ['CLASSIC HANDLE'], 'grs': 744.0, 'dzn': 62.0},
    {'ref': '77', 'names': ['RING HANDLE PL/ICE/AL'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '78', 'names': ['SUNSILK HANDLE PL/ICE/SHELL'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '79', 'names': ['CROSS HANDLE PL/ICE'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '80', 'names': ['FANCY HANDLE PL/SHELL/ICE'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '81', 'names': ['20-20 HANDLE PL/ALM'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '82', 'names': ['ELEGANT HANDLE PL/DC'], 'grs': 840.0, 'dzn': 70.0},
    {'ref': '83', 'names': ['SUMO HANDLE PL/ICE'], 'grs': 840.0, 'dzn': 70.0},
    {'ref': '84', 'names': ['IPL HANDLE PL/ALM/SHELL'], 'grs': 960.0, 'dzn': 80.0},
    {'ref': '85', 'names': ['AUDI FL/MILKY'], 'grs': 648.0, 'dzn': 54.0},

    # PRINT COLLECTION
    {'ref': '86', 'names': ['BEAUTY OPPO PRINT MIX', 'OPPO PRINT'], 'grs': 840.0, 'dzn': 70.0},
    {'ref': '87', 'names': ['BIG BOSS PRINT', 'TAJ PRINT'], 'grs': 1080.0, 'dzn': 90.0},
    {'ref': '88', 'names': ['BEAUTY SIMBA/BIGBOSS/FANCY PRINT BOX'], 'grs': 1080.0, 'dzn': 90.0},
    {'ref': '89', 'names': ['FANCY HANDLE PRINT', 'SUNSILK HANDLE PRINT'], 'grs': 1080.0, 'dzn': 90.0},
    {'ref': '90', 'names': ['ZEE PRINT', 'DIKOS ZEE & ZEE HANDLE PRINT'], 'grs': 1080.0, 'dzn': 90.0},

    # 9" PREMIUM COLLECTION
    {'ref': '91', 'names': ['MXC (MASKA-CHASKA) K.R.T'], 'grs': 600.0, 'dzn': 50.0},
    {'ref': '92', 'names': ['MXC (MASKA-CHASKA) PL/GW/ALM'], 'grs': 648.0, 'dzn': 54.0},
    {'ref': '93', 'names': ['MAXX PL/DC/GW/TOM'], 'grs': 648.0, 'dzn': 54.0},
    {'ref': '94', 'names': ['KIRAN PL/GW'], 'grs': 648.0, 'dzn': 54.0},
    {'ref': '95', 'names': ['HEADLINE PL/GW/AL'], 'grs': 648.0, 'dzn': 54.0},
    {'ref': '96', 'names': ['SITARA'], 'grs': 672.0, 'dzn': 56.0},
    {'ref': '97', 'names': ['SANTRO PEARL'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '98', 'names': ['HERO'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '99', 'names': ['50-50 PL/GW/SHELL/ALM', '50-50'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '100', 'names': ['CROWN PL/GW'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '101', 'names': ['BULLET PL/ICE/MILKY'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '102', 'names': ['C.C.999 PL/GW/FM'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '103', 'names': ['CUTTING PL/ICE/FM'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '104', 'names': ['INDIGO PL/GW/SHELL'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '105', 'names': ['MARUTI PL/ICE/SHELL'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '106', 'names': ['SUNFLOWER PL/ICE/FM'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '107', 'names': ['DAIMOND'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '108', 'names': ['3 IN 1 PL/GW/Shell/TOM', '3-IN-1'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '109', 'names': ['SURYA PL/GW/SHELL/FM'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '110', 'names': ['HONDA COMB 9 PL/ICE/GW'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '111', 'names': ['SIMBA PL/ICE/MILKY'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '112', 'names': ['DOLLY 9" PL/ICE/MILKY', 'BISLERI PL/GW/SHELL/'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '113', 'names': ['NOKIA G.R.T/FM'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '114', 'names': ['PRINCE'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '115', 'names': ['AMAZON'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '116', 'names': ['KIA PL/GW/SHELL'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '117', 'names': ['TRIDEV PL/GW/SHELL'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '118', 'names': ['ERTIGA PL/GW/ICE'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '119', 'names': ['RIO PL/GW/MILKY'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '120', 'names': ['TAJ PL/ICE/GW'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '121', 'names': ['OLA PEARL/GW/ALM', '5" OLA PL/GW'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '122', 'names': ['BIG BOSS PL/SHELL/GW'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '123', 'names': ['ROYAL PL/GW/SHELL/DC'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '124', 'names': ['METRO COMBS'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '125', 'names': ['LOTUS PL/GW', 'BADSHAH PL/ICE/GW'], 'grs': 792.0, 'dzn': 66.0},
    {'ref': '126', 'names': ['GALAXY PEARL'], 'grs': 828.0, 'dzn': 69.0},
    {'ref': '127', 'names': ['MAGGIE PL/ALM'], 'grs': 828.0, 'dzn': 69.0},
    {'ref': '128', 'names': ['H.P.999 PEARL/ALM'], 'grs': 828.0, 'dzn': 69.0},
    {'ref': '129', 'names': ['SUPERMAN PL/GW/SHELL/ALM'], 'grs': 960.0, 'dzn': 80.0},
    {'ref': '130', 'names': ['INNOVA PL/MILKY/SHELL'], 'grs': 960.0, 'dzn': 80.0},
    {'ref': '131', 'names': ['TOP-TEN PL/GW/TOM'], 'grs': 960.0, 'dzn': 80.0},
    {'ref': '132', 'names': ['SINGHAM PL/GW/ICE'], 'grs': 960.0, 'dzn': 80.0},
    {'ref': '133', 'names': ['SAMSUNG PL/GW/TOM'], 'grs': 1080.0, 'dzn': 90.0},
    
    # SHAMPOO COLLECTION
    {'ref': '134', 'names': ['BABY ZEE PL/ALM'], 'grs': 432.0, 'dzn': 36.0},
    {'ref': '135', 'names': ['ZEE PEARL', 'DIKOS ZEE & ZEE HANDLE PL'], 'grs': 756.0, 'dzn': 63.0},
    {'ref': '136', 'names': ['ZEE HANDLE PL/SHELL'], 'grs': 960.0, 'dzn': 80.0},
    {'ref': '137', 'names': ['ZAM ZAM PL/ALM/SHELL'], 'grs': 960.0, 'dzn': 80.0},
    {'ref': 'BRUSH', 'names': ['SOLAR HAIR BRUSH AL/M/TP', 'SOLAR HAIR BRUSH C'], 'grs': 3600.0, 'dzn': 300.0},
]

def apply_pricing():
    print("[*] Starting Price List Synchronization from 01.08.2026 Sheet...")
    updated_products = set()
    not_found = []

    for rule in EXPLICIT_RULES:
        ref = rule['ref']
        grs = Decimal(str(rule['grs']))
        dzn = Decimal(str(rule['dzn']))
        half_carton = (grs / Decimal("2.0")).quantize(Decimal("0.01"))
        
        target_names = rule['names']
        rule_matched = False
        
        for t_name in target_names:
            prods = list(Product.objects.filter(name__iexact=t_name, is_active=True, soft_deleted=0))
            if not prods:
                prods = list(Product.objects.filter(name__icontains=t_name, is_active=True, soft_deleted=0))
                
            for p in prods:
                p.base_price = dzn
                p.loose_price = dzn
                p.full_carton_price = grs
                p.half_carton_price = half_carton
                p.full_carton_quantity = 12  # 12 Dozen (1 Gross = 144 combs)
                p.save()
                updated_products.add(p.id)
                rule_matched = True
                print(f"  [+] Ref {ref:>4} | {p.name:<32} -> Loose (DZN): Rs.{dzn:>6.2f} | Carton (GRS): Rs.{grs:>7.2f}")
                
        if not rule_matched:
            not_found.append((ref, target_names))

    print(f"\n[SUMMARY] Successfully updated {len(updated_products)} products with exact PDF pricing!")
    if not_found:
        print(f"[!] Warning: {len(not_found)} rules had no matching DB product:")
        for ref, names in not_found:
            print(f"    Ref {ref}: {names}")

    # Set all products not present in the PDF to Rs. 1.00 for both loose and carton
    unlisted_products = (
        Product.objects.filter(is_active=True, soft_deleted=0)
        .exclude(id__in=updated_products)
        .exclude(sku__startswith="TEST")
        .exclude(sku__startswith="GST-TEST")
    )
    unlisted_count = unlisted_products.count()
    print(f"\n[*] Setting {unlisted_count} products not present in PDF to Rs. 1.00 (both loose & carton)...")
    
    unlisted_products.update(
        base_price=Decimal("1.00"),
        loose_price=Decimal("1.00"),
        full_carton_price=Decimal("1.00"),
        half_carton_price=Decimal("1.00"),
    )
    print(f"[+] Successfully set {unlisted_count} unlisted products to Rs. 1.00!")

if __name__ == '__main__':
    apply_pricing()
