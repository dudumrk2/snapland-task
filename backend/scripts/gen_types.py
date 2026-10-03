import json
import os
import subprocess
import sys
from pathlib import Path

# Add the backend directory to sys.path so we can import our app
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

def main():
    try:
        from main import app
    except ImportError as e:
        print(f"Failed to import app from main.py: {e}")
        print("Continuing with dummy app if possible or exiting...")
        return

    # Generate OpenAPI schema
    openapi_schema = app.openapi()
    openapi_path = backend_dir / "openapi.json"
    with open(openapi_path, "w") as f:
        json.dump(openapi_schema, f)
    print(f"Exported OpenAPI JSON to {openapi_path}")

    # Generate TypeScript types from OpenAPI
    shared_types_dir = backend_dir.parent / "packages" / "shared-types"
    generated_dir = shared_types_dir / "src" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    api_ts_path = generated_dir / "api.ts"

    # Use npx openapi-typescript
    print("Running openapi-typescript...")
    try:
        subprocess.run(
            ["npx.cmd" if os.name == "nt" else "npx", "openapi-typescript", str(openapi_path), "-o", str(api_ts_path)],
            check=True
        )
        print(f"Successfully generated {api_ts_path}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to run openapi-typescript: {e}")
    except FileNotFoundError:
        print("npx not found. Ensure Node.js is installed.")

    # In the future, parse Pydantic WS models, dump their JSON schema, and run json-schema-to-typescript
    # Example placeholder:
    # ws_models_schema = {}
    # with open("ws_schema.json", "w") as f: json.dump(...)
    # subprocess.run(["npx.cmd", "json-schema-to-typescript", "ws_schema.json", "-o", str(generated_dir / "ws.ts")])
    print("WebSocket models type generation will be added when WS models are defined.")

if __name__ == "__main__":
    main()
