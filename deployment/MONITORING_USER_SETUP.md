# Monitoring User Setup Guide

Create a dedicated least-privilege SSH user for the monitoring agent instead of using your admin key.

## Exact SSH Commands Used by the Agent

| Collector | Commands |
|-----------|----------|
| **VPS** | `top -bn1`, `free -m`, `df -h` |
| **Docker** | `docker ps -a --format "{{json .}}"` |
| **Docker Logs** | `docker compose -f <file> logs --since 4h \| grep -ci ...` |

All are read-only. No writes, no restarts, no destructive operations.

---

## Step 1 — Generate a New SSH Key Pair (local machine)

```bash
ssh-keygen -t ed25519 -C "monitoring-agent" -f ~/.ssh/monitoring_agent_key
```

This creates:
- `~/.ssh/monitoring_agent_key` — private key (stays on your machine / in the agent)
- `~/.ssh/monitoring_agent_key.pub` — public key (goes on the server)

---

## Step 2 — Create the Monitoring User on the Server

SSH in with your admin key for this one-time setup:

```bash
ssh -i ~/.ssh/your_admin_key ubuntu@your-server-ip
```

Then on the server:

```bash
# Create a system user with a home directory
sudo useradd --system --create-home --shell /bin/bash monitoring

# Create .ssh directory
sudo mkdir -p /home/monitoring/.ssh
sudo chmod 700 /home/monitoring/.ssh

# Install the public key (paste the contents of ~/.ssh/monitoring_agent_key.pub)
echo "ssh-ed25519 AAAA... monitoring-agent" | sudo tee /home/monitoring/.ssh/authorized_keys
sudo chmod 600 /home/monitoring/.ssh/authorized_keys
sudo chown -R monitoring:monitoring /home/monitoring/.ssh
```

---

## Step 3 — Grant Docker Access

The `docker` group grants access to the Docker socket. Choose the option that fits your threat model.

### Option A — Docker Group (simple, wider access)

```bash
sudo usermod -aG docker monitoring
```

The `monitoring` user can run any `docker` command. Simple, but if the agent is ever compromised it has full Docker control (docker group access is effectively equivalent to root on the host).

### Option B — Restricted sudo (recommended for production)

```bash
sudo visudo -f /etc/sudoers.d/monitoring
```

Add these lines:

```
monitoring ALL=(root) NOPASSWD: /usr/bin/docker ps -a --format *
monitoring ALL=(root) NOPASSWD: /usr/bin/docker compose -f * logs --since *
```

For most self-hosted setups, **Option A** is the practical choice if you trust the agent machine.

---

## Step 4 — Verify the User Can Run All Needed Commands

Still as admin on the server, test as the new user:

```bash
sudo -u monitoring bash -c 'top -bn1 | head -5'
sudo -u monitoring bash -c 'free -m'
sudo -u monitoring bash -c 'df -h'
sudo -u monitoring bash -c 'docker ps -a --format "{{json .}}"'
sudo -u monitoring bash -c 'docker compose -f /path/to/docker-compose.yml logs --since 4h 2>&1 | grep -ci "error" || true'
```

All should succeed without errors or permission denials.

---

## Step 5 — Update config.yaml

For each VPS, Docker, and Docker Logs target, update the SSH credentials:

```yaml
vps_servers:
  - name: my-server
    host: your-server-ip
    username: monitoring                        # was "ubuntu" or "root"
    ssh_key_path: ~/.ssh/monitoring_agent_key   # new key
    port: 22

docker_logs_targets:
  - name: my-app
    host: your-server-ip
    username: monitoring
    ssh_key_path: ~/.ssh/monitoring_agent_key
    compose_file: /path/to/docker-compose.yml
    error_patterns: "error|exception|fatal"
```

---

## Step 6 — (Optional) Harden SSH on the Server

Add a `Match User` block to `/etc/ssh/sshd_config`:

```
Match User monitoring
    AllowTcpForwarding no
    X11Forwarding no
    PermitTTY no
```

Reload SSH to apply:

```bash
sudo systemctl reload sshd
```

---

## What the Monitoring User Can and Cannot Do

| Can | Cannot |
|-----|--------|
| Read CPU / RAM / disk stats | Modify any files |
| Read Docker container list | Restart or stop containers |
| Read Docker logs | Escalate privileges (unless Option B above) |
| SSH in with the monitoring key | Use the admin key |
| — | Access other users' home directories |

Once set up, the admin key can be removed from the monitoring config entirely. The private key (`monitoring_agent_key`) should only exist on the machine running the agent.
