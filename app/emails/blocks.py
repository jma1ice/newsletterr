import base64

from email.mime.image import MIMEImage
from email.utils import make_msgid

from app.theme import get_email_theme_colors
from app.emails.images import fetch_and_attach_image

import logging

logger = logging.getLogger(__name__)

def build_graph_html_with_frontend_image(item, msg_root):
    chart_name = item.get('name', 'Chart')
    chart_image_data = item.get('chartImage', '')
    
    logger.debug(f"Processing graph: {chart_name}")
    
    if chart_image_data and chart_image_data.startswith('data:image/png'):
        try:
            header, encoded = chart_image_data.split(',', 1)
            image_data = base64.b64decode(encoded)
            
            cid = make_msgid(domain="newsletterr.local")[1:-1]
            
            img_part = MIMEImage(image_data, _subtype='png')
            img_part.add_header('Content-ID', f'<{cid}>')
            img_part.add_header('Content-Disposition', 'inline', filename=f'chart-{cid}.png')
            msg_root.attach(img_part)
            
            logger.debug(f"Successfully attached PNG chart with CID: {cid}")
            
            container_style = """
                border-radius: 8px;
                text-align: center;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
            """
            
            image_style = """
                max-width: 100%;
                height: auto;
                border-radius: 4px;
                border: 0;
                line-height: 100%;
                outline: none;
                text-decoration: none;
                display: block;
                margin: 0 auto;
            """
            
            return f"""
            <div style="{container_style}">
                <img src="cid:{cid}" alt="{chart_name}" style="{image_style}">
            </div>
            """
            
        except Exception as e:
            logger.error(f"Error processing chart image for {chart_name}: {e}")
    
    logger.debug(f"No valid chart data for {chart_name}")
    
    placeholder_style = """
        margin: 20px 0;
        padding: 30px;
        background-color: #f8f9fa;
        border: 2px dashed #dee2e6;
        border-radius: 8px;
        text-align: center;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    placeholder_title_style = """
        color: #6c757d;
        margin: 0 0 10px 0;
        font-size: 18px;
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    placeholder_text_style = """
        color: #6c757d;
        margin: 0;
        font-size: 14px;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    placeholder_subtext_style = """
        color: #6c757d;
        margin: 5px 0 0;
        font-size: 12px;
        font-style: italic;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    return f"""
    <div style="{placeholder_style}">
        <h3 style="{placeholder_title_style}">{chart_name}</h3>
        <p style="{placeholder_text_style}">Chart image not available</p>
        <p style="{placeholder_subtext_style}">Interactive charts available in dashboard</p>
    </div>
    """

def build_text_block_html(content, block_type='textblock', theme_colors=None):
    if not theme_colors:
        theme_colors = get_email_theme_colors()
    
    if not content or not content.strip():
        logger.debug(f"Textblock called but no text present: {content}")
        return ""
    
    formatted_content = content.strip().replace('\n', '<br>')
    
    base_style = f"""
        margin-bottom: 20px;
        line-height: 1.6;
        color: {theme_colors['text']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    if block_type == 'titleblock':
        style = base_style + """
            font-size: 2em;
            font-weight: bold;
            text-align: center;
        """
    elif block_type == 'headerblock':
        style = base_style + """
            font-size: 1.5em;
            font-weight: bold;
            text-align: center;
        """
    else:
        style = base_style + """
            margin-bottom: 15px;
            text-align: center;
        """
    
    return f'<div style="{style}">{formatted_content}</div>'

def build_separator_html(theme_colors=None):
    if not theme_colors:
        theme_colors = get_email_theme_colors()
    return f'''<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 20px 0;">
                <tr>
                    <td style="padding: 0 10%;">
                        <hr style="border: none; border-top: 1px solid {theme_colors['text']}; margin: 0;">
                    </td>
                </tr>
            </table>'''

def build_image_html_with_cid(item, msg_root, base_url=""):
    src = item.get('src', '').strip()
    width = item.get('width', 400)
    align = item.get('align', 'center')

    if not src:
        return ''

    cid = fetch_and_attach_image(src, msg_root, f"media-{item.get('id', 'img')}", base_url)

    if cid:
        img_src = f"cid:{cid}"
    else:
        img_src = src

    align_style = {
        'left': 'margin: 0 auto 15px 0;',
        'right': 'margin: 0 0 15px auto;',
        'center': 'margin: 0 auto 15px auto;'
    }.get(align, 'margin: 0 auto 15px auto;')

    return f'''<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 10px 0;">
        <tr>
            <td align="{align}" style="padding: 0;">
                <img src="{img_src}"
                     width="{width}"
                     style="display: block; {align_style} max-width: 100%; height: auto; border: 0;"
                     alt="">
            </td>
        </tr>
    </table>'''

def build_emoji_html(item, theme_colors=None):
    if not theme_colors:
        theme_colors = get_email_theme_colors()

    content = item.get('content', '').strip()
    size = item.get('size', '2em')
    align = item.get('align', 'center')

    if not content:
        return ''

    return f'''<div style="
        text-align: {align};
        font-size: {size};
        line-height: 1.4;
        margin: 10px 0;
        font-family: 'Segoe UI Emoji', 'Apple Color Emoji', 'Noto Color Emoji', sans-serif;
    ">{content}</div>'''
