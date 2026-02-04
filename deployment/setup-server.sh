#!/bin/bash
# Server setup helper - checks and installs Docker Compose if needed

set -e

echo "Checking Docker installation..."

# Check if docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed"
    echo "Install Docker first:"
    echo "  sudo yum install -y docker"
    echo "  sudo systemctl start docker"
    echo "  sudo systemctl enable docker"
    echo "  sudo usermod -aG docker \$USER"
    exit 1
fi

echo "✅ Docker is installed: $(docker --version)"

# Check if docker compose (v2) is available
if docker compose version &> /dev/null; then
    echo "✅ Docker Compose plugin is installed: $(docker compose version)"
else
    echo "❌ Docker Compose plugin not found"
    echo ""
    echo "Installing Docker Compose plugin..."

    # Install Docker Compose plugin
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

    echo "✅ Docker Compose plugin installed: $(docker compose version)"
fi

echo ""
echo "✅ Server is ready for deployment!"
echo ""
echo "Next steps:"
echo "  1. Create config/config.yaml from config/config.example.yaml"
echo "  2. Create .env file with your credentials"
echo "  3. Copy SSH keys to secrets/ folder"
echo "  4. Run: docker compose -f deployment/docker-compose.yml up -d"
