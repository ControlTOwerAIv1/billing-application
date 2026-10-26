import os
import re
import json
import urllib.request
import urllib.parse
from html import unescape
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings
from apps.core.models import Product

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

ALIASES = {
    'PUSPA': 'PUSHPA',
    'CARTIER': 'CARTER',
    'AMAZONE': 'AMAZON',
    'C4': 'C 4',
    'RED GOLD': 'REDGOLD',
    'BEAUTY TAJ PRINT': 'TAJ PRINT',
}

GENERIC_WORDS = {'COMB', 'COMBS', 'COLLECTION', 'INCH', 'PRODUCT', 'PRODUCTS', 'SERIES'}

def clean_text(s: str) -> str:
    if not s:
        return ""
    s = unescape(s).upper()
    s = s.replace('&#8243;', ' INCH ').replace('″', ' INCH ').replace('"', ' INCH ').replace("'", "")
    s = s.replace('&AMP;', '&').replace('&', ' & ')
    for k, v in ALIASES.items():
        s = re.sub(rf'\b{re.escape(k)}\b', v, s)
    s = re.sub(r'[^A-Z0-9\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[^\w\-_\.]', '_', name)
    return re.sub(r'__+', '_', name).strip('_')

def download_image(url: str, dest_path: Path, timeout: int = 15) -> bool:
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        # Parse URL properly in case of special characters
        parts = urllib.parse.urlsplit(url)
        safe_path = urllib.parse.quote(parts.path)
        safe_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, safe_path, parts.query, parts.fragment))
        
        req = urllib.request.Request(safe_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = resp.read()
                if len(data) > 0:
                    with open(dest_path, 'wb') as f:
                        f.write(data)
                    return True
        return False
    except Exception as e:
        return False

class Command(BaseCommand):
    help = "Download product images from hindustanplast.in WooCommerce API and save locally in media/products against matching products."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview matches and actions without downloading or modifying database.'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-download and overwrite existing local image files.'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limit the number of products processed.'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        limit = options['limit']

        media_products_dir = Path(settings.MEDIA_ROOT) / "products"
        if not dry_run:
            media_products_dir.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.NOTICE("Fetching product catalog from https://hindustanplast.in/wp-json/wc/store/v1/products..."))
        
        wc_products = []
        page = 1
        while True:
            url = f"https://hindustanplast.in/wp-json/wc/store/v1/products?per_page=100&page={page}"
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    items = json.loads(resp.read().decode('utf-8'))
                    if not items:
                        break
                    wc_products.extend(items)
                    page += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Finished fetching at page {page}: {e}"))
                break

        wc_with_imgs = [p for p in wc_products if p.get('images')]
        self.stdout.write(self.style.SUCCESS(f"Fetched {len(wc_products)} total products ({len(wc_with_imgs)} with images)."))

        local_products = list(Product.objects.all())
        self.stdout.write(self.style.NOTICE(f"Total local products in database: {len(local_products)}"))

        # Pre-process local products
        local_cache = []
        for lp in local_products:
            cname = clean_text(lp.name)
            tokens = set(cname.split())
            local_cache.append({
                'obj': lp,
                'name': lp.name,
                'clean_name': cname,
                'tokens': tokens,
                'group': (lp.group_alias or '').upper(),
                'cat': (lp.category_alias or '').upper(),
            })

        matched_count = 0
        updated_products_count = 0
        downloaded_count = 0
        skipped_download_count = 0
        failed_download_count = 0

        if limit > 0:
            wc_with_imgs = wc_with_imgs[:limit]

        for wc in wc_with_imgs:
            raw_name = unescape(wc.get('name', ''))
            wc_slug = wc.get('slug', '')
            clean_wc = clean_text(raw_name)
            wc_tokens = set(clean_wc.split())
            spec_tokens = {t for t in wc_tokens if t not in GENERIC_WORDS}
            
            wc_cat_str = " ".join([c.get('name', '') for c in wc.get('categories', [])]).upper()
            is_wc_comb = any(w in wc_cat_str for w in ['COMB', 'POCKET', 'COLLECTION', 'SHAMPOO', 'HANDLE', 'TOOTH'])
            is_wc_cutlery = any(w in wc_cat_str for w in ['SCISSOR', 'CUTTER', 'PIN', 'ACCESSORIES'])

            # Find matching products
            scored_matches = []
            for item in local_cache:
                lp_tokens = item['tokens']
                clean_lp = item['clean_name']
                lp_group = item['group']

                score = 0
                # Exact clean match
                if clean_wc == clean_lp:
                    score = 150
                elif spec_tokens and spec_tokens.issubset(lp_tokens):
                    score = 100 - (len(lp_tokens) - len(spec_tokens))
                elif len(wc_tokens.intersection(lp_tokens)) >= 2 and len(wc_tokens.intersection(lp_tokens)) / len(wc_tokens) >= 0.7:
                    score = 75

                if score > 0:
                    # Category affinity bonus / penalty
                    if is_wc_comb:
                        if lp_group in ['SOLAR COMB', 'COMBS']:
                            score += 25
                        elif lp_group in ['POWDER PUF', 'CUTLERY', 'STATIONERY']:
                            score -= 60
                    elif is_wc_cutlery:
                        if lp_group in ['CUTLERY']:
                            score += 25
                        elif lp_group in ['SOLAR COMB', 'COMBS', 'POWDER PUF']:
                            score -= 60

                    if score >= 60:
                        scored_matches.append((item['obj'], score))

            if not scored_matches:
                self.stdout.write(self.style.WARNING(f"[UNMATCHED] WC: '{raw_name}' ({wc_slug})"))
                continue

            matched_count += 1
            scored_matches.sort(key=lambda x: x[1], reverse=True)
            top_score = scored_matches[0][1]
            selected_local_products = [m[0] for m in scored_matches if m[1] >= max(top_score - 10, 70)]

            # Main image
            main_img_url = wc['images'][0]['src']
            ext = os.path.splitext(urllib.parse.urlparse(main_img_url).path)[1] or ".jpg"
            if ext.lower() not in ['.jpg', '.jpeg', '.png', '.webp']:
                ext = ".jpg"
                
            base_filename = sanitize_filename(wc_slug or clean_wc.lower().replace(' ', '_'))
            main_filename = f"{base_filename}{ext}"
            main_local_path = media_products_dir / main_filename

            # Gallery images
            gallery_filenames = []
            for idx, g_img in enumerate(wc['images'][1:], start=1):
                g_url = g_img['src']
                g_ext = os.path.splitext(urllib.parse.urlparse(g_url).path)[1] or ".jpg"
                g_filename = f"{base_filename}_gallery_{idx}{g_ext}"
                gallery_filenames.append((g_url, g_filename))

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[DRY-RUN] WC: '{raw_name}' -> Matched {len(selected_local_products)} items: "
                        f"{', '.join([p.name for p in selected_local_products[:3]])}"
                        f"{'...' if len(selected_local_products) > 3 else ''} | Image: {main_filename}"
                    )
                )
                continue

            # Download Main Image
            if not main_local_path.exists() or force:
                success = download_image(main_img_url, main_local_path)
                if success:
                    downloaded_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f"Failed to download: {main_img_url}"))
                    failed_download_count += 1
            else:
                skipped_download_count += 1

            # Download Gallery Images
            saved_gallery_urls = [f"/media/products/{main_filename}"]
            for g_url, g_fname in gallery_filenames:
                g_path = media_products_dir / g_fname
                if not g_path.exists() or force:
                    g_success = download_image(g_url, g_path)
                    if g_success:
                        downloaded_count += 1
                        saved_gallery_urls.append(f"/media/products/{g_fname}")
                    else:
                        failed_download_count += 1
                else:
                    skipped_download_count += 1
                    saved_gallery_urls.append(f"/media/products/{g_fname}")

            # Update database records
            photo_rel_path = f"products/{main_filename}"
            image_url_path = f"/media/products/{main_filename}"

            for prod in selected_local_products:
                prod.photo = photo_rel_path
                prod.image_url = image_url_path
                prod.gallery_images = saved_gallery_urls
                prod.save(update_fields=['photo', 'image_url', 'gallery_images'])
                updated_products_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"[SAVED] WC: '{raw_name}' -> Saved to {main_filename} & updated {len(selected_local_products)} products."
                )
            )

        self.stdout.write(self.style.NOTICE("=" * 60))
        self.stdout.write(self.style.SUCCESS(f"Finished!"))
        self.stdout.write(f"Matched WC items: {matched_count} / {len(wc_with_imgs)}")
        if not dry_run:
            self.stdout.write(f"Updated local DB products: {updated_products_count}")
            self.stdout.write(f"Downloaded images: {downloaded_count}")
            self.stdout.write(f"Reused existing files: {skipped_download_count}")
            self.stdout.write(f"Failed downloads: {failed_download_count}")
        self.stdout.write(self.style.NOTICE("=" * 60))
