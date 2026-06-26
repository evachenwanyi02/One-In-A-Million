#!/usr/bin/env python3
"""
sync.py — 自動同步 projects/ 資料夾與 projects.json

用法：
  python3 sync.py

邏輯：
  1. 掃描 projects/*.html，提取每個文件的 <title> 作為項目名稱
  2. 讀取現有 projects.json，保留已有項目的元數據（createdAt, location, tag 等）
  3. 新文件 → 自動加入，createdAt = 文件修改時間
  4. 文件被更新過（比 JSON 記錄的時間新）→ 自動設 editedAt
  5. JSON 裡有但文件已刪除 → 自動移除
  6. 文件名根據 <title> 自動重命名為 slug
"""

import os
import re
import json
import glob
import shutil
from datetime import datetime, timezone

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects')
JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects.json')


def slugify(text):
    """將標題轉成 URL 友好的文件名"""
    # 保留中文字符和英文
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9一-鿿]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text or 'untitled'


def extract_title(html_path):
    """從 HTML 的 <title> 標籤提取項目名稱"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read(5000)  # 只讀前面一段
        match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
        if match:
            title = match.group(1).strip()
            # 移除常見的後綴，比如 " — O, I AM" 之類
            title = re.split(r'\s*[—|–|-]\s*O,?\s*I\s*AM', title)[0].strip()
            if title:
                return title
    except Exception:
        pass
    # Fallback：用文件名
    name = os.path.splitext(os.path.basename(html_path))[0]
    return name.replace('-', ' ').replace('_', ' ').title()


def get_file_size_class(file_path):
    """根據文件大小決定圖示等級"""
    size = os.path.getsize(file_path)
    if size < 5000:
        return 'sm'
    elif size < 20000:
        return 'md'
    return 'lg'


def iso_from_timestamp(ts):
    """把文件時間戳轉成 ISO 格式"""
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%S')


def load_existing():
    """讀取現有的 projects.json"""
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def sync():
    os.makedirs(PROJECTS_DIR, exist_ok=True)

    # 讀取現有 JSON，建立 id → entry 的映射
    existing = load_existing()
    existing_map = {}
    for entry in existing:
        existing_map[entry['id']] = entry
        # 也用 href 做反向索引，方便匹配已有文件
        fname = os.path.basename(entry.get('href', ''))
        if fname:
            existing_map['file:' + fname] = entry

    # 掃描 projects/ 下所有 .html
    html_files = sorted(glob.glob(os.path.join(PROJECTS_DIR, '*.html')))

    new_projects = []
    seen_ids = set()
    renames = []

    for html_path in html_files:
        old_filename = os.path.basename(html_path)
        title = extract_title(html_path)
        slug = slugify(title)

        # 避免 slug 重複
        final_slug = slug
        counter = 2
        while final_slug in seen_ids:
            final_slug = slug + '-' + str(counter)
            counter += 1
        seen_ids.add(final_slug)

        expected_filename = final_slug + '.html'

        # 如果文件名和 slug 不匹配，重命名文件
        if old_filename != expected_filename:
            new_path = os.path.join(PROJECTS_DIR, expected_filename)
            if not os.path.exists(new_path):
                shutil.move(html_path, new_path)
                renames.append((old_filename, expected_filename))
                html_path = new_path
                print(f'  Renamed: {old_filename} → {expected_filename}')

        # 查找是否已有這個項目的記錄
        matched = (
            existing_map.get(final_slug)
            or existing_map.get('file:' + old_filename)
            or existing_map.get('file:' + expected_filename)
        )

        file_mtime = os.path.getmtime(html_path)

        if matched:
            # 保留已有的元數據
            entry = dict(matched)
            entry['id'] = final_slug
            entry['name'] = title
            entry['href'] = 'projects/' + expected_filename
            entry['size'] = get_file_size_class(html_path)

            # 檢查是否被更新過（文件修改時間比 createdAt 晚超過 60 秒）
            created_ts = None
            try:
                created_ts = datetime.fromisoformat(entry['createdAt']).timestamp()
            except Exception:
                pass

            if created_ts and file_mtime > created_ts + 60:
                entry['editedAt'] = iso_from_timestamp(file_mtime)

            new_projects.append(entry)
        else:
            # 全新項目
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

    # 找出被刪除的項目
    new_ids = {p['id'] for p in new_projects}
    for entry in existing:
        if entry['id'] not in new_ids:
            print(f'  Removed: {entry["name"]} (file deleted)')

    # 寫入 JSON
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(new_projects, f, ensure_ascii=False, indent=2)

    print(f'\nSynced: {len(new_projects)} project(s) in projects.json')


if __name__ == '__main__':
    print('Syncing projects...')
    sync()
