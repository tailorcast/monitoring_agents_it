"""Tests for SSL certificate collector.

The badssl.com family is used as fixtures: always-on, purpose-built and stable
per case, so these tests do not depend on the user's config.yaml being populated.
"""

import asyncio
import socket
import pytest
from unittest.mock import patch

from src.collectors.ssl_collector import SSLCollector
from src.config.models import SSLCertTargetConfig, ThresholdsConfig
from src.services.metric_history import MetricHistoryStore
from src.utils.metrics import CollectorResult
from src.utils.status import HealthStatus

# Fixtures imported from conftest.py: ssl_configs, thresholds, logger


# Defaults, so threshold tests do not depend on the user's config.yaml.
DEFAULT_THRESHOLDS = ThresholdsConfig().__dict__


def target(host, name="test", **kwargs):
    """Build a single SSL target config."""
    return SSLCertTargetConfig(host=host, name=name, **kwargs)


async def check_one(host, logger, thresholds=None, **kwargs):
    """Run the collector against one host and return the single result."""
    collector = SSLCollector(
        [target(host, **kwargs)], thresholds or DEFAULT_THRESHOLDS, logger
    )
    results = await collector.collect()
    assert len(results) == 1
    return results[0]


@pytest.mark.asyncio
async def test_ssl_collector_valid_cert_green(logger):
    """A valid, trusted, long-lived certificate is GREEN."""
    result = await check_one("badssl.com", logger)

    assert result.collector_name == "ssl"
    assert result.status == HealthStatus.GREEN
    assert result.error is None
    assert result.metrics["days_until_expiry"] > DEFAULT_THRESHOLDS["ssl_expiry_days_yellow"]
    assert result.metrics["verified"] is True
    assert result.metrics["host"] == "badssl.com"


@pytest.mark.asyncio
async def test_ssl_collector_expired_cert_red(logger):
    """An expired certificate is RED with a negative day count.

    This also proves the two-phase probe works: the certificate failed
    verification, so its dates could only come from the unverified re-probe.
    """
    result = await check_one("expired.badssl.com", logger)

    assert result.status == HealthStatus.RED
    assert result.metrics["days_until_expiry"] < 0
    assert "EXPIRED" in result.message
    assert result.metrics["verified"] is False


@pytest.mark.asyncio
async def test_ssl_collector_hostname_mismatch_red(logger):
    """A certificate that does not cover the probed hostname is RED."""
    result = await check_one("wrong.host.badssl.com", logger)

    assert result.status == HealthStatus.RED
    assert "does not cover" in result.message.lower()
    assert result.metrics["verified"] is False


@pytest.mark.asyncio
async def test_ssl_collector_incomplete_chain_red(logger):
    """A missing intermediate is RED, and is not mislabelled as an expiry.

    This is the common nginx misconfiguration: the leaf is perfectly valid but
    every non-browser client rejects the chain.
    """
    result = await check_one("incomplete-chain.badssl.com", logger)

    assert result.status == HealthStatus.RED
    assert "chain" in result.message.lower()
    # The leaf itself is still in date -- the problem is the chain, not time.
    assert result.metrics["days_until_expiry"] > 0


@pytest.mark.asyncio
async def test_ssl_collector_untrusted_root_red(logger):
    """A self-signed / untrusted chain is RED."""
    result = await check_one("untrusted-root.badssl.com", logger)

    assert result.status == HealthStatus.RED
    assert result.metrics["verify_code"] in (18, 19)


@pytest.mark.asyncio
async def test_ssl_collector_dns_failure_red(logger):
    """A hostname that cannot resolve is RED, not a crash.

    .invalid is reserved by RFC 2606, so this is guaranteed NXDOMAIN.
    """
    result = await check_one("no-such-host.invalid", logger, timeout_s=5)

    assert result.status == HealthStatus.RED
    assert "dns" in result.message.lower()


@pytest.mark.asyncio
async def test_ssl_collector_connection_refused_red(logger):
    """A closed port on a resolvable host is RED.

    Refused is distinct from a timeout: the remote definitively answered
    "nothing here", so it is the target's problem, not ours.
    """
    # Bind and release to get a port nothing is listening on.
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    closed_port = probe.getsockname()[1]
    probe.close()

    result = await check_one("127.0.0.1", logger, port=closed_port, timeout_s=3)

    assert result.status == HealthStatus.RED
    assert "refused" in result.message.lower()


@pytest.mark.asyncio
async def test_ssl_collector_timeout_is_unknown(logger):
    """A timeout is UNKNOWN, not RED.

    No answer at all is indistinguishable from a blip on the monitoring host's
    own network, and certificate alerts must not flap on our problems.
    """
    with patch(
        'src.collectors.ssl_collector.socket.create_connection',
        side_effect=TimeoutError()
    ):
        result = await check_one("example.com", logger, timeout_s=3)

    assert result.status == HealthStatus.UNKNOWN
    assert "timeout" in result.message.lower()


@pytest.mark.asyncio
async def test_ssl_collector_idn_passed_through_unchanged(logger):
    """A Unicode IDN host reaches the socket layer unchanged.

    Python encodes IDN to punycode internally, so the collector must not do it
    itself, and must report back the name it was given. Offline by design: the
    socket layer is intercepted, so this asserts the passthrough without
    depending on any real IDN domain resolving.
    """
    idn_host = "пример.invalid"   # RFC 2606 reserved, so never resolvable
    addresses = []

    def capture(address, timeout=None):
        addresses.append(address)
        raise TimeoutError()

    with patch(
        'src.collectors.ssl_collector.socket.create_connection',
        side_effect=capture
    ):
        result = await check_one(idn_host, logger, timeout_s=3)

    assert addresses, "create_connection was never called"
    assert addresses[0][0] == idn_host          # Unicode form, not xn--
    assert result.metrics["host"] == idn_host


@pytest.mark.asyncio
async def test_ssl_collector_no_cryptography(logger):
    """Missing cryptography degrades to a single UNKNOWN, not a crash."""
    with patch('src.collectors.ssl_collector.x509', None):
        collector = SSLCollector([target("badssl.com")], DEFAULT_THRESHOLDS, logger)
        results = await collector.collect()

    assert len(results) == 1
    assert results[0].status == HealthStatus.UNKNOWN
    assert results[0].target_name == "all"


@pytest.mark.asyncio
async def test_ssl_collector_empty_config(logger):
    """No configured targets yields no results."""
    collector = SSLCollector([], DEFAULT_THRESHOLDS, logger)

    assert await collector.collect() == []


@pytest.mark.asyncio
async def test_ssl_collector_parallel_execution(logger):
    """Multiple hosts are probed concurrently, not serially."""
    hosts = [
        target("badssl.com", "a"),
        target("expired.badssl.com", "b"),
        target("wrong.host.badssl.com", "c"),
        target("untrusted-root.badssl.com", "d"),
    ]
    collector = SSLCollector(hosts, DEFAULT_THRESHOLDS, logger)

    loop = asyncio.get_event_loop()
    start = loop.time()
    results = await collector.collect()
    duration = loop.time() - start

    assert len(results) == len(hosts)
    # Four sequential probes (two round trips each for the failing three) would
    # take far longer than this.
    assert duration < 20


def test_ssl_expiry_threshold_boundaries(logger):
    """Threshold boundaries, offline.

    30 days must be GREEN: that is certbot's renewal point, where a healthy
    certificate legitimately sits. Alerting there would be permanent noise.
    """
    collector = SSLCollector([], DEFAULT_THRESHOLDS, logger)

    def status_for(days):
        return collector._determine_status(
            "ssl_expiry_days", days, higher_is_worse=False
        )

    assert status_for(40) == HealthStatus.GREEN
    assert status_for(30) == HealthStatus.GREEN   # certbot renewal point
    assert status_for(22) == HealthStatus.GREEN
    assert status_for(21) == HealthStatus.YELLOW
    assert status_for(8) == HealthStatus.YELLOW
    assert status_for(7) == HealthStatus.RED
    assert status_for(0) == HealthStatus.RED


def test_ssl_red_is_never_dampened(logger, tmp_path):
    """An SSL RED must reach the report as RED, never dampened to YELLOW.

    history_filter dampens first-occurrence threshold breaches, which is right
    for noisy sampled metrics but wrong here: days_until_expiry is monotonic,
    and the store resets daily, so dampening would downgrade the first report of
    every day -- including the day a certificate actually expires.

    get_red_metric_keys returning [] is exactly what workflow._history_filter
    treats as "pass through unchanged".
    """
    store = MetricHistoryStore(history_file=str(tmp_path / "history.json"), logger=logger)

    result = CollectorResult(
        collector_name="ssl",
        target_name="Example site cert",
        status=HealthStatus.RED,
        metrics={
            "days_until_expiry": -3,
            "not_after": "2026-09-26",
            "host": "example.com",
        },
        message="EXPIRED 3d ago (2026-09-26)",
        error=None,
    )

    assert store.get_red_metric_keys(result, DEFAULT_THRESHOLDS) == []

    # Guard the reasoning above against a future "helpful" addition.
    assert not any(
        collector == "ssl" for collector, _ in MetricHistoryStore.THRESHOLD_METRICS
    )


@pytest.mark.asyncio
async def test_ssl_collector_real_targets(ssl_configs, thresholds, logger):
    """The configured targets all resolve and report a certificate."""
    collector = SSLCollector(ssl_configs, thresholds, logger)
    results = await collector.collect()

    assert len(results) == len(ssl_configs)

    configured_names = {c.name for c in ssl_configs}
    for result in results:
        assert result.collector_name == "ssl"
        assert result.target_name in configured_names
        assert result.status != HealthStatus.UNKNOWN, (
            f"{result.target_name}: {result.message}"
        )
        assert "days_until_expiry" in result.metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
