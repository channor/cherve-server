import typer

from cherve import server as server_module
from cherve import site as site_module

app = typer.Typer(no_args_is_help=True)
server = typer.Typer(no_args_is_help=True)
site = typer.Typer(no_args_is_help=True)

app.add_typer(server, name="server")
app.add_typer(site, name="site")

@server.command("install")
def server_install():
    """Install server requirements (stub)."""
    server_module.install()
    raise typer.Exit(code=0)

@site.command("create")
def site_create():
    """Create site (stub)."""
    site_module.create()
    raise typer.Exit(code=0)

@site.command("deploy")
def site_deploy(domain: str = typer.Argument(None)):
    """Deploy site (stub)."""
    site_module.deploy(domain)
    raise typer.Exit(code=0)

def main():
    app()
