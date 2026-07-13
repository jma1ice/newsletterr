/*
 * Email provider presets for the guided SMTP setup wizard (settings + first-run
 * setup). Classic script, deliberately outside the index-only numbered
 * static/js/app/ load chain. Defines window.EMAIL_PROVIDERS.
 *
 * Each preset: label, smtpServer, smtpPort, smtpProtocol, usernameIsEmail,
 * appPasswordUrl, notes[]. No OAuth: every provider uses an app password or the
 * account password over SMTP.
 */
(function () {
    window.EMAIL_PROVIDERS = {
        gmail: {
            label: 'Gmail',
            smtpServer: 'smtp.gmail.com',
            smtpPort: 587,
            smtpProtocol: 'TLS',
            usernameIsEmail: true,
            appPasswordUrl: 'https://myaccount.google.com/apppasswords',
            notes: [
                'Turn on 2-Step Verification on your Google account first; app passwords are only available once it is enabled.',
                'Create a 16-character app password and paste it below (spaces are optional).',
                'Use your full Gmail address as the From address.'
            ]
        },
        outlook: {
            label: 'Outlook / Microsoft 365',
            smtpServer: 'smtp-mail.outlook.com',
            smtpPort: 587,
            smtpProtocol: 'TLS',
            usernameIsEmail: true,
            appPasswordUrl: 'https://account.microsoft.com/security',
            notes: [
                'Enable two-step verification, then create an app password under Security settings.',
                'Some newer Microsoft 365 tenants disable basic SMTP auth; ask your admin if the test fails.',
                'Use your full Outlook address as the From address.'
            ]
        },
        yahoo: {
            label: 'Yahoo Mail',
            smtpServer: 'smtp.mail.yahoo.com',
            smtpPort: 465,
            smtpProtocol: 'SSL',
            usernameIsEmail: true,
            appPasswordUrl: 'https://login.yahoo.com/account/security',
            notes: [
                'Generate an app password from Account Security; your normal password will not work over SMTP.',
                'Use your full Yahoo address as the From address.'
            ]
        },
        icloud: {
            label: 'iCloud Mail',
            smtpServer: 'smtp.mail.me.com',
            smtpPort: 587,
            smtpProtocol: 'TLS',
            usernameIsEmail: true,
            appPasswordUrl: 'https://appleid.apple.com/account/manage',
            notes: [
                'Enable two-factor authentication, then create an app-specific password under Sign-In and Security.',
                'Use your iCloud Mail address (icloud.com, me.com, or mac.com) as the From address.'
            ]
        },
        custom: {
            label: 'Custom / Other',
            smtpServer: '',
            smtpPort: 587,
            smtpProtocol: 'TLS',
            usernameIsEmail: false,
            appPasswordUrl: '',
            notes: [
                'Enter the SMTP host, port, and protocol from your email provider.',
                'Port 465 usually means SSL; port 587 usually means TLS.'
            ]
        }
    };
})();
