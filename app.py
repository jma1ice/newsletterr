import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, render_template_string, request

app = Flask(__name__)

def apply_layout(body, layout, subject, server_name):
    body = body.replace('\n', '<br>')
    if layout == "basic":
        return f"""
        <html><body style="font-family: Arial; padding: 20px;">
        <h2>newsletterr</h2>
        <div style="border: 1px solid #ddd; padding: 10px; background: #f9f9f9;">
            {body}
        </div></body></html>"""
    elif layout == "card":
        return f"""
        <html><body style="background: #f0f0f0; display: flex; justify-content: center; font-family: Arial;">
        <div style="background: white; max-width: 600px; padding: 20px; margin: 40px auto; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
            {body}
        </div></body></html>"""
    elif layout == "dark":
        return f"""
        <html><body style="background: #111; color: #eee; font-family: Arial; padding: 20px;">
        <div style="background: #222; padding: 20px; border-radius: 8px;">
            {body}
        </div></body></html>"""
    elif layout == "twocol":
        return f"""
        <html><body style="font-family: Arial; padding: 20px;">
        <table style="width: 100%;">
            <tr>
                <td style="width: 50%; padding: 10px;">
                    <img src="https://d15k2d11r6t6rl.cloudfront.net/public/users/Integrators/669d5713-9b6a-46bb-bd7e-c542cff6dd6a/3bef3c50f13f4320a9e31b8be79c6ad2/Plex%20Logo%20Update%202022/plex-logo-heavy-stroke.png" style="max-width: 100%;">
                </td>
                <td style="width: 50%; padding: 10px;">{body}</td>
            </tr>
        </table></body></html>"""
    elif layout == "banner":
        return f"""
        <html><body style="font-family: Arial;">
        <div style="background: #0077cc; color: white; padding: 20px; text-align: center;">
            <h1>newsletterr Header</h1>
        </div>
        <div style="padding: 20px;">{body}</div></body></html>"""
    elif layout == "tautulli":
        return f"""
        <html><body style="font-family: Arial;">
            <table class="body" style="border-collapse: separate; mso-table-lspace: 0pt; mso-table-rspace: 0pt; width: 100%;" border="0" cellspacing="0" cellpadding="0">
                <tbody>
                    <tr>
                        <td class="container" style="font-family: 'Open Sans', Helvetica, Arial, sans-serif; font-size: 14px; vertical-align: top; display: block; max-width: 1042px; padding: 10px; width: 1042px; margin: 0 auto !important;">
                            <div class="content" style="box-sizing: border-box; display: block; margin: 0 auto; max-width: 1037px; padding: 10px;"><span class="preheader" style="color: transparent; display: none; height: 0; max-height: 0; max-width: 0; opacity: 0; overflow: hidden; mso-hide: all; visibility: hidden; width: 0;">ma1ice_m3dia Newsletter</span>
                                <table class="main" style="border-collapse: separate; mso-table-lspace: 0pt; mso-table-rspace: 0pt; width: 100%; background: #282A2D; border-radius: 3px; color: #ffffff;" border="0" cellspacing="0" cellpadding="3">
                                    <tbody>
                                        <tr>
                                            <td class="wrapper" style="font-family: 'Open Sans', Helvetica, Arial, sans-serif; font-size: 14px; vertical-align: top; box-sizing: border-box; padding: 5px; overflow: auto;">
                                                <div class="header" style="width: 50%; height: 10px; text-align: center;"><img class="header-img" style="border: none; -ms-interpolation-mode: bicubic; max-width: 9%; width: 492px; height: 20px; margin-left: -35px;" src="https://d15k2d11r6t6rl.cloudfront.net/public/users/Integrators/669d5713-9b6a-46bb-bd7e-c542cff6dd6a/3bef3c50f13f4320a9e31b8be79c6ad2/Plex%20Logo%20Update%202022/plex-logo-heavy-stroke.png" width="492" height="90" /></div>
                                                <div class="server-name" style="font-size: 25px; text-align: center; margin-bottom: 0;">{server_name} Newsletter</div>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td class="footer" style="font-family: 'Open Sans', Helvetica, Arial, sans-serif; font-size: 12px; vertical-align: top; clear: both; margin-top: 0; text-align: center; width: 100%;">
                                                <h1 class="footer-bar" style="margin-left: auto; margin-right: auto; width: 250px; border-top: 1px solid #E5A00D; margin-top: 5px;">{subject}</h1>
                                                <p>
                                                    {body}
                                                </p>
                                                <div class="footer-bar" style="margin-left: auto; margin-right: auto; width: 250px; border-top: 1px solid #E5A00D; margin-top: 25px;">&nbsp;</div>
                                                <div class="content-block powered-by" style="padding-bottom: 10px; padding-top: 0;">Generated for Plex Media Server by newsletterr</div>
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </td>
                    </tr>
                </tbody>
            </table></body></html>"""
    else:
        return body

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/send_email', methods=['POST'])
def send_email():
    from_email = request.form['from_email']
    password = request.form['password']
    smtp_server = request.form['smtp_server']
    smtp_port = int(request.form['smtp_port'])
    server_name = request.form['server_name']
    to_email = request.form['to_email']
    subject = request.form['subject']
    email_text = request.form['email_text']
    layout = request.form.get('layout', 'none')
    html_content = apply_layout(email_text, layout, subject, server_name)

    msg = MIMEText(html_content, 'html')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(from_email, password)
            server.sendmail(from_email, to_email, msg.as_string())
            alert = "Email sent!"
    except Exception as e:
        alert = f"Error: {str(e)}"
    return render_template('index.html', alert=alert)

if __name__ == '__main__':
    app.run(host="127.0.0.1", port=9898, debug=True)

##testjmw commit###
#jmam test for branching