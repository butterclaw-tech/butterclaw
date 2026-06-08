#!/bin/bash
# ButterClaw v0.6.4 Exoskeleton - Automated Deployment

set -e

echo "🦞 Initializing ButterClaw Exoskeleton Deployment..."
echo "------------------------------------------------------"

# 1. Check for unautclated environments (Missing Docker)
if ! command -v docker &> /dev/null; then
    echo "❌ CRITICAL: Docker is not installed. The Exoskeleton requires Docker to run."
    echo "Please install Docker and Docker Compose, then try again."
    exit 1
fi

# 2. Host Ollama Check
echo "🧠 Checking for local inference engine..."
if ! command -v ollama &> /dev/null; then
    echo "⚠️  NOTE: Ollama not found on host. If you plan to use local inference,"
    echo "   ensure Ollama is installed on your machine and running the gemma4 model."
else
    echo "✅ Host Ollama detected."
fi

# 3. Clone the Repository
if [ -d "butterclaw" ]; then
    echo "⚠️  Directory 'butterclaw' already exists."
    echo "To update, cd into the directory and run 'git pull', then 'docker compose up -d'."
    exit 1
fi

echo "📦 Cloning ButterClaw repository..."
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw

# 4. Scaffold the Environment
echo "⚙️  Configuring the local ButterVault environment..."
cp .env.example .env

# Auto-generate Instance ID
INSTANCE_ID="bc_$(openssl rand -hex 4)"
sed -i "s/BUTTERCLAW_INSTANCE_ID=.*/BUTTERCLAW_INSTANCE_ID=$INSTANCE_ID/" .env

# Auto-generate Internal API Key for daemon self-healing
INTERNAL_KEY="$(openssl rand -hex 32)"
sed -i "s/BUTTERCLAW_API_KEY=.*/BUTTERCLAW_API_KEY=$INTERNAL_KEY/" .env

# Auto-generate a unique ntfy topic to prevent cross-talk
UNIQUE_NTFY="butterclaw_alerts_$(openssl rand -hex 4)"
sed -i "s/NTFY_TOPIC=.*/NTFY_TOPIC=$UNIQUE_NTFY/" .env

# 5. Optional: Remote API Configuration
echo ""
echo "🤖 Brain Configuration:"
echo "By default, ButterClaw routes to a local Ollama instance."
read -p "Do you want to use a remote API (like Gemini) instead? (y/N): " USE_REMOTE < /dev/tty || USE_REMOTE="n"

if [[ "$USE_REMOTE" =~ ^[Yy]$ ]]; then
    read -p "Enter LLM Provider (e.g., gemini): " PROVIDER < /dev/tty
    read -p "Enter your API Key: " API_KEY < /dev/tty
    sed -i "s/LLM_PROVIDER=.*/LLM_PROVIDER=$PROVIDER/" .env
    sed -i "s/LLM_API_KEY=.*/LLM_API_KEY=$API_KEY/" .env
    echo "✅ Remote API configured."
fi

# 6. Generate Local TLS Certificates for the Nginx Ingress
echo ""
echo "🔐 Forging local TLS certificates for secure routing..."
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx/certs/butterclaw.key \
    -out nginx/certs/butterclaw.crt \
    -subj "/C=US/ST=State/L=City/O=ButterClaw/CN=localhost" 2>/dev/null

# 7. Bring the Sentinel Online
echo "🚀 Igniting the LLM-in-the-middle proxy..."
docker compose up -d --build

echo "------------------------------------------------------"
echo "✅ DEPLOYMENT SUCCESSFUL."
echo "🦞 The Sentinel is now watching the room."
echo ""
echo "API & Dashboard available at: https://localhost"
echo "(Note: Accept the self-signed certificate in your browser for local testing)"
echo ""
echo "Your unique Instance ID: $INSTANCE_ID"
echo "Your private Ntfy Topic: https://ntfy.sh/$UNIQUE_NTFY"
echo ""
echo "To view live telemetry, run: cd butterclaw && docker compose logs -f"