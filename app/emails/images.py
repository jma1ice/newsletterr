import io, mimetypes

import requests
from email.mime.image import MIMEImage
from email.utils import make_msgid
from PIL import Image, ImageFilter, ImageEnhance
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from app import config
from app.security import safe_get
from app.store import save_hosted_image

import logging

logger = logging.getLogger(__name__)

def _center_crop_resize(img, target_w, target_h):
    """Center-crop `img` to the target_w:target_h aspect ratio then resize to
    exactly (target_w, target_h), so the delivered bytes match the display box
    without relying on CSS object-fit (which most email clients ignore)."""
    orig_w, orig_h = img.size
    if orig_w <= 0 or orig_h <= 0:
        return img
    target_ratio = target_w / target_h
    orig_ratio = orig_w / orig_h
    if orig_ratio > target_ratio:
        new_w = max(1, int(round(orig_h * target_ratio)))
        left = (orig_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, orig_h))
    elif orig_ratio < target_ratio:
        new_h = max(1, int(round(orig_w / target_ratio)))
        top = (orig_h - new_h) // 2
        img = img.crop((0, top, orig_w, top + new_h))
    return img.resize((target_w, target_h), Image.LANCZOS)

def fetch_and_attach_image(image_url, msg_root, cid_name, base_url="", max_height=None, hosted_images_enabled=False, hosted_base_url="", target=None):
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
        # An explicit (width, height) target wins over max_height: crop the
        # delivered bytes to exactly that box so grid posters share one aspect
        # ratio regardless of column count.
        _tw = _th = 0
        if target and isinstance(target, (tuple, list)) and len(target) == 2:
            try:
                _tw, _th = int(target[0]), int(target[1])
            except (TypeError, ValueError):
                _tw = _th = 0
        if _tw > 0 and _th > 0:
            try:
                img = Image.open(io.BytesIO(image_bytes))
                img = _center_crop_resize(img, _tw, _th)
                out = io.BytesIO()
                save_fmt = 'JPEG' if subtype == 'jpeg' else 'PNG'
                if save_fmt == 'JPEG' and img.mode in ('RGBA', 'P', 'LA'):
                    img = img.convert('RGB')
                img.save(out, format=save_fmt, quality=85)
                image_bytes = out.getvalue()
            except Exception as _e:
                logger.error(f"PIL target crop failed, using original: {_e}")
        elif max_height and isinstance(max_height, int) and max_height > 0:
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

        if hosted_images_enabled and hosted_base_url:
            try:
                token = save_hosted_image(image_bytes, f"image/{subtype}")
                logger.debug(f"Successfully saved hosted image with token: {token}")
                return f"{hosted_base_url.rstrip('/')}/i/{token}"
            except Exception:
                logger.warning("hosted image write failed, falling back to CID attachment", exc_info=True)
                # fall through to CID attach below, using the bytes already fetched, no re-fetch

        cid = make_msgid(domain="newsletterr.local")[1:-1]

        img_part = MIMEImage(image_bytes, _subtype=subtype)
        img_part.add_header('Content-ID', f'<{cid}>')
        img_part.add_header('Content-Disposition', 'inline', filename=f'{cid_name}.{subtype}')
        msg_root.attach(img_part)

        logger.debug(f"Successfully attached image with CID: {cid}")
        return f"cid:{cid}"

    except requests.exceptions.Timeout as e:
        logger.warning(f"Timeout fetching image {image_url}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching image {image_url}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Error processing image {image_url}: {e}")
        return None

def fetch_and_attach_blurred_image(image_url, msg_root, cid_name, base_url="", hosted_images_enabled=False, hosted_base_url=""):
    if image_url.lower().endswith('.gif'):
        return fetch_and_attach_image(image_url, msg_root, cid_name, base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)
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

        if hosted_images_enabled and hosted_base_url:
            try:
                token = save_hosted_image(img_bytes.getvalue(), "image/jpeg")
                return f"{hosted_base_url.rstrip('/')}/i/{token}"
            except Exception:
                logger.warning("hosted image write failed, falling back to CID attachment", exc_info=True)

        cid = make_msgid(domain="newsletterr.local")[1:-1]

        img_part = MIMEImage(img_bytes.getvalue(), _subtype='jpeg')
        img_part.add_header('Content-ID', f'<{cid}>')
        img_part.add_header('Content-Disposition', 'inline', filename=f'{cid_name}-blurred.jpg')
        msg_root.attach(img_part)

        return f"cid:{cid}"

    except Exception as e:
        logger.error(f"Error processing blurred image {image_url}: {e}")
        return fetch_and_attach_image(image_url, msg_root, cid_name, base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

def fetch_and_attach_small_thumbnail(image_url, msg_root, cid_name, base_url="", height=40, hosted_images_enabled=False, hosted_base_url=""):
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

        if hosted_images_enabled and hosted_base_url:
            try:
                token = save_hosted_image(img_bytes.getvalue(), "image/jpeg")
                return f"{hosted_base_url.rstrip('/')}/i/{token}"
            except Exception:
                logger.warning("hosted image write failed, falling back to CID attachment", exc_info=True)

        cid = make_msgid(domain="newsletterr.local")[1:-1]
        img_part = MIMEImage(img_bytes.getvalue(), _subtype='jpeg')
        img_part.add_header('Content-ID', f'<{cid}>')
        img_part.add_header('Content-Disposition', 'inline', filename=f'{cid_name}.jpg')
        msg_root.attach(img_part)

        return f"cid:{cid}"

    except Exception as e:
        logger.error(f"Error fetching small thumbnail {image_url}: {e}")
        return None

def truncate_text(text, max_chars=28):
    if len(text) <= max_chars:
        return text
    return text[:max_chars-3] + '...'

# Static PNG icons for email output, rendered from the app SVG icon set
# (Gmail strips inline SVG, so emails get raster). Tint 'gray' reads on card
# backgrounds in both light and dark themes; 'white' is for the gradient
# chrome (wrapped card). Assets live in static/img/email-icons/.
EMAIL_ICON_NAMES = {'film', 'tv', 'music', 'users'}

def email_icon_img(icon, msg_root, base_url="", tint="gray", size=14, hosted_images_enabled=False, hosted_base_url=""):
    if icon not in EMAIL_ICON_NAMES:
        return ""
    path = f"/static/img/email-icons/{icon}-{tint}.png"
    cid_name = f"emailicon-{icon}-{tint}-{len(msg_root.get_payload())}"
    src = fetch_and_attach_image(path, msg_root, cid_name, base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url) or path
    return f'<img src="{src}" alt="" width="{size}" height="{size}" style="width: {size}px; height: {size}px; border: 0; vertical-align: -2px; display: inline-block;">'
