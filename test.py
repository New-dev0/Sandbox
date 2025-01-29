import asyncio
from sandbox.client import SandboxClient, CreateSandboxRequest, ResourceConfig, PortConfig

async def main():
    # Initialize client
    async with SandboxClient("http://34.132.186.142:8000/api/v1",  # Base URL with /api/v1
                             timeout=1000) as client:
        # Create sandbox request
        request = CreateSandboxRequest(
            image="newdev00/pack-nextjs-shadcn:latest",
            command="/bin/sh -c 'cd frontend && npm install --force && npm run dev'",  # Wrap in shell
            ports=[
                PortConfig(
                    port=3000,  # Next.js default port
                    protocol="http"
                )
            ],
            resources=ResourceConfig(
                cpu=2.0,
                memory="2g"  # Node needs decent memory for install/build
            ),
            environment={
                "NODE_ENV": "development",
                "PORT": "3000"
            }
        )

        try:
            # Create and start sandbox
            print("Creating sandbox...")
            sandbox = await client.create_sandbox(request)
            print(f"Sandbox created: {sandbox.container_id}")
            
            # Get the URL
            if sandbox.urls:
                print("\nAccess your Next.js app at:")
                for port, url in sandbox.urls.items():
                    print(f"- {url}")
            
            # Stream logs
            print("\nStreaming logs...")
            logs = await client.get_sandbox_logs(sandbox.container_id)
            for log in logs:
                print(log.message)
                
            # Keep container running
            print("\nPress Ctrl+C to stop the sandbox")
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print("\nStopping sandbox...")
            await client.delete_sandbox(sandbox.container_id)
            print("Sandbox stopped")
            
        except Exception as e:
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 