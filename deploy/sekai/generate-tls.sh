#!/bin/sh
# Make a private local CA and an IP/localhost server certificate. Never overwrite keys.
set -eu
umask 077

if [ "$#" -ne 2 ]; then
    echo "Usage: sh generate-tls.sh <LAN-IP> <new-certificate-directory>" >&2
    exit 2
fi

lan_ip=$(python3 -c 'import ipaddress,sys; print(ipaddress.IPv4Address(sys.argv[1]))' "$1")
cert_dir=$2
mkdir -p "$cert_dir"
chmod 700 "$cert_dir"
for name in root-ca.key root-ca.crt server.key server.csr server.crt server.ext; do
    if [ -e "$cert_dir/$name" ]; then
        echo "Refusing to overwrite existing certificate material: $name" >&2
        exit 1
    fi
done

openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 3650 \
    -subj '/CN=SEKAI Local Test Root CA' \
    -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' \
    -addext 'keyUsage=critical,keyCertSign,cRLSign' \
    -keyout "$cert_dir/root-ca.key" -out "$cert_dir/root-ca.crt"

openssl req -new -newkey rsa:2048 -sha256 -nodes \
    -subj '/CN=SEKAI Local Companion' \
    -keyout "$cert_dir/server.key" -out "$cert_dir/server.csr"

cat > "$cert_dir/server.ext" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:$lan_ip,IP:127.0.0.1,DNS:localhost
EOF

openssl x509 -req -sha256 -days 365 \
    -in "$cert_dir/server.csr" \
    -CA "$cert_dir/root-ca.crt" -CAkey "$cert_dir/root-ca.key" \
    -set_serial "0x$(openssl rand -hex 16)" \
    -extfile "$cert_dir/server.ext" -out "$cert_dir/server.crt"
openssl verify -CAfile "$cert_dir/root-ca.crt" -verify_ip "$lan_ip" "$cert_dir/server.crt"
echo "Created local TLS certificates. Import root-ca.crt on client devices; keep both .key files private."
