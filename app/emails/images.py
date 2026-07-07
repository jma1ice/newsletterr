import io, mimetypes

import requests
from email.mime.image import MIMEImage
from email.utils import make_msgid
from PIL import Image, ImageFilter, ImageEnhance
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from app import config
from app.security import safe_get

import logging

logger = logging.getLogger(__name__)

def fetch_and_attach_image(image_url, msg_root, cid_name, base_url="", max_height=None):
    try:
        logger.debug(f"fetch_and_attach_image called with: {image_url}")
        
        is_local_static = (
            image_url.startswith('/static/') or 
            image_url.startswith('/static\\') or
            'static/img/' in image_url or
            'static/uploads/' in image_url
        )
        
        if is_local_static:
            full_url = urljoin(base_url or "http://127.0.0.1:6397", image_url)
            logger.debug(f"Local static file, fetching directly: {full_url}")
        elif image_url.startswith('/library/') or image_url.startswith('/photo/'):
            full_url = urljoin(base_url or "http://127.0.0.1:6397", f"/proxy-art{image_url}")
            logger.debug(f"Plex image, using proxy: {full_url}")
        elif image_url.startswith('http'):
            parsed = urlparse(image_url)
            
            if '/library/' in parsed.path or '/photo/' in parsed.path or '/composite/' in parsed.path:
                path = parsed.path
                query = parsed.query
                
                if query:
                    params = parse_qs(query)
                    if 'X-Plex-Token' in params:
                        del params['X-Plex-Token']
                    
                    if params:
                        query_str = urlencode(params, doseq=True)
                        path = f"{path}?{query_str}"
                
                full_url = urljoin(base_url or "http://127.0.0.1:6397", f"/proxy-art{path}")
                logger.debug(f"Full Plex URL, using proxy: {full_url}")
            else:
                full_url = image_url
                logger.debug(f"External URL, fetching directly: {full_url}")
        else:
            full_url = urljoin(base_url or "http://127.0.0.1:6397", image_url)
            logger.debug(f"Default case, fetching: {full_url}")
        
        logger.debug(f"Final URL to fetch: {full_url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'X-Internal-Token': config.INTERNAL_TOKEN
        }
        
        response = safe_get(full_url, timeout=15, headers=headers)
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Response content length: {len(response.content)}")
        
        response.raise_for_status()
        
        if len(response.content) < 100:
            logger.warning(f"Warning: Response content too small ({len(response.content)} bytes), likely not a valid image")
            return None
        
        content_type = response.headers.get('Content-Type')
        logger.debug(f"Content-Type: {content_type}")
        
        if not content_type or not content_type.startswith('image/'):
            logger.warning(f"Warning: Invalid content type: {content_type}")
            content_type = mimetypes.guess_type(full_url)[0] or 'image/png'
        
        subtype = content_type.split('/')[-1]
        if subtype == 'jpg':
            subtype = 'jpeg'

        image_bytes = response.content
        if max_height and isinstance(max_height, int) and max_height > 0:
            try:
                img = Image.open(io.BytesIO(image_bytes))
                orig_w, orig_h = img.size
                if orig_h > max_height:
                    target_w = max(1, int(orig_w * max_height / orig_h))
                    img = img.resize((target_w, max_height), Image.LANCZOS)
                    out = io.BytesIO()
                    save_fmt = 'JPEG' if subtype == 'jpeg' else 'PNG'
                    if save_fmt == 'JPEG' and img.mode in ('RGBA', 'P', 'LA'):
                        img = img.convert('RGB')
                    img.save(out, format=save_fmt, quality=85)
                    image_bytes = out.getvalue()
            except Exception as _e:
                logger.error(f"PIL resize failed, using original: {_e}")

        cid = make_msgid(domain="newsletterr.local")[1:-1]

        img_part = MIMEImage(image_bytes, _subtype=subtype)
        img_part.add_header('Content-ID', f'<{cid}>')
        img_part.add_header('Content-Disposition', 'inline', filename=f'{cid_name}.{subtype}')
        msg_root.attach(img_part)
        
        logger.debug(f"Successfully attached image with CID: {cid}")
        return cid
        
    except requests.exceptions.Timeout as e:
        logger.warning(f"Timeout fetching image {image_url}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching image {image_url}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Error processing image {image_url}: {e}")
        return None

def fetch_and_attach_blurred_image(image_url, msg_root, cid_name, base_url=""):
    if image_url.lower().endswith('.gif'):
        return fetch_and_attach_image(image_url, msg_root, cid_name, base_url)
    try:
        if image_url.startswith('/'):
            full_url = urljoin(base_url or "http://127.0.0.1:6397", image_url)
        else:
            full_url = image_url
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'X-Internal-Token': config.INTERNAL_TOKEN
        }

        response = safe_get(full_url, timeout=10, headers=headers)
        response.raise_for_status()
        
        image = Image.open(io.BytesIO(response.content))
        
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')
        
        blurred = image.filter(ImageFilter.GaussianBlur(radius=30))
        
        enhancer = ImageEnhance.Brightness(blurred)
        darkened = enhancer.enhance(0.7)
        
        img_bytes = io.BytesIO()
        darkened.save(img_bytes, format='JPEG', quality=85)
        img_bytes.seek(0)
        
        cid = make_msgid(domain="newsletterr.local")[1:-1]
        
        img_part = MIMEImage(img_bytes.getvalue(), _subtype='jpeg')
        img_part.add_header('Content-ID', f'<{cid}>')
        img_part.add_header('Content-Disposition', 'inline', filename=f'{cid_name}-blurred.jpg')
        msg_root.attach(img_part)
        
        return cid
        
    except Exception as e:
        logger.error(f"Error processing blurred image {image_url}: {e}")
        return fetch_and_attach_image(image_url, msg_root, cid_name, base_url)

def fetch_and_attach_small_thumbnail(image_url, msg_root, cid_name, base_url="", height=40):
    try:
        if image_url.startswith('/'):
            full_url = urljoin(base_url or "http://127.0.0.1:6397", image_url)
        elif image_url.startswith('http'):
            full_url = image_url
        else:
            full_url = urljoin(base_url or "http://127.0.0.1:6397", image_url)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'X-Internal-Token': config.INTERNAL_TOKEN
        }

        response = safe_get(full_url, timeout=10, headers=headers)
        response.raise_for_status()

        if len(response.content) < 100:
            return None

        image = Image.open(io.BytesIO(response.content))
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')

        orig_w, orig_h = image.size
        if orig_h == 0:
            return None
        target_w = max(1, int(orig_w * height / orig_h))
        resized = image.resize((target_w, height), Image.LANCZOS)

        img_bytes = io.BytesIO()
        resized.save(img_bytes, format='JPEG', quality=65)
        img_bytes.seek(0)

        cid = make_msgid(domain="newsletterr.local")[1:-1]
        img_part = MIMEImage(img_bytes.getvalue(), _subtype='jpeg')
        img_part.add_header('Content-ID', f'<{cid}>')
        img_part.add_header('Content-Disposition', 'inline', filename=f'{cid_name}.jpg')
        msg_root.attach(img_part)

        return cid

    except Exception as e:
        logger.error(f"Error fetching small thumbnail {image_url}: {e}")
        return None

def truncate_text(text, max_chars=28):
    if len(text) <= max_chars:
        return text
    return text[:max_chars-3] + '...'
