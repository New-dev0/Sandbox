# Docker Sandbox Manager

Lightweight Docker container management system for running isolated code environments.

## Setup Steps

1. Environment Setup
   - Install Docker
   - Install Python 3.9+
   - Install requirements: pip install -r requirements.txt
   - Configure environment variables in .env

2. Database Setup
   - Create PostgreSQL database
   - Run migrations: alembic upgrade head
   - Configure DB credentials in .env

3. Start Services
   - Start API server: python -m sandbox.server
   - Start monitoring: python -m sandbox.monitor
   - Start cleanup worker: python -m sandbox.worker

4. Usage
   - Use REST API endpoints
   - Or use Python client SDK
   - See examples in /examples

## Project Structure

/sandbox
  /api         - FastAPI server & endpoints
  /client      - Python SDK
  /core        - Core container management
  /db          - Database models & migrations
  /monitor     - Resource monitoring
  /worker      - Cleanup & maintenance
  /config      - Configuration
  /tests       - Test suite

## Key Features

- Container lifecycle management via API
- Resource limits & monitoring
- Secure isolation
- Auto cleanup of inactive containers
- Client SDK for easy integration

## Security Notes

- Containers run in isolated networks
- Resource limits enforced
- Read-only filesystem
- No privileged access
- API authentication required

## Development

- Run tests: pytest
- Format code: black .
- Check types: mypy .
- Lint: flake8

## Support

Report issues on GitHub

# Sandbox Client Library

A Python client library for interacting with the Sandbox API. This library provides a clean, async interface for managing sandbox containers, volumes, and executing commands.

## Installation

```bash
pip install httpx pydantic
```

## Quick Start

```python
import asyncio
from sandbox.client import SandboxClient, CreateSandboxRequest, PortConfig, ResourceConfig

async def main():
    async with SandboxClient("http://your-api-host:8000") as client:
        # Create a sandbox
        request = CreateSandboxRequest(
            image="python:3.9",
            command="python app.py",
            ports=[PortConfig(internal=8080, protocol="http")],
            resources=ResourceConfig(cpu=1.0, memory="512m")
        )
        sandbox = await client.create_sandbox(request)
        print(f"Created sandbox: {sandbox}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Features

- Async/await support
- Type hints and Pydantic models
- Automatic request/response validation
- Context manager support
- Comprehensive error handling
- File upload/download support
- Command streaming support

## Error Handling

The library provides several custom exceptions:

- `SandboxError`: Base exception class
- `SandboxConnectionError`: Connection issues
- `SandboxTimeoutError`: Operation timeouts
- `SandboxNotFoundError`: Resource not found
- `SandboxOperationError`: General operation failures
- `SandboxValidationError`: Invalid request data
- `SandboxVolumeError`: Volume operation issues

Example error handling:

```python
try:
    sandbox = await client.create_sandbox(request)
except SandboxTimeoutError:
    print("Operation timed out")
except SandboxValidationError as e:
    print(f"Invalid request: {e}")
except SandboxError as e:
    print(f"Operation failed: {e}")
```

## API Reference

### Sandbox Management

- `create_sandbox(request: CreateSandboxRequest)`: Create new sandbox
- `delete_sandbox(sandbox_id: str)`: Delete sandbox
- `get_sandbox_status(sandbox_id: str)`: Get sandbox status
- `list_sandboxes(status: Optional[str])`: List all sandboxes
- `stop_sandbox(sandbox_id: str, timeout: int)`: Stop sandbox
- `start_sandbox(sandbox_id: str)`: Start sandbox
- `restart_sandbox(sandbox_id: str)`: Restart sandbox

### Command Execution

- `execute_command(sandbox_id: str, command: str)`: Execute command
- `stream_command(sandbox_id: str, command: str)`: Stream command output

### Environment & Configuration

- `update_environment(sandbox_id: str, environment: Dict[str, str], merge: bool)`: Update environment variables
- `get_environment(sandbox_id: str)`: Get environment variables
- `update_entrypoint(sandbox_id: str, entrypoint: Optional[Union[str, List[str]]], command: Optional[Union[str, List[str]]])`: Update entrypoint/command
- `get_entrypoint(sandbox_id: str)`: Get entrypoint/command

### Volume Operations

- `list_directory(sandbox_id: str, volume_id: str, path: str)`: List directory contents
- `make_directory(sandbox_id: str, volume_id: str, path: str)`: Create directory
- `read_file(sandbox_id: str, volume_id: str, path: str)`: Read file content
- `write_file(sandbox_id: str, volume_id: str, path: str, content: str)`: Write file content
- `upload_file(sandbox_id: str, volume_id: str, path: str, file_path: str)`: Upload file
- `export_container(sandbox_id: str, folder_path: str, output_path: Optional[str])`: Export container folder as zip

### Network Volume Operations

- `create_network_volume(name: str, driver: str, size: Optional[str], mount_path: Optional[str])`: Create network volume
- `mount_volume(sandbox_id: str, volume_name: str, mount_path: str)`: Mount network volume
- `unmount_volume(sandbox_id: str, volume_name: str)`: Unmount network volume

## Models

### CreateSandboxRequest

```python
class CreateSandboxRequest(BaseModel):
    image: str
    volumes: Optional[Dict[str, VolumeConfig]] = None
    environment: Optional[Dict[str, str]] = None
    resources: Optional[ResourceConfig] = None
    command: Optional[str] = None
    force_build: Optional[bool] = False
    build_context: Optional[Dict[str, str]] = None
    ports: Optional[List[PortConfig]] = None
```

### ResourceConfig

```python
class ResourceConfig(BaseModel):
    cpu: float = Field(default=1.0, ge=0.1, le=8.0)
    memory: str = Field(default="512m")
    gpu: Optional[str] = None
    timeout: Optional[int] = None
    max_retries: Optional[int] = None
```

### PortConfig

```python
class PortConfig(BaseModel):
    internal: int = Field(ge=1, le=65535)
    external: Optional[int] = None
    protocol: str = "http"
    subdomain: Optional[str] = None
```

## Best Practices

1. Always use the context manager to ensure proper cleanup:
```python
async with SandboxClient("http://api-host") as client:
    # Your code here
```

2. Handle errors appropriately:
```python
try:
    await client.create_sandbox(request)
except SandboxError as e:
    logger.error(f"Sandbox operation failed: {e}")
```

3. Use type hints and models for better code completion and validation:
```python
request = CreateSandboxRequest(
    image="python:3.9",
    resources=ResourceConfig(cpu=2.0, memory="1g")
)
```

4. For long-running operations, consider using timeouts:
```python
client = SandboxClient("http://api-host", timeout=60)
```

5. When streaming command output, remember to handle the async iterator:
```python
async for line in client.stream_command(sandbox_id, "tail -f /var/log/app.log"):
    print(line)
```

## License

MIT License