# Fase 2 (CHG-020, T-120): Caddy reenvía a la app por la red Docker `ffmovil_net`.
# Las cabeceras de seguridad (RNF-14) y `Cache-Control` las pone la propia app en todas sus
# respuestas; aquí solo se quitan las que delatan el servidor y se añade HSTS (RNF-21).
{
	servers {
		# Cloudflare ya ofrece HTTP/3 al cliente; el origen solo habla HTTP/1.1 y HTTP/2.
		protocols h1 h2

		# RNF-19: solo se cree en `CF-Connecting-IP` si la conexión viene de Cloudflare.
		# Rangos de https://www.cloudflare.com/ips-v4 y /ips-v6; revisarlos si Cloudflare los cambia.
		trusted_proxies static \
 173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22 \
 141.101.64.0/18 108.162.192.0/18 190.93.240.0/20 188.114.96.0/20 \
 197.234.240.0/22 198.41.128.0/17 162.158.0.0/15 104.16.0.0/13 \
 104.24.0.0/14 172.64.0.0/13 131.0.72.0/22 \
 2400:cb00::/32 2606:4700::/32 2803:f800::/32 2405:b500::/32 \
 2405:8100::/32 2a06:98c0::/29 2c0f:f248::/32
		client_ip_headers CF-Connecting-IP
	}
}

ffmovil.com {
	encode zstd gzip
	header -Server
	header -Via
	# RNF-21: 1 año, sin includeSubDomains ni preload.
	header Strict-Transport-Security "max-age=31536000"

	reverse_proxy app:8000 {
		# Reemplaza cualquier `X-Client-IP` que mande el cliente; la app lo lee con
		# CLIENT_IP_HEADER=X-Client-IP (RNF-16, RNF-19).
		header_up X-Client-IP {client_ip}
	}
}

www.ffmovil.com {
	# `route` respeta este orden: sin él Caddy ejecuta `redir` antes que `header`
	# y la redirección saldría sin HSTS.
	route {
		header Strict-Transport-Security "max-age=31536000"
		redir https://ffmovil.com{uri} permanent
	}
}
