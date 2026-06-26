#!/usr/bin/env python3
"""
sync.py — 自動同步 projects/ 和 logos/ 資料夾

用法：
  python3 sync.py

邏輯：
  projects/:
    1. 掃描 *.html，提取 <title> 作為項目名稱
    2. 自動重命名文件為 slug.html
    3. 新文件自動加入 projects.json，保留已有元數據
    4. 文件更新 → 自動設 editedAt
    5. 文件刪除 → 自動移除

  logos/:
    1. 掃描所有圖片文件 (png/jpg/svg/webp)
    2. 用文件名作為組織名稱
    3. 自動生成 logos.json
    4. 文件刪除 → 自動移除
"""

import os
import re
import json
import glob
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, 'projects')
LOGOS_DIR = os.path.join(BASE_DIR, 'logos')
PROJECTS_JSON = os.path.join(BASE_DIR, 'projects.json')
LOGOS_JSON = os.path.join(BASE_DIR, 'logos.json')

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif'}


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9一-鿿]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text or 'untitled'


def extract_title(html_path):
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read(5000)
        match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
        if match:
            title = match.group(1).strip()
            title = re.split(r'\s*[—|–|-]\s*O,?\s*I\s*AM', title)[0].strip()
            if title:
                return title
    except Exception:
        pass
    name = os.path.splitext(os.path.basename(html_path))[0]
    return name.replace('-', ' ').replace('_', ' ').title()


def get_file_size_class(file_path):
    size = os.path.getsize(file_path)
    if size < 5000:
        return 'sm'
    elif size < 20000:
        return 'md'
    return 'lg'


def iso_from_timestamp(ts):
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%S')


def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    f.close()


# ═══════════════════════════════════
#  Sync Projects
# ═══════════════════════════════════

def sync_projects():
    os.makedirs(PROJECTS_DIR, exist_ok=True)

    existing = load_json(PROJECTS_JSON)
    existing_map = {}
    for entry in existing:
        existing_map[entry['id']] = entry
        fname = os.path.basename(entry.get('href', ''))
        if fname:
            existing_map['file:' + fname] = entry

    html_files = sorted(glob.glob(os.path.join(PROJECTS_DIR, '*.html')))
    new_projects = []
    seen_ids = set()

    for html_path in html_files:
        old_filename = os.path.basename(html_path)
        title = extract_title(html_path)
        slug = slugify(title)

        final_slug = slug
        counter = 2
        while final_slug in seen_ids:
            final_slug = slug + '-' + str(counter)
            counter += 1
        seen_ids.add(final_slug)

        expected_filename = final_slug + '.html'

        if old_filename != expected_filename:
            new_path = os.path.join(PROJECTS_DIR, expected_filename)
            if not os.path.exists(new_path):
                shutil.move(html_path, new_path)
                html_path = new_path
                print(f'  Renamed: {old_filename} → {expected_filename}')

        matched = (
            existing_map.get(final_slug)
            or existing_map.get('file:' + old_filename)
            or existing_map.get('file:' + expected_filename)
        )

        file_mtime = os.path.getmtime(html_path)

        if matched:
            entry = dict(matched)
            entry['id'] = final_slug
            entry['name'] = title
            entry['href'] = 'projects/' + expected_filename
            entry['size'] = get_file_size_class(html_path)

            created_ts = None
            try:
                created_ts = datetime.fromisoformat(entry['createdAt']).timestamp()
            except Exception:
                pass

            if created_ts and file_mtime > created_ts + 60:
                entry['editedAt'] = iso_from_timestamp(file_mtime)

            new_projects.append(entry)
        else:
            new_projects.append({
                'id': final_slug,
                'name': title,
                'tag': 'PROJECT',
                'href': 'projects/' + expected_filename,
                'createdAt': iso_from_timestamp(file_mtime),
                'editedAt': None,
                'location': 'Hong Kong',
                'size': get_file_size_class(html_path)
            })
            print(f'  New project: {title} ({expected_filename})')

    new_ids = {p['id'] for p in new_projects}
    for entry in existing:
        if entry['id'] not in new_ids:
            print(f'  Removed project: {entry["name"]}')

    save_json(PROJECTS_JSON, new_projects)
    print(f'  Projects: {len(new_projects)} synced')


# ═══════════════════════════════════
#  Sync Logos
# ═══════════════════════════════════

def sync_logos():
    os.makedirs(LOGOS_DIR, exist_ok=True)

    existing = load_json(LOGOS_JSON)
    existing_map = {}
    for entry in existing:
        existing_map[entry.get('id', '')] = entry
        # Also index by src filename
        src_fname = os.path.basename(entry.get('src', ''))
        if src_fname:
            existing_map['file:' + src_fname] = entry

    # Scan all image files in logos/
    image_files = []
    for f in sorted(os.listdir(LOGOS_DIR)):
        ext = os.path.splitext(f)[1].lower()
        if ext in IMAGE_EXTS:
            image_files.append(f)

    new_logos = []
    seen_ids = set()

    for filename in image_files:
        name_part = os.path.splitext(filename)[0]
        # Clean up filename to readable name
        display_name = name_part.replace('-', ' ').replace('_', ' ').strip()
        slug = slugify(display_name)

        final_slug = slug
        counter = 2
        while final_slug in seen_ids:
            final_slug = slug + '-' + str(counter)
            counter += 1
        seen_ids.add(final_slug)

        # Check if we have existing metadata for this logo
        matched = (
            existing_map.get(final_slug)
            or existing_map.get('file:' + filename)
        )

        if matched:
            entry = dict(matched)
            entry['id'] = final_slug
            entry['src'] = 'logos/' + filename
            # Keep existing name and type
            new_logos.append(entry)
        else:
            # Guess type from common keywords
            lower_name = display_name.lower()
            if any(w in lower_name for w in ['university', 'uni', 'college', 'school', '大学', '學院']):
                logo_type = 'university'
            elif any(w in lower_name for w in ['inc', 'corp', 'ltd', 'tech', 'group', '公司', '集团']):
                logo_type = 'company'
            else:
                logo_type = 'other'

            new_logos.append({
                'id': final_slug,
                'name': display_name.title(),
                'src': 'logos/' + filename,
                'type': logo_type
            })
            print(f'  New logo: {display_name.title()} ({filename})')

    # Report removed
    new_ids = {l['id'] for l in new_logos}
    for entry in existing:
        if entry['id'] not in new_ids:
            print(f'  Removed logo: {entry["name"]} (file deleted)')

    save_json(LOGOS_JSON, new_logos)
    print(f'  Logos: {len(new_logos)} synced')


# ═══════════════════════════════════
#  Main
# ═══════════════════════════════════

if __name__ == '__main__':
    print('Syncing...')
    sync_projects()
    sync_logos()
    print('Done!')
