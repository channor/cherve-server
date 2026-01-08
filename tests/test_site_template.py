from cherve import site


def test_render_nginx_template():
    rendered = site._render_nginx_config(
        server_name="example.com www.example.com",
        root_path="/var/www/example.com/public",
        php_fpm_sock="/run/php/php8.3-fpm.sock",
        client_max_body_size="64M",
    )
    assert "server_name example.com www.example.com;" in rendered
    assert "root /var/www/example.com/public;" in rendered
    assert "fastcgi_pass unix:/run/php/php8.3-fpm.sock;" in rendered
