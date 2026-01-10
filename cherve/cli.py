import typer

from cherve import server as server_module
from cherve import site as site_module

app = typer.Typer(no_args_is_help=True)
server = typer.Typer(no_args_is_help=True)
site = typer.Typer(no_args_is_help=True)
site_tls = typer.Typer(no_args_is_help=True)
domain = typer.Typer(no_args_is_help=True)

app.add_typer(server, name="server")
app.add_typer(site, name="site")
app.add_typer(domain, name="domain")
site.add_typer(site_tls, name="tls")

@server.command("install")
def server_install():
    """Install server requirements."""
    server_module.install()
    raise typer.Exit(code=0)

@site.command("create")
def site_create():
    """Create site (stub)."""
    site_module.create()
    raise typer.Exit(code=0)

@site.command("deploy")
def site_deploy(site_name: str = typer.Argument(None)):
    """Deploy site (stub)."""
    site_module.deploy(site_name)
    raise typer.Exit(code=0)

@site.command("activate")
def site_activate(site_name: str = typer.Argument(None)):
    """Activate site."""
    site_module.activate(site_name)
    raise typer.Exit(code=0)

@site.command("deactivate")
def site_deactivate(site_name: str = typer.Argument(None)):
    """Deactivate site."""
    site_module.deactivate(site_name)
    raise typer.Exit(code=0)

@site_tls.command("enable")
def site_tls_enable(site_name: str = typer.Argument(None), domain_name: str = typer.Argument(None)):
    """Enable TLS."""
    site_module.tls_enable(site_name, domain_name)
    raise typer.Exit(code=0)


@domain.command("add")
def domain_add(site_name: str = typer.Argument(None), domain_name: str = typer.Argument(None)):
    """Add domain to a site."""
    site_module.domain_add(site_name, domain_name)
    raise typer.Exit(code=0)

def main():
    app()
