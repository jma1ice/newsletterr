import sqlite3

from app import config

def get_theme_settings():
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT primary_color, secondary_color, accent_color, background_color, text_color, email_theme
            FROM settings WHERE id = 1
        """)
        row = cursor.fetchone()
        
        if row:
            return {
                'primary_color': row[0] or '#8acbd4',
                'secondary_color': row[1] or '#222222',
                'accent_color': row[2] or '#62a1a4',
                'background_color': row[3] or '#333333',
                'text_color': row[4] or '#62a1a4',
                'email_theme': row[5] or 'newsletterr_blue'
            }
    except Exception as e:
        print(f"Error getting theme settings: {e}")
    finally:
        conn.close()
    
    return {
        'primary_color': '#8acbd4',
        'secondary_color': '#222222',
        'accent_color': '#62a1a4',
        'background_color': '#333333',
        'text_color': '#62a1a4',
        'email_theme': 'newsletterr_blue'
    }

def get_email_theme_colors():
    theme_settings = get_theme_settings()
    
    return {
        'background': theme_settings['background_color'],
        'text': theme_settings['text_color'],
        'primary': theme_settings['primary_color'],
        'secondary': theme_settings['secondary_color'],
        'accent': theme_settings['accent_color'],
        'card_bg': '#2d2d2d',
        'border': '#404040',
        'muted_text': '#cccccc',
        'email_theme': theme_settings['email_theme']
    }

def build_email_css_from_theme(theme_colors, logo_width):
    return f"""
        <style>
            @import url(https://fonts.googleapis.com/css?family=IBM+Plex+Sans:400,700&display=swap);
            
            body {{
                margin: 0 !important;
                padding: 0 !important;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif !important;
                background-color: {theme_colors['background']} !important;
                line-height: 1.6 !important;
                color: {theme_colors['text']} !important;
                -webkit-text-size-adjust: 100% !important;
                -ms-text-size-adjust: 100% !important;
            }}
            
            table, td {{
                border-collapse: collapse !important;
                mso-table-lspace: 0pt !important;
                mso-table-rspace: 0pt !important;
            }}
            
            img {{
                border: 0 !important;
                height: auto !important;
                line-height: 100% !important;
                outline: none !important;
                text-decoration: none !important;
                -ms-interpolation-mode: bicubic !important;
            }}
            
            .ReadMsgBody {{ width: 100% !important; }}
            .ExternalClass {{ width: 100% !important; }}
            .ExternalClass * {{ line-height: 100% !important; }}

            .email-container {{
                max-width: 800px !important;
                width: 100% !important;
                margin: 0 auto !important;
            }}
            
            .email-logo {{
                max-width: {logo_width}px !important;
                width: auto !important;
                height: auto !important;
            }}

            .card-poster-wrapper {{
                position: relative !important;
                display: block !important;
            }}

            .card-poster {{
                background-size: cover !important;
                background-position: center !important;
                background-repeat: no-repeat !important;
                width: 100% !important;
                height: auto;
                padding-top: 135%;
                position: relative !important;
                background-color: #f8f9fa !important;
                border-radius: 10px 10px 0 0 !important;
            }}

            .card-poster-badge {{
                position: absolute !important;
                bottom: 1px !important;
                right: 1px !important;
                background-color: rgba(0, 0, 0, 0.6);
                color: rgba(255, 255, 255, 0.9);
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 9px;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                line-height: 1;
                max-width: fit-content;
            }}

            @media only screen and (max-width: 600px) {{
                .email-container {{
                    width: 100% !important;
                    max-width: 100% !important;
                    margin: 0 !important;
                }}
                
                .email-logo {{
                    max-width: 60px !important;
                    width: 60px !important;
                }}

                .recently-added-table {{
                    display: block !important;
                    width: 100% !important;
                    text-align: center !important;
                }}

                .recently-added-row {{
                    display: inline !important;
                }}
                
                .recently-added-table td {{
                    width: 30% !important;
                    padding: 6px !important;
                    display: inline-block !important;
                    vertical-align: top !important;
                    box-sizing: border-box !important;
                }}
                
                .recently-added-card {{
                    width: 100% !important;
                    max-width: 150px !important;
                    margin: 0 auto 10px auto !important;
                    height: auto !important;
                    overflow: hidden !important;
                    border-radius: 10px !important;
                }}

                .card-poster {{
                    padding-top: 125% !important;
                    min-height: 25px;
                }}
                
                .card-content {{
                    height: auto !important;
                    min-height: 165px !important;
                    text-align: left !important;
                }}
            }}
        </style>
    """
