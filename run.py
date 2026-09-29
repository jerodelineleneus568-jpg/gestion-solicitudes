from app import create_app

app = create_app()

if __name__ == '__main__':
    # A02: Transmisión cifrada mediante HTTPS/TLS
    app.run(
        host='0.0.0.0',
        port=8443,
        ssl_context=('certs/cert.pem', 'certs/key.pem'),
        debug=False
    )