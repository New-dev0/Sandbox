import click
import asyncio
from sandbox.db.database import DatabaseManager
from sandbox.config import settings
from sandbox.server import start as start_server

@click.group()
def cli():
    """Sandbox CLI tools"""
    pass

@cli.group()
def db():
    """Database management commands"""
    pass

@cli.group()
def server():
    """Server management commands"""
    pass

@server.command()
@click.option('--host', default=None, help='Server host')
@click.option('--port', default=None, type=int, help='Server port')
@click.option('--workers', default=None, type=int, help='Number of workers')
@click.option('--reload/--no-reload', default=None, help='Enable auto-reload')
def start(host, port, workers, reload):
    """Start the API server"""
    if host:
        settings.HOST = host
    if port:
        settings.PORT = port
    if workers:
        settings.WORKERS = workers
    if reload is not None:
        settings.RELOAD = reload
    
    click.echo(f"Starting server on {settings.HOST}:{settings.PORT}")
    start_server()

@server.command()
def check():
    """Check server configuration"""
    click.echo("Server configuration:")
    click.echo(f"Host: {settings.HOST}")
    click.echo(f"Port: {settings.PORT}")
    click.echo(f"Workers: {settings.WORKERS}")
    click.echo(f"Reload: {settings.RELOAD}")
    click.echo(f"SSL: {'Enabled' if settings.SSL_CERT_FILE else 'Disabled'}")
    click.echo(f"Metrics: {'Enabled' if settings.METRICS_ENABLED else 'Disabled'}")
    click.echo(f"Auto Cleanup: {'Enabled' if settings.AUTO_CLEANUP_ENABLED else 'Disabled'}")

@db.command()
def init():
    """Initialize database tables"""
    click.echo("Initializing database...")
    asyncio.run(DatabaseManager.create_tables())
    click.echo("Database initialized successfully!")

@db.command()
def check():
    """Check database connection"""
    click.echo("Checking database connection...")
    if asyncio.run(DatabaseManager.check_connection()):
        click.echo("Database connection successful!")
    else:
        click.echo("Database connection failed!")
        exit(1)

@db.command()
def drop():
    """Drop all database tables"""
    if click.confirm("Are you sure you want to drop all tables? This cannot be undone!"):
        click.echo("Dropping database tables...")
        asyncio.run(DatabaseManager.drop_tables())
        click.echo("Database tables dropped successfully!")

@db.command()
def stats():
    """Show database statistics"""
    click.echo("Fetching database statistics...")
    sizes = asyncio.run(DatabaseManager.get_table_sizes())
    for table, size in sizes.items():
        click.echo(f"{table}: {size/1024/1024:.2f} MB")

@db.command()
def vacuum():
    """Run VACUUM ANALYZE"""
    click.echo("Running VACUUM ANALYZE...")
    asyncio.run(DatabaseManager.vacuum_analyze())
    click.echo("VACUUM ANALYZE completed successfully!")

if __name__ == "__main__":
    cli() 