import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, render_template_string, request

app = Flask(__name__)

def apply_layout(body, layout):
    body = body.replace('\n', '<br>')
    if layout == "basic":
        return f"""
        <html><body style="font-family: Arial; padding: 20px;">
        <h2>Newsletter</h2>
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
              <img src="https://via.placeholder.com/250" style="max-width: 100%;">
            </td>
            <td style="width: 50%; padding: 10px;">{body}</td>
          </tr>
        </table></body></html>"""
    elif layout == "banner":
        return f"""
        <html><body style="font-family: Arial;">
        <div style="background: #0077cc; color: white; padding: 20px; text-align: center;">
          <h1>Newsletter Header</h1>
        </div>
        <div style="padding: 20px;">{body}</div></body></html>"""
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
    to_email = request.form['to_email']
    subject = request.form['subject']
    email_text = request.form['email_text']
    layout = request.form.get('layout', 'none')
    html_content = apply_layout(email_text, layout)

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