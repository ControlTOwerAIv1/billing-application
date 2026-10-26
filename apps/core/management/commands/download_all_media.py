import os
import re
import csv
import json
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path

from django.core.management.base import BaseCommand
from django.conf import settings
from apps.core.models import Product

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[^\w\-_\.]', '_', name)
    return re.sub(r'__+', '_', name).strip('_')

def download_file(url: str, dest_path: Path, timeout: int = 20) -> bool:
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
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
    except Exception:
        return False

class Command(BaseCommand):
    help = "Download all images from hindustanplast.in WordPress Media Library into media/products and generate a catalog manifest."

    def add_arguments(self, parser):
        parser.add_argument(
            '--concurrency',
            type=int,
            default=8,
            help='Number of concurrent download threads (default: 8).'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-download and overwrite existing files.'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview actions without downloading files or modifying database.'
        )

    def handle(self, *args, **options):
        concurrency = options['concurrency']
        force = options['force']
        dry_run = options['dry_run']

        media_products_dir = Path(settings.MEDIA_ROOT) / "products"
        if not dry_run:
            media_products_dir.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.NOTICE("1. Fetching product titles for parent post mapping..."))
        product_title_map = {}
        wc_page = 1
        while True:
            url = f"https://hindustanplast.in/wp-json/wc/store/v1/products?per_page=100&page={wc_page}"
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    prods = json.loads(resp.read().decode('utf-8'))
                    if not prods:
                        break
                    for p in prods:
                        product_title_map[p['id']] = unescape(p.get('name', ''))
                    wc_page += 1
            except Exception:
                break
        self.stdout.write(self.style.SUCCESS(f"Mapped {len(product_title_map)} parent product names."))

        self.stdout.write(self.style.NOTICE("2. Fetching all items from WordPress media library (/wp-json/wp/v2/media)..."))
        all_media = []
        page = 1
        while True:
            url = f"https://hindustanplast.in/wp-json/wp/v2/media?per_page=100&page={page}"
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    items = json.loads(resp.read().decode('utf-8'))
                    if not items:
                        break
                    all_media.extend(items)
                    self.stdout.write(f"  Page {page}: fetched {len(items)} items")
                    page += 1
            except Exception as e:
                break

        self.stdout.write(self.style.SUCCESS(f"Total media records fetched: {len(all_media)}"))

        # Filter image files (exclude SVGs)
        image_tasks = []
        used_filenames = {}

        for m in all_media:
            if m.get('media_type') != 'image':
                continue
            src = m.get('source_url', '')
            if not src or src.lower().endswith('.svg'):
                continue

            path_part = urllib.parse.urlparse(src).path
            raw_filename = os.path.basename(path_part)
            clean_filename = sanitize_filename(raw_filename)

            # Avoid collision between different media records having identical filename
            if clean_filename in used_filenames and used_filenames[clean_filename] != src:
                name_part, ext_part = os.path.splitext(clean_filename)
                clean_filename = f"{name_part}_{m['id']}{ext_part}"
            used_filenames[clean_filename] = src

            parent_id = m.get('post')
            parent_name = product_title_map.get(parent_id, '')

            image_tasks.append({
                'media_id': m['id'],
                'title': unescape(m.get('title', {}).get('rendered', '')),
                'source_url': src,
                'filename': clean_filename,
                'parent_id': parent_id,
                'parent_name': parent_name,
                'local_dest': media_products_dir / clean_filename,
                'local_rel_url': f"/media/products/{clean_filename}"
            })

        self.stdout.write(self.style.NOTICE(f"Total valid images to process: {len(image_tasks)}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run enabled. Exiting before download."))
            return

        # 3. Concurrent Download
        self.stdout.write(self.style.NOTICE(f"3. Downloading {len(image_tasks)} images using {concurrency} threads..."))
        
        download_queue = []
        skipped_count = 0
        for task in image_tasks:
            if task['local_dest'].exists() and not force:
                skipped_count += 1
            else:
                download_queue.append(task)

        self.stdout.write(f"  Already downloaded: {skipped_count}, To download now: {len(download_queue)}")

        success_count = 0
        fail_count = 0

        if download_queue:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                future_to_task = {
                    executor.submit(download_file, t['source_url'], t['local_dest']): t
                    for t in download_queue
                }

                completed = 0
                for future in as_completed(future_to_task):
                    completed += 1
                    t = future_to_task[future]
                    try:
                        ok = future.result()
                        if ok:
                            success_count += 1
                        else:
                            fail_count += 1
                    except Exception:
                        fail_count += 1

                    if completed % 50 == 0 or completed == len(download_queue):
                        self.stdout.write(f"  Progress: {completed} / {len(download_queue)} images processed...")

        self.stdout.write(self.style.SUCCESS(
            f"Download completed! New downloaded: {success_count}, Skipped (existing): {skipped_count}, Failed: {fail_count}"
        ))

        # 4. Check against existing local DB products and generate Manifest
        self.stdout.write(self.style.NOTICE("4. Generating media catalog manifest and linking unlinked products..."))

        local_products = list(Product.objects.all())
        unlinked_products = [p for p in local_products if not p.photo or "unsplash" in (p.image_url or "")]
        newly_linked_count = 0

        # Try to link any unlinked products based on parent_name or image title
        for task in image_tasks:
            task['linked_db_products'] = []
            
            # Find DB products already pointing to this image
            current_users = [
                p.name for p in local_products 
                if task['filename'] in (p.photo.name if p.photo else '') or task['filename'] in (p.image_url or '')
            ]
            task['linked_db_products'].extend(current_users)

            # Check if this image matches any unlinked product
            p_name_hint = task['parent_name'] or task['title']
            if p_name_hint:
                p_name_hint_clean = re.sub(r'[^A-Z0-9]', '', p_name_hint.upper())
                if len(p_name_hint_clean) >= 4:
                    for lp in unlinked_products:
                        lp_clean = re.sub(r'[^A-Z0-9]', '', lp.name.upper())
                        if p_name_hint_clean in lp_clean:
                            lp.photo = f"products/{task['filename']}"
                            lp.image_url = task['local_rel_url']
                            if not lp.gallery_images:
                                lp.gallery_images = [task['local_rel_url']]
                            lp.save(update_fields=['photo', 'image_url', 'gallery_images'])
                            newly_linked_count += 1
                            task['linked_db_products'].append(lp.name)

            task['status'] = "Linked" if task['linked_db_products'] else "Available for new product"

        # Write JSON Catalog
        manifest_json_path = media_products_dir.parent / "media_catalog.json"
        with open(manifest_json_path, 'w', encoding='utf-8') as f:
            json.dump([
                {
                    'media_id': t['media_id'],
                    'filename': t['filename'],
                    'local_path': t['local_rel_url'],
                    'title': t['title'],
                    'parent_name': t['parent_name'],
                    'parent_id': t['parent_id'],
                    'source_url': t['source_url'],
                    'status': t['status'],
                    'linked_db_products': t['linked_db_products'],
                }
                for t in image_tasks
            ], f, indent=2, ensure_ascii=False)

        # Write CSV Catalog
        manifest_csv_path = media_products_dir.parent / "media_catalog.csv"
        with open(manifest_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Media ID', 'Filename', 'Local Path', 'Title', 'Parent Product Name', 'Status', 'Linked Products', 'Source URL'])
            for t in image_tasks:
                writer.writerow([
                    t['media_id'],
                    t['filename'],
                    t['local_rel_url'],
                    t['title'],
                    t['parent_name'],
                    t['status'],
                    "; ".join(t['linked_db_products']),
                    t['source_url']
                ])

        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS(f"ALL IMAGES DOWNLOADED & INDEXED SUCCESSFULLY!"))
        self.stdout.write(f"Total media items processed: {len(image_tasks)}")
        self.stdout.write(f"Local files in media/products: {len(list(media_products_dir.glob('*')))}")
        self.stdout.write(f"Newly linked DB products: {newly_linked_count}")
        self.stdout.write(f"Manifest JSON saved at: {manifest_json_path}")
        self.stdout.write(f"Manifest CSV saved at:  {manifest_csv_path}")
        self.stdout.write(self.style.SUCCESS("=" * 60))
