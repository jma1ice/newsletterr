import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, request

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
    html_content = request.form['html_content']

    msg = MIMEText(html_content, 'html')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(from_email, password)
            server.sendmail(from_email, to_email, msg.as_string())
        return "Email sent!"
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == '__main__':
    app.run(host="127.0.0.1", port=9898, debug=True)

##testjmw commit###
#jmam test for branching