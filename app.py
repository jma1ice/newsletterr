import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, render_template_string, request

app = Flask(__name__)

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
    use_layout = 'layout' in request.form

    if use_layout:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Newsletterr</h2>
            <div style="border: 1px solid #ddd; padding: 10px; background: #f9f9f9;">
                {email_text.replace('\n', '<br>')}
            </div>
            </body>
        </html>
        """
    else:
        html_content = email_text.replace('\n', '<br>')

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