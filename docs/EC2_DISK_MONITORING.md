# EC2 Disk Space Monitoring

## Overview

The EC2 collector supports monitoring disk space usage via CloudWatch custom metrics published by the CloudWatch Agent. This feature allows you to track disk utilization alongside CPU metrics and receive alerts when disk space runs low.

## Prerequisites

### 1. CloudWatch Agent Installed

The CloudWatch Agent must be installed and configured on your EC2 instances to publish disk metrics.

### 2. Metrics Published

The agent must publish `disk_used_percent` metric to the `CWAgent` namespace in CloudWatch.

### 3. IAM Permissions

EC2 instances need the following IAM permissions:
- `cloudwatch:PutMetricData` - To publish metrics
- Your monitoring system needs `cloudwatch:GetMetricStatistics` and `cloudwatch:ListMetrics` - To read metrics

## CloudWatch Agent Setup

### Install CloudWatch Agent

#### Amazon Linux 2 / RHEL / CentOS
```bash
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
sudo rpm -U ./amazon-cloudwatch-agent.rpm
```

#### Ubuntu / Debian
```bash
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i -E ./amazon-cloudwatch-agent.deb
```

### Configure Agent

Create `/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json`:

```json
{
  "metrics": {
    "namespace": "CWAgent",
    "metrics_collected": {
      "disk": {
        "measurement": [
          {
            "name": "used_percent",
            "rename": "disk_used_percent",
            "unit": "Percent"
          }
        ],
        "metrics_collection_interval": 300,
        "resources": [
          "*"
        ]
      }
    }
  }
}
```

**Configuration Options**:
- `namespace`: Must be `CWAgent` to match the collector's default
- `metrics_collection_interval`: 300 seconds (5 minutes) recommended
- `resources`: `["*"]` monitors all filesystems, or specify specific mount points like `["/", "/data"]`

### Start Agent

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -s \
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

### Verify Agent is Running

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a query -m ec2 -c default
```

Expected output:
```json
{
  "status": "running",
  "starttime": "2024-01-15T10:30:00",
  "version": "1.x.x"
}
```

## Configuration

### Basic Configuration

Monitor root filesystem with auto-detection of device and filesystem type:

```yaml
targets:
  ec2_instances:
    - instance_id: "i-1234567890abcdef0"
      name: "prod-server"
      region: "us-east-1"
      monitor_disk: true  # Enable disk monitoring
```

### Advanced Configuration

Explicit device and filesystem type specification:

```yaml
targets:
  ec2_instances:
    - instance_id: "i-1234567890abcdef0"
      name: "prod-server"
      region: "us-east-1"
      monitor_disk: true
      disk_path: "/"              # Mount point to monitor (default: /)
      disk_namespace: "CWAgent"   # CloudWatch namespace (default: CWAgent)
      disk_device: "nvme0n1p1"    # Device name (auto-detected if omitted)
      disk_fstype: "ext4"         # Filesystem type (auto-detected if omitted)
```

### Monitor Multiple Mount Points

To monitor a specific mount point like `/data`:

```yaml
targets:
  ec2_instances:
    - instance_id: "i-1234567890abcdef0"
      name: "storage-server"
      region: "us-east-1"
      monitor_disk: true
      disk_path: "/data"          # Monitor /data instead of /
      disk_device: "nvme1n1"      # Device for /data mount
      disk_fstype: "xfs"          # Filesystem type
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `monitor_disk` | boolean | `false` | Enable disk space monitoring |
| `disk_namespace` | string | `"CWAgent"` | CloudWatch namespace for disk metrics |
| `disk_path` | string | `"/"` | Mount point to monitor |
| `disk_device` | string | `null` | Device name (auto-detected if null) |
| `disk_fstype` | string | `null` | Filesystem type (auto-detected if null) |

## Behavior

### With Disk Monitoring Enabled

When `monitor_disk: true`:

- **GREEN**: Both CPU and disk within thresholds
- **YELLOW**: Either metric unavailable OR between yellow/red thresholds
- **RED**: Either CPU or disk exceeds red threshold (worst status wins)

**Example output**:
```
Running, CPU: 25.5%, Disk free: 35.2%
```

### Without Disk Monitoring (Default)

When `monitor_disk: false` or omitted:

- Behaves exactly as before (backward compatible)
- Only monitors CPU utilization
- No CloudWatch Agent required
- Disk metrics not included in output

**Example output**:
```
Running, CPU: 25.5%
```

### Metrics Unavailable

If `monitor_disk: true` but CloudWatch Agent not installed or not publishing metrics:

- **Overall status**: YELLOW (degraded but not critical)
- **CPU metrics**: Still reported normally
- **Disk metrics**: Show as `null` in output
- **Warning logged**: Suggests CloudWatch Agent setup

**Example output**:
```
Running, CPU: 25.5%, Disk: unavailable
```

## Thresholds

Disk space thresholds are configured in the `thresholds` section:

```yaml
thresholds:
  disk_free_red: 10      # RED if <= 10% free space
  disk_free_yellow: 20   # YELLOW if <= 20% free space
```

**Important Notes**:
- Thresholds use "disk_free" (lower is worse)
- CloudWatch Agent publishes "disk_used" (higher is worse)
- The collector automatically converts: `disk_free = 100 - disk_used`
- Default thresholds: RED at 10% free, YELLOW at 20% free

## Auto-Discovery

When `disk_device` and `disk_fstype` are not specified, the collector automatically discovers them:

1. First attempts to fetch metrics with partial dimensions (InstanceId + path)
2. If no data found, calls `list_metrics` to discover available metrics
3. Uses the first matching metric's dimensions
4. Retries fetch with discovered dimensions

**Benefits**:
- Simpler configuration
- Works across different instance types (nvme vs xvd devices)
- Handles filesystem type variations

**Trade-off**:
- One additional API call on first metric fetch (cached thereafter)

## Troubleshooting

### No disk metrics appearing

**Symptoms**: Status is YELLOW, message shows "Disk: unavailable"

**Solutions**:

1. **Verify CloudWatch Agent is running**:
   ```bash
   sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
       -a query -m ec2 -c default
   ```

2. **Check metrics in CloudWatch Console**:
   - Navigate to CloudWatch > Metrics
   - Namespace: `CWAgent`
   - Metric: `disk_used_percent`
   - Dimensions: InstanceId, path, device, fstype

3. **Enable auto-discovery**:
   - Omit `disk_device` and `disk_fstype` in config
   - Let the collector discover correct values

4. **Check agent logs**:
   ```bash
   sudo tail -f /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
   ```

### Wrong device/mount monitored

**Symptoms**: Metrics show but values seem incorrect

**Solutions**:

1. **Check available mount points**:
   ```bash
   df -h
   ```

2. **Verify `disk_path` matches exactly**:
   ```yaml
   disk_path: "/"      # Must match mount point exactly
   ```

3. **List available metrics in CloudWatch**:
   ```bash
   aws cloudwatch list-metrics \
       --namespace CWAgent \
       --metric-name disk_used_percent \
       --dimensions Name=InstanceId,Value=i-1234567890abcdef0
   ```

### Status YELLOW with disk enabled

**Symptoms**: Status is YELLOW even though instance is healthy

**Common Causes**:

1. **CloudWatch Agent not installed/running**
   - Install and start the agent (see setup instructions above)

2. **Agent not publishing to correct namespace**
   - Verify agent config has `"namespace": "CWAgent"`
   - Restart agent after config changes

3. **IAM permissions missing**
   - Instance role needs `cloudwatch:PutMetricData`
   - Monitoring system needs `cloudwatch:GetMetricStatistics` and `cloudwatch:ListMetrics`

4. **Metrics delayed**
   - CloudWatch has 5-15 minute delay for metric availability
   - Wait and retry after a few minutes

5. **Wrong region**
   - Verify `region` in config matches instance's actual region

### High false positive rate

**Symptoms**: Frequent RED alerts but disk is not actually full

**Solutions**:

1. **Adjust thresholds**:
   ```yaml
   thresholds:
     disk_free_red: 5      # More aggressive threshold
     disk_free_yellow: 15
   ```

2. **Check if monitoring correct filesystem**:
   - Some instances have small boot partitions
   - Monitor `/data` or application-specific mount instead

3. **Verify CloudWatch Agent configuration**:
   - Ensure monitoring correct filesystems
   - Exclude temporary or system filesystems

## Cost Considerations

### CloudWatch Custom Metrics Pricing

- **Cost**: $0.30 per metric per month (first 10,000 metrics)
- **Each filesystem/mount point**: 1 metric
- **Billing**: Prorated for partial months

### Cost Optimization

1. **Monitor only critical filesystems**:
   ```json
   "resources": ["/"]  // Only root, not all filesystems
   ```

2. **Increase collection interval**:
   ```json
   "metrics_collection_interval": 300  // 5 minutes instead of 1 minute
   ```

3. **Use high-resolution metrics sparingly**:
   - Standard resolution (5 minutes) is sufficient for disk monitoring
   - High-resolution (1 minute) adds 10x cost

### Example Cost Calculation

For 10 EC2 instances, each monitoring root filesystem:
- 10 instances × 1 metric per instance = 10 metrics
- 10 metrics × $0.30 = **$3.00/month**

## Best Practices

1. **Start with root filesystem monitoring**:
   - Most critical for system stability
   - Add other mounts as needed

2. **Use auto-discovery for device/fstype**:
   - Simplifies configuration
   - Works across instance types

3. **Set conservative thresholds initially**:
   - Start with RED at 10%, YELLOW at 20%
   - Adjust based on workload patterns

4. **Monitor agent health**:
   - Set up alerts for agent stopped/failed
   - Regularly review agent logs

5. **Test before production**:
   - Verify metrics appear in CloudWatch Console
   - Test with low disk space scenario
   - Confirm alerts trigger correctly

6. **Document instance-specific requirements**:
   - Different applications need different thresholds
   - Large log directories may need separate monitoring

## Example Configurations

### Web Application Server
```yaml
- instance_id: "i-web123"
  name: "web-server-prod"
  region: "us-east-1"
  monitor_disk: true
  disk_path: "/"
  # Auto-detect device/fstype
```

### Database Server with Separate Data Volume
```yaml
- instance_id: "i-db123"
  name: "postgres-prod"
  region: "us-east-1"
  monitor_disk: true
  disk_path: "/var/lib/postgresql"
  disk_device: "nvme1n1"
  disk_fstype: "ext4"
```

### Storage Server with Multiple Volumes
```yaml
# Monitor system volume
- instance_id: "i-storage123"
  name: "storage-server-root"
  region: "us-east-1"
  monitor_disk: true
  disk_path: "/"

# Monitor data volume (configure as separate instance entry)
- instance_id: "i-storage123"
  name: "storage-server-data"
  region: "us-east-1"
  monitor_disk: true
  disk_path: "/data"
  disk_device: "nvme1n1"
  disk_fstype: "xfs"
```

## Metrics Output

### Without Disk Monitoring
```json
{
  "instance_id": "i-123",
  "region": "us-east-1",
  "state": "running",
  "cpu_usage_pct": 25.5,
  "instance_type": "t3.medium"
}
```

### With Disk Monitoring
```json
{
  "instance_id": "i-123",
  "region": "us-east-1",
  "state": "running",
  "cpu_usage_pct": 25.5,
  "instance_type": "t3.medium",
  "disk_free_pct": 35.2
}
```

### Disk Metrics Unavailable
```json
{
  "instance_id": "i-123",
  "region": "us-east-1",
  "state": "running",
  "cpu_usage_pct": 25.5,
  "instance_type": "t3.medium",
  "disk_free_pct": null
}
```

## Related Documentation

- [AWS CloudWatch Agent Documentation](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html)
- [CloudWatch Metrics Pricing](https://aws.amazon.com/cloudwatch/pricing/)
- [EC2 IAM Roles](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)
