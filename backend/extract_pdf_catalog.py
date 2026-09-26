"""
PDF Catalog Extractor & Product Enricher
Extracts high-resolution product photographs and color variant data directly
from the Solar Comb catalog PDF ('Solar-Brochure.pdf') and enriches matching
Product records in the database.
"""

import os
import sys
import re
from pathlib import Path
import fitz

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'orderbot.settings')

import django
django.setup()

from apps.core.models import Product

MEDIA_PRODUCTS_DIR = BASE_DIR / "media" / "products"
MEDIA_PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)

BROCHURE_PATH = r"C:\Users\belda\Downloads\httpsflipbook.digirich.inwp-contentuploads202307Solar-Brochure.pdf.pdf"

# Standard color tokens recognized across the catalog
COLOR_KEY = {
    'PL': 'Plain/Plastic',
    'GW': 'Glowhite',
    'ALM': 'Almond',
    'SHELL': 'Shell/Tortoise',
    'BKDC': 'Black DC',
    'TOM': 'Tomato/Red',
    'ICE': 'Ice Blue',
    'RG': 'Red Gold',
    'BLACK': 'Black',
    'BLK': 'Black',
    'ACT': 'Active',
    'FL': 'Fluorescent',
    'KRT': 'Kartik/Amber',
    'TIR': 'Tricolor',
    'TP': 'Transparent',
    'IVR': 'Ivory',
    'IVRY': 'Ivory',
    'PEARL': 'Pearl',
    'WHITE': 'White',
    'FM': 'Fast Marble',
    'BINGO': 'Bingo',
    'MILKY': 'Milky',
}

KNOWN_COLOR_TOKENS = set(COLOR_KEY.keys())

# Page-by-page mapping for pages 2 to 35
# Each entry is a list of product descriptors ordered by vertical appearance on the page
PAGE_CATALOG_MAP = {
    2: [
        {"title": '5" RED GOLD', "colors": ["RG", "BLACK"], "db_match": ["5", "REDGOLD"], "slug": "solar_5_inch_red_gold"},
        {"title": '5" HOLE', "colors": ["PL", "GW", "ACT", "BKDC", "TOM"], "db_match": ["5", "HOLE"], "slug": "solar_5_inch_hole"},
        {"title": '5" BUNTY', "colors": ["PL", "GW", "BKDC", "TOM"], "db_match": ["5", "BUNTY"], "slug": "solar_5_inch_bunty"},
        {"title": '5" LOVELY HANDLE', "colors": ["PL", "GW", "ALM", "SHELL", "BKDC", "TOM"], "db_match": ["5", "LOVELY", "HANDLE"], "slug": "solar_5_inch_lovely_handle"},
        {"title": '5" PEARL', "colors": ["PL", "GW", "BKDC", "TOM"], "db_match": ["5", "PEARL"], "slug": "solar_5_inch_pearl"},
    ],
    3: [
        {"title": '5" D. HOLE', "colors": ["PL", "GW", "ALM", "BKDC", "TOM"], "db_match": ["D.HOLE"], "slug": "solar_5_inch_d_hole"},
        {"title": '5" CLIP', "colors": ["PL", "GW", "BKDC", "TOM"], "db_match": ["5", "CLIP"], "slug": "solar_5_inch_clip"},
        {"title": '5" RIO', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["5", "RIO"], "slug": "solar_5_inch_rio"},
        {"title": '5" HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["5", "HANDLE"], "slug": "solar_5_inch_handle"},
        {"title": '5" CROSS HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["5", "CROSS", "HANDLE"], "slug": "solar_5_inch_cross_handle"},
    ],
    4: [
        {"title": '5" PURNIMA 2IN1', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["PURNIMA", "2", "1"], "slug": "solar_purnima_5_inch_2in1"},
        {"title": '5" PURNIMA DANBY', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["PURNIMA", "DANBY"], "slug": "solar_purnima_5_inch_danby"},
        {"title": '5" PURNIMA 555', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["PURNIMA", "555"], "slug": "solar_purnima_5_inch_555"},
        {"title": '5" PURNIMA HOLE', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["PURNIMA", "HOLE"], "slug": "solar_purnima_5_inch_hole"},
        {"title": '5" MASKACHASKA', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["5", "MXC"], "slug": "solar_5_inch_maskachaska"},
    ],
    5: [
        {"title": '5" C4 OPEC', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["C-4", "OPEC"], "slug": "solar_5_inch_c4_opec"},
        {"title": '4" WESTON OPEC', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["WESTON"], "slug": "solar_4_inch_weston_opec"},
    ],
    6: [
        {"title": 'SMALL CARTIER', "colors": ["IVR", "TOM", "PL", "TP"], "db_match": ["SMALL", "CARTER"], "slug": "solar_small_cartier"},
        {"title": 'BIG CARTIER', "colors": ["IVR", "TOM", "PL", "TP"], "db_match": ["BIG", "CARTER"], "slug": "solar_big_cartier"},
        {"title": 'SUNRISE', "colors": ["IVR", "TOM"], "db_match": ["SUNRISE"], "slug": "solar_sunrise"},
        {"title": 'QUEEN', "colors": ["PL", "GW", "ALM", "TP", "SHELL", "TOM", "IVR"], "db_match": ["QUEEN"], "slug": "solar_queen"},
        {"title": 'AIWA', "colors": ["PL", "GW", "ALM", "TP", "SHELL", "TOM", "IVR", "KRT"], "db_match": ["AIWA"], "slug": "solar_aiwa"},
        {"title": 'CHARMI JALI', "colors": ["PL", "SHELL", "TOM"], "db_match": ["CHARMI", "JALI"], "slug": "solar_charmi_jali"},
    ],
    7: [
        {"title": 'SONY', "colors": ["PL", "GW", "ALM", "SHELL", "TOM", "IVR"], "db_match": ["SONY"], "slug": "solar_sony"},
        {"title": 'BIG HEARTY', "colors": ["PL", "GW", "ALM", "SHELL", "TOM", "IVR"], "db_match": ["BIG", "HEARTY"], "slug": "solar_big_hearty"},
        {"title": 'STAR', "colors": ["PL", "GW", "ALM", "SHELL", "TOM", "IVR", "TP"], "db_match": ["STAR"], "slug": "solar_star"},
        {"title": 'KITKAT', "colors": ["PL", "SHELL", "TOM"], "db_match": ["KIT-KAT"], "slug": "solar_kitkat"},
        {"title": 'KING CARTIER', "colors": ["PL", "GW", "ALM", "SHELL", "TOM", "IVR"], "db_match": ["KING", "CARTER"], "slug": "solar_king_cartier"},
    ],
    8: [
        {"title": 'TIPTOP', "colors": ["FL", "TIR", "ALM", "SHELL", "TOM", "IVR"], "db_match": ["TIP", "TOP"], "slug": "solar_tiptop"},
        {"title": 'JUMBO', "colors": ["PL", "GW", "ALM", "SHELL", "TOM", "IVR"], "db_match": ["JUMBO"], "slug": "solar_jumbo"},
        {"title": 'CAMEL', "colors": ["PL", "GW", "ALM", "SHELL", "TOM", "IVR"], "db_match": ["CAMEL"], "slug": "solar_camel"},
        {"title": 'OPEL', "colors": ["PL", "GW", "TOM", "SHELL"], "db_match": ["OPEL"], "slug": "solar_opel"},
    ],
    9: [
        {"title": '077 RED GOLD', "colors": ["RG", "BLACK"], "db_match": ["077", "RED", "GOLD"], "slug": "solar_077_red_gold"},
        {"title": '7" RED GOLD', "colors": ["RG", "BLACK"], "db_match": ["7", "REDGOLD"], "slug": "solar_7_inch_red_gold"},
        {"title": 'BARBER', "colors": ["PL", "GW", "ALM", "SHELL", "TOM"], "db_match": ["BARBER"], "slug": "solar_barber"},
        {"title": '7" D. HOLE', "colors": ["PL", "GW", "TOM"], "db_match": ["7", "D.HOLE"], "slug": "solar_7_inch_d_hole"},
    ],
    10: [
        {"title": 'NEW BARBER', "colors": ["PL", "GW", "ALM", "SHELL", "BKDC", "TOM", "BLACK"], "db_match": ["NEW", "BARBER"], "slug": "solar_new_barber"},
        {"title": 'TAIL COMB', "colors": ["PL", "ALM", "SHELL", "BLACK"], "db_match": ["TAIL"], "slug": "solar_tail_comb"},
        {"title": '7" WONDER', "colors": ["PL", "ALM", "ICE", "SHELL", "TOM"], "db_match": ["7", "WONDER"], "slug": "solar_7_inch_wonder"},
        {"title": '7" LOVELY HANDLE', "colors": ["PL", "GW", "ALM", "WHITE", "SHELL", "BKDC", "TOM"], "db_match": ["7", "LOVELY"], "slug": "solar_7_inch_lovely_handle"},
        {"title": '7" INCH', "colors": ["PL", "GW", "ALM", "FM", "TOM", "SHELL"], "db_match": ["7", "PEARL"], "slug": "solar_7_inch"},
        {"title": '8" WONDER', "colors": ["PL", "GW", "ALM", "SHELL"], "db_match": ["8", "WONDER"], "slug": "solar_8_inch_wonder"},
    ],
    11: [
        {"title": 'SANTRO', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "TOM"], "db_match": ["SANTRO"], "slug": "solar_santro"},
        {"title": 'YAHOO', "colors": ["PL", "GW", "ALM", "BKDC", "TOM"], "db_match": ["YAHOO"], "slug": "solar_yahoo"},
        {"title": 'OPPO', "colors": ["PL", "GW", "ALM", "ICE", "TOM"], "db_match": ["OPPO"], "slug": "solar_oppo"},
        {"title": 'DELIGHT', "colors": ["PL", "GW", "TOM"], "db_match": ["DELITE"], "slug": "solar_delight"},
        {"title": 'TITAN', "colors": ["PL", "GW", "ALM", "ICE", "TOM"], "db_match": ["TITAN"], "slug": "solar_titan"},
    ],
    12: [
        {"title": 'RUBY HANDLE', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["RUBY"], "slug": "solar_ruby_handle"},
        {"title": 'FLOWER HANDLE', "colors": ["PL", "GW"], "db_match": ["FLOWER"], "slug": "solar_flower_handle"},
        {"title": 'DOLPHIN HANDLE', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["DOLPHINE"], "slug": "solar_dolphin_handle"},
        {"title": 'DRESSING HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["DRESSING"], "slug": "solar_dressing_handle"},
        {"title": 'COSMO HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "FL"], "db_match": ["COSMO"], "slug": "solar_cosmo_handle"},
    ],
    13: [
        {"title": 'AUDI', "colors": ["FL", "GW", "ALM", "ICE", "KRT", "BKDC"], "db_match": ["AUDI"], "slug": "solar_audi"},
        {"title": 'DOLLAR CLIP', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["DOLLAR"], "slug": "solar_dollar_clip"},
        {"title": 'VIVO HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["VIVO"], "slug": "solar_vivo_handle"},
    ],
    14: [
        {"title": 'CROSS HANDLE', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["CROSS", "HANDLE"], "slug": "solar_cross_handle_large"},
        {"title": 'FANCY HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["FANCY", "HANDLE"], "slug": "solar_fancy_handle"},
        {"title": 'TIGER HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["TIGER"], "slug": "solar_tiger_handle"},
    ],
    15: [
        {"title": '2020 HANDLE', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["20-20"], "slug": "solar_2020_handle"},
        {"title": 'SUMO HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "TOM"], "db_match": ["SUMO"], "slug": "solar_sumo_handle"},
        {"title": 'ELEGANT HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "TOM"], "db_match": ["ELEGANT"], "slug": "solar_elegant_handle"},
    ],
    16: [
        {"title": 'RING HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["RING"], "slug": "solar_ring_handle"},
        {"title": 'IPL HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC"], "db_match": ["IPL"], "slug": "solar_ipl_handle"},
        {"title": 'SUNSILK HANDLE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["SUNSILK", "HANDLE"], "slug": "solar_sunsilk_handle"},
    ],
    17: [
        {"title": '9" BEST', "colors": ["PL", "GW", "ALM", "ICE", "SHELL"], "db_match": ["9", "BEST"], "slug": "solar_9_inch_best"},
        {"title": '9" PEARL', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["9", "PEARL"], "slug": "solar_9_inch_pearl"},
        {"title": '9" RED GOLD', "colors": ["RG", "BLACK"], "db_match": ["9", "REDGOLD"], "slug": "solar_9_inch_red_gold"},
        {"title": '9" BINGO', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "TOM"], "db_match": ["9", "BINGO"], "slug": "solar_9_inch_bingo"},
    ],
    18: [
        {"title": 'MAHARAJA BARBER', "colors": ["PL", "GW", "ALM"], "db_match": ["MAHARAJA", "BARBER"], "slug": "solar_maharaja_barber"},
        {"title": 'MAHARAJA 999 MIX', "colors": ["RG", "BLACK"], "db_match": ["999", "MAHARAJA", "MIX"], "slug": "solar_maharaja_999_mix"},
        {"title": 'MAHARAJA 999 PEARL', "colors": ["PL", "SHELL"], "db_match": ["999", "MAHARAJA", "PEARL"], "slug": "solar_maharaja_999_pearl"},
    ],
    19: [
        {"title": 'MASKA CHASKA KRT', "colors": ["KRT"], "db_match": ["MXC", "K.R.T"], "slug": "solar_maskachaska_krt"},
        {"title": 'MASKA CHASKA', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["MXC", "PL"], "slug": "solar_maskachaska_regular"},
        {"title": 'MAXX', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["MAXX"], "slug": "solar_maxx"},
        {"title": 'KIRAN', "colors": ["PL", "GW"], "db_match": ["KIRAN"], "slug": "solar_kiran"},
    ],
    20: [
        {"title": '888 PRIME', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BLACK", "TOM"], "db_match": ["888", "PRIME"], "slug": "solar_888_prime"},
        {"title": 'HEADLINE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "TOM"], "db_match": ["HEADLINE"], "slug": "solar_headline"},
        {"title": 'CROWN', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["CROWN"], "slug": "solar_crown"},
        {"title": '50 50', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["50-50"], "slug": "solar_50_50"},
    ],
    21: [
        {"title": 'BULLET', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["BULLET"], "slug": "solar_bullet"},
        {"title": 'C.C.999', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["C.C.999"], "slug": "solar_cc_999"},
        {"title": 'CUTTING', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["CUTTING"], "slug": "solar_cutting"},
        {"title": 'INDIGO', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["INDIGO"], "slug": "solar_indigo"},
    ],
    22: [
        {"title": 'MARUTI', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["MARUTI"], "slug": "solar_maruti"},
        {"title": 'SUNFLOWER', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["SUNFLOWER"], "slug": "solar_sunflower"},
        {"title": 'DIAMOND', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["DAIMOND"], "slug": "solar_diamond"},
        {"title": '3 IN 1', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["3", "1"], "slug": "solar_3_in_1"},
    ],
    23: [
        {"title": 'SURYA', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["SURYA"], "slug": "solar_surya"},
        {"title": 'HONDA', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["HONDA"], "slug": "solar_honda"},
        {"title": 'DOLLY', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["DOLLY"], "slug": "solar_dolly"},
        {"title": 'SIMBHA', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["SIMBA"], "slug": "solar_simbha"},
    ],
    24: [
        {"title": 'KIA', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["KIA"], "slug": "solar_kia"},
        {"title": 'TRIDEV', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["TRIDEV"], "slug": "solar_tridev"},
        {"title": 'ERTIGA', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["ERTIGA"], "slug": "solar_ertiga"},
        {"title": 'RIO', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["RIO"], "slug": "solar_rio"},
    ],
    25: [
        {"title": 'TAJ', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["TAJ"], "slug": "solar_taj"},
        {"title": 'OLA', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["OLA"], "slug": "solar_ola"},
        {"title": 'BIGBOSS', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["BIG", "BOSS"], "slug": "solar_bigboss"},
        {"title": 'ROYAL', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["ROYAL"], "slug": "solar_royal"},
        {"title": 'SAMSUNG', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["SAMSUNG"], "slug": "solar_samsung"},
    ],
    26: [
        {"title": 'LOTUS', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["LOTUS"], "slug": "solar_lotus"},
        {"title": 'METRO', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["METRO"], "slug": "solar_metro"},
        {"title": '9" AMAZONE', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "RG", "BLK"], "db_match": ["AMAZON"], "slug": "solar_9_inch_amazone"},
        {"title": 'BADSHAH', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["BADSHAH"], "slug": "solar_badshah"},
    ],
    27: [
        {"title": '9" PEARL FOLDER', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BINGO", "TOM"], "db_match": ["9", "PEARL", "FOLDER"], "slug": "solar_9_inch_pearl_folder"},
        {"title": 'GALAXY', "colors": ["PL", "GW", "FL", "ALM"], "db_match": ["GALAXY"], "slug": "solar_galaxy"},
        {"title": 'MAGGIE', "colors": ["FL", "GW", "ALM"], "db_match": ["MAGGIE"], "slug": "solar_maggie"},
        {"title": 'H.P 999', "colors": ["FL", "GW", "ALM"], "db_match": ["H.P.999"], "slug": "solar_hp_999"},
    ],
    28: [
        {"title": 'INNOVA', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["INNOVA"], "slug": "solar_innova"},
        {"title": 'TOP10', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["TOP-TEN"], "slug": "solar_top10"},
        {"title": 'SUPERMAN', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["SUPERMAN"], "slug": "solar_superman"},
    ],
    29: [
        {"title": 'BABY ZEE', "colors": ["PL", "GW", "ALM", "ICE"], "db_match": ["BABY", "ZEE"], "slug": "solar_baby_zee"},
        {"title": 'ZEE', "colors": ["PL", "GW", "ALM", "TP", "SHELL"], "db_match": ["ZEE", "PEARL"], "slug": "solar_zee"},
        {"title": 'ZEE HANDLE', "colors": ["PL", "GW", "ALM", "TP", "SHELL"], "db_match": ["ZEE", "HANDLE"], "slug": "solar_zee_handle"},
        {"title": 'ZAMZAM', "colors": ["PL", "GW", "ALM", "ICE", "SHELL"], "db_match": ["ZAM", "ZAM"], "slug": "solar_zamzam"},
    ],
    30: [
        {"title": 'OPPO PRINT', "colors": ["PRINTED"], "db_match": ["OPPO", "PRINT"], "slug": "solar_oppo_print"},
        {"title": 'BIGBOSS PRINT', "colors": ["PRINTED"], "db_match": ["BIG", "BOSS", "PRINT"], "slug": "solar_bigboss_print"},
        {"title": 'TAJ PRINT', "colors": ["PRINTED"], "db_match": ["TAJ", "PRINT"], "slug": "solar_taj_print"},
    ],
    31: [
        {"title": 'SUNSILK HANDLE PRINT', "colors": ["PRINTED"], "db_match": ["SUNSILK", "HANDLE", "PRINT"], "slug": "solar_sunsilk_handle_print"},
        {"title": 'FANCY HANDLE PRINT', "colors": ["PRINTED"], "db_match": ["FANCY", "HANDLE", "PRINT"], "slug": "solar_fancy_handle_print"},
        {"title": 'ZEE PRINT', "colors": ["PRINTED"], "db_match": ["ZEE", "PRINT"], "slug": "solar_zee_print"},
    ],
    32: [
        {"title": 'SMALL CHAPTA', "colors": ["PL", "FL"], "db_match": ["SMALL", "CHAPTA"], "slug": "solar_small_chapta"},
        {"title": 'BIG CHAPTA', "colors": ["PL", "GW", "ALM", "BKDC", "TOM", "FL", "KRT"], "db_match": ["BIG-CHAPTA"], "slug": "solar_big_chapta"},
    ],
    33: [
        {"title": 'INDIAN IDOL', "colors": ["PL", "GW", "ALM", "BKDC", "KRT", "TOM"], "db_match": ["INDIAN", "IDOL"], "slug": "solar_indian_idol"},
        {"title": 'SULTAN', "colors": ["GW", "ALM", "ICE", "BKDC", "KRT", "TOM"], "db_match": ["SULTAN"], "slug": "solar_sultan"},
    ],
    34: [
        {"title": 'PUSHPA SET', "colors": ["PL", "GW", "ALM", "ICE", "SHELL", "BKDC", "TOM"], "db_match": ["PUSHPA"], "slug": "solar_pushpa_set"},
    ],
    35: [
        {"title": 'SOLAR HAIR BRUSH', "colors": ["TP", "PL", "ALM"], "db_match": ["HAIR", "BRUSH"], "slug": "solar_hair_brush"},
    ]
}


def run_catalog_extraction():
    print(f"Opening brochure from: {BROCHURE_PATH}")
    doc = fitz.open(BROCHURE_PATH)
    
    total_images_saved = 0
    products_updated = 0
    all_solar_products = list(Product.objects.filter(group_alias='SOLAR COMB'))
    print(f"Found {len(all_solar_products)} SOLAR COMB products in database.")
    
    for page_idx in range(1, 35):
        page_num = page_idx + 1
        page = doc[page_idx]
        
        # Extract images sorted vertically
        page_images = []
        for img_info in page.get_images():
            xref = img_info[0]
            rects = page.get_image_rects(xref)
            if rects:
                page_images.append({'xref': xref, 'y0': rects[0].y0, 'rect': rects[0]})
        page_images.sort(key=lambda x: x['y0'])
        
        descriptors = PAGE_CATALOG_MAP.get(page_num, [])
        if not descriptors:
            print(f"Page {page_num}: No descriptors mapped.")
            continue
            
        print(f"\n--- Processing Page {page_num} ({len(page_images)} images, {len(descriptors)} mapped products) ---")
        
        for i, desc in enumerate(descriptors):
            # Pick corresponding image
            img_item = page_images[i] if i < len(page_images) else page_images[-1]
            xref = img_item['xref']
            
            # Extract image bytes
            base_img = doc.extract_image(xref)
            img_bytes = base_img['image']
            ext = base_img['ext']
            
            filename = f"{desc['slug']}.{ext}"
            img_path = MEDIA_PRODUCTS_DIR / filename
            img_path.write_bytes(img_bytes)
            total_images_saved += 1
            
            relative_url = f"/media/products/{filename}"
            relative_photo = f"products/{filename}"
            colors_formatted = ", ".join(desc['colors'])
            
            # Find matching products in DB using word boundaries
            match_keywords = desc['db_match']
            matching_products = []
            for p in all_solar_products:
                name_upper = p.name.upper()
                matches_all = True
                for kw in match_keywords:
                    # check word boundary or exact token
                    pattern = r'(?<![A-Z0-9])' + re.escape(kw.upper()) + r'(?![A-Z0-9])'
                    if not re.search(pattern, name_upper):
                        matches_all = False
                        break
                if matches_all:
                    matching_products.append(p)
            
            for p in matching_products:
                p.image_url = relative_url
                p.photo = relative_photo
                p.colors = colors_formatted
                p.save()
                products_updated += 1
                print(f"  [SAVED] {p.name} (ID: {p.id}) -> Image: {relative_url}, Colors: {p.colors}")
                
    # Second pass: for any remaining products that don't have colors, extract colors from their name!
    print("\n--- Running Second Pass: Extracting color variants from Product Names for remaining items ---")
    for p in all_solar_products:
        p.refresh_from_db()
        # If colors is empty, check name for patterns like PL/GW/ALM or GW/DC
        if not p.colors:
            name_parts = re.split(r'[\s/]+', p.name.upper())
            found_colors = []
            for token in name_parts:
                clean_tok = token.strip(',.()')
                if clean_tok in KNOWN_COLOR_TOKENS and clean_tok not in found_colors:
                    found_colors.append(clean_tok)
            if found_colors:
                p.colors = ", ".join(found_colors)
                p.save()
                print(f"  [INFERRED COLOR] {p.name} -> {p.colors}")
                
    print(f"\nCompleted! Saved {total_images_saved} images. Updated database records.")

if __name__ == '__main__':
    run_catalog_extraction()
