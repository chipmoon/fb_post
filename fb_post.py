#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Facebook Auto-Post from Text/Word Files
Đọc nội dung từ file .txt hoặc .docx và đăng lên Facebook
"""

import os
import sys
import glob
import requests
from datetime import datetime
from pathlib import Path

# Try import docx (optional)
try:
    from docx import Document
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False
    print("⚠️ python-docx not installed. .docx files will be skipped.")
    print("   Install: pip install python-docx")

# ========== CẤU HÌNH ==========

POSTS_DIR = "posts"          # Thư mục chứa file nội dung
IMAGES_DIR = "images"        # Thư mục chứa ảnh
CONFIG_FILE = "config.txt"   # File cấu hình Facebook pages

# Facebook Graph API
GRAPH_API_VERSION = "v18.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# ========== HELPER FUNCTIONS ==========

def load_facebook_pages(config_file):
    """
    Đọc danh sách Facebook pages từ config.txt
    Format: page_id|access_token|page_name
    """
    pages = []
    
    if not os.path.exists(config_file):
        print(f"❌ Config file not found: {config_file}")
        return pages
    
    with open(config_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            parts = line.split('|')
            if len(parts) < 2:
                print(f"⚠️ Invalid format at line {line_num}: {line}")
                continue
            
            page_id = parts[0].strip()
            token = parts[1].strip()
            name = parts[2].strip() if len(parts) > 2 else f"Page_{page_id}"
            
            # Get token from env if placeholder
            if token.startswith('$'):
                env_var = token[1:]
                token = os.environ.get(env_var, '')
                if not token:
                    print(f"⚠️ Environment variable {env_var} not set")
                    continue
            
            pages.append({
                'page_id': page_id,
                'token': token,
                'name': name
            })
            print(f"  ✅ Loaded: {name}")
    
    return pages

def read_text_file(filepath):
    """Đọc file .txt"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"❌ Error reading {filepath}: {e}")
        return None

def read_docx_file(filepath):
    """Đọc file .docx"""
    if not DOCX_SUPPORT:
        return None
    
    try:
        doc = Document(filepath)
        content = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
        return content
    except Exception as e:
        print(f"❌ Error reading {filepath}: {e}")
        return None

def parse_post_content(content):
    """
    Parse nội dung bài đăng
    Format:
        IMAGE: filename.jpg
        IMAGE: another.png
        
        Nội dung bài viết...
    
    Returns: {
        'text': 'nội dung',
        'images': ['file1.jpg', 'file2.png']
    }
    """
    lines = content.split('\n')
    images = []
    text_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        
        # Check if line specifies image
        if line_stripped.upper().startswith('IMAGE:'):
            img_filename = line_stripped[6:].strip()
            images.append(img_filename)
        else:
            text_lines.append(line)
    
    text = '\n'.join(text_lines).strip()
    
    return {
        'text': text,
        'images': images
    }

def get_all_post_files(posts_dir):
    """Lấy tất cả file .txt và .docx trong thư mục posts/"""
    files = []
    
    # Get .txt files
    txt_files = glob.glob(os.path.join(posts_dir, "*.txt"))
    files.extend(txt_files)
    
    # Get .docx files if supported
    if DOCX_SUPPORT:
        docx_files = glob.glob(os.path.join(posts_dir, "*.docx"))
        files.extend(docx_files)
    
    # Sort by filename
    files.sort()
    
    return files

def load_post_from_file(filepath):
    """
    Load nội dung bài đăng từ file
    Returns: dict hoặc None nếu lỗi
    """
    filename = os.path.basename(filepath)
    ext = os.path.splitext(filepath)[1].lower()
    
    print(f"\n📄 Reading: {filename}")
    
    # Read content based on extension
    if ext == '.txt':
        content = read_text_file(filepath)
    elif ext == '.docx':
        content = read_docx_file(filepath)
    else:
        print(f"  ⚠️ Unsupported file type: {ext}")
        return None
    
    if not content:
        return None
    
    # Parse content
    parsed = parse_post_content(content)
    
    if not parsed['text']:
        print(f"  ⚠️ No text content found")
        return None
    
    print(f"  ✅ Text: {len(parsed['text'])} characters")
    if parsed['images']:
        print(f"  ✅ Images: {len(parsed['images'])} file(s)")
        for img in parsed['images']:
            print(f"     - {img}")
    
    return {
        'filename': filename,
        'text': parsed['text'],
        'images': parsed['images']
    }

# ========== FACEBOOK API ==========

class FacebookPoster:
    def __init__(self, page_id, access_token, page_name=""):
        self.page_id = page_id
        self.token = access_token
        self.name = page_name
    
    def test_connection(self):
        """Test connection to Facebook Page"""
        url = f"{GRAPH_API_BASE}/{self.page_id}"
        params = {
            'fields': 'name,fan_count',
            'access_token': self.token
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                actual_name = data.get('name', 'Unknown')
                fans = data.get('fan_count', 0)
                print(f"✅ Connected: {actual_name} ({fans:,} followers)")
                return True
            else:
                error = response.json().get('error', {})
                print(f"❌ Connection failed: {error.get('message', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    def upload_photo(self, image_path):
        """Upload ảnh lên Facebook, trả về photo_id"""
        url = f"{GRAPH_API_BASE}/{self.page_id}/photos"
        
        if not os.path.exists(image_path):
            print(f"  ❌ Image not found: {image_path}")
            return None
        
        try:
            with open(image_path, 'rb') as img_file:
                files = {'source': img_file}
                data = {
                    'access_token': self.token,
                    'published': 'false'
                }
                
                response = requests.post(url, files=files, data=data, timeout=60)
                result = response.json()
                
                if 'id' in result:
                    print(f"  ✅ Uploaded: {os.path.basename(image_path)} → {result['id']}")
                    return result['id']
                else:
                    error = result.get('error', {}).get('message', 'Unknown')
                    print(f"  ❌ Upload failed: {error}")
                    return None
        except Exception as e:
            print(f"  ❌ Upload error: {e}")
            return None
    
    def post_text_only(self, message):
        """Đăng bài chỉ có text"""
        url = f"{GRAPH_API_BASE}/{self.page_id}/feed"
        data = {
            'message': message,
            'access_token': self.token
        }
        
        try:
            response = requests.post(url, data=data, timeout=30)
            return response.json()
        except Exception as e:
            return {'error': {'message': str(e)}}
    
    def post_with_photos(self, message, photo_ids):
        """Đăng bài có 1 hoặc nhiều ảnh"""
        url = f"{GRAPH_API_BASE}/{self.page_id}/feed"
        
        # Prepare attached media
        if len(photo_ids) == 1:
            attached_media = [{'media_fbid': photo_ids[0]}]
        else:
            attached_media = [{'media_fbid': pid} for pid in photo_ids]
        
        data = {
            'message': message,
            'attached_media': str(attached_media).replace("'", '"'),
            'access_token': self.token
        }
        
        try:
            response = requests.post(url, data=data, timeout=30)
            return response.json()
        except Exception as e:
            return {'error': {'message': str(e)}}
    
    def post(self, message, image_paths=None):
        """
        Đăng bài lên Facebook
        Args:
            message: Nội dung bài viết
            image_paths: List các đường dẫn ảnh (hoặc None)
        """
        print(f"\n  📤 Posting to: {self.name}")
        
        # Upload images first
        photo_ids = []
        if image_paths:
            for img_path in image_paths:
                photo_id = self.upload_photo(img_path)
                if photo_id:
                    photo_ids.append(photo_id)
        
        # Post to feed
        if photo_ids:
            result = self.post_with_photos(message, photo_ids)
        else:
            result = self.post_text_only(message)
        
        # Check result
        if 'id' in result:
            post_id = result['id']
            post_url = f"https://facebook.com/{post_id}"
            print(f"  ✅ Posted successfully!")
            print(f"     ID: {post_id}")
            print(f"     URL: {post_url}")
            return {
                'success': True,
                'post_id': post_id,
                'url': post_url
            }
        else:
            error = result.get('error', {}).get('message', 'Unknown error')
            print(f"  ❌ Post failed: {error}")
            return {
                'success': False,
                'error': error
            }

# ========== MAIN ==========

def main():
    print("=" * 80)
    print("🚀 FACEBOOK AUTO-POST - File-based Version")
    print("=" * 80)
    
    # Check directories
    if not os.path.exists(POSTS_DIR):
        print(f"❌ Posts directory not found: {POSTS_DIR}")
        print(f"   Please create it and add .txt or .docx files")
        sys.exit(1)
    
    if not os.path.exists(IMAGES_DIR):
        print(f"⚠️ Images directory not found: {IMAGES_DIR}")
        print(f"   Creating it...")
        os.makedirs(IMAGES_DIR)
    
    # Load Facebook pages config
    print(f"\n🔐 Loading Facebook pages from {CONFIG_FILE}...")
    pages = load_facebook_pages(CONFIG_FILE)
    
    if not pages:
        print("❌ No Facebook pages configured!")
        print(f"   Please create {CONFIG_FILE} with format:")
        print("   page_id|access_token|page_name")
        sys.exit(1)
    
    # Test connections
    print("\n🔌 Testing connections...")
    valid_pages = []
    for page in pages:
        poster = FacebookPoster(page['page_id'], page['token'], page['name'])
        if poster.test_connection():
            valid_pages.append(poster)
    
    if not valid_pages:
        print("❌ No valid Facebook pages found!")
        sys.exit(1)
    
    print(f"\n✅ {len(valid_pages)} page(s) ready")
    
    # Load all post files
    print(f"\n📁 Loading posts from {POSTS_DIR}/...")
    post_files = get_all_post_files(POSTS_DIR)
    
    if not post_files:
        print(f"❌ No post files found in {POSTS_DIR}/")
        print("   Please add .txt or .docx files")
        sys.exit(1)
    
    print(f"✅ Found {len(post_files)} post file(s)")
    
    # Load posts
    posts = []
    for filepath in post_files:
        post_data = load_post_from_file(filepath)
        if post_data:
            posts.append(post_data)
    
    if not posts:
        print("❌ No valid posts loaded!")
        sys.exit(1)
    
    print(f"\n✅ Loaded {len(posts)} valid post(s)")
    
    # Post to Facebook
    print("\n" + "=" * 80)
    print("📤 POSTING TO FACEBOOK")
    print("=" * 80)
    
    total_success = 0
    total_failed = 0
    
    for i, post in enumerate(posts, 1):
        print(f"\n[{i}/{len(posts)}] Processing: {post['filename']}")
        print("-" * 80)
        
        # Prepare image paths
        image_paths = []
        for img_filename in post['images']:
            img_path = os.path.join(IMAGES_DIR, img_filename)
            if os.path.exists(img_path):
                image_paths.append(img_path)
            else:
                print(f"  ⚠️ Image not found: {img_filename}")
        
        # Post to all pages
        for poster in valid_pages:
            result = poster.post(post['text'], image_paths if image_paths else None)
            
            if result['success']:
                total_success += 1
            else:
                total_failed += 1
            
            # Small delay between posts
            import time
            time.sleep(2)
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"📄 Posts processed:  {len(posts)}")
    print(f"📍 Pages targeted:   {len(valid_pages)}")
    print(f"✅ Total success:    {total_success}")
    print(f"❌ Total failed:     {total_failed}")
    print("=" * 80)
    
    if total_failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
