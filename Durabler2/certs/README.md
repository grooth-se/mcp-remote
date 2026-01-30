# Certificate Setup for PDF Signing

This folder contains the X.509 certificate used for digitally signing test reports.

## Required Certificate Format

The system requires a **PKCS#12** certificate file (`.p12` or `.pfx` extension) containing:
- Private key
- Company certificate
- Certificate chain (optional, for full trust verification)

## Certificate File Location

Place your certificate file in this directory with the name:
```
durabler_company.p12
```

Or configure a custom filename via environment variable:
```bash
export COMPANY_CERT_FILE=your_certificate.p12
```

## Certificate Password

Set the certificate password via environment variable (recommended for production):
```bash
export COMPANY_CERT_PASSWORD=your_secure_password
```

**Important:** Never commit certificates or passwords to version control.

## Creating a Self-Signed Certificate (Development/Testing)

For development purposes, you can create a self-signed certificate:

```bash
# Generate private key and self-signed certificate
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/C=SE/ST=Vastra Gotaland/L=Gothenburg/O=Durabler AB/OU=Testing Laboratory/CN=Durabler AB"

# Convert to PKCS#12 format
openssl pkcs12 -export -out durabler_company.p12 -inkey key.pem -in cert.pem \
  -name "Durabler AB Test Certificate"

# Clean up intermediate files
rm key.pem cert.pem
```

## Obtaining a Production Certificate

For production use (ISO 17025 accredited reports), obtain a certificate from:

1. **Certificate Authority (CA)** - Trusted certificates like:
   - DigiCert
   - GlobalSign
   - Sectigo (formerly Comodo)

2. **Swedish Trust Service Providers** - For Swedish regulatory compliance:
   - BankID
   - Freja eID
   - Swedish e-Identification Board approved providers

## Verification

To verify your certificate is valid:

```bash
# View certificate details
openssl pkcs12 -in durabler_company.p12 -info -nokeys
```

## Security Notes

- Keep the private key secure - it provides proof of document authenticity
- Use strong passwords for certificate files
- Rotate certificates before expiration
- Store backup copies in a secure location
- Never share the private key or PKCS#12 file

## Configuration

In `config.py`, the following settings control certificate usage:

```python
CERTS_FOLDER = basedir / 'certs'
COMPANY_CERT_FILE = os.environ.get('COMPANY_CERT_FILE') or 'durabler_company.p12'
COMPANY_CERT_PASSWORD = os.environ.get('COMPANY_CERT_PASSWORD') or ''
```
