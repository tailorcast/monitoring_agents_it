"""TLS certificate expiry collector.

Gives advance warning that a certificate renewal has silently failed, while the
site still works. The API collector already goes RED on an expired certificate,
but only once it has expired and the site is already down -- this collector
turns that into a numeric countdown with days of lead time.
"""

import asyncio
import dataclasses
import datetime
import logging
import socket
import ssl
from typing import List, Optional, Tuple

try:
    import certifi
except ImportError:
    certifi = None

try:
    from cryptography import x509
except ImportError:
    x509 = None

try:
    from langsmith import traceable
except ImportError:
    # Graceful fallback if langsmith not installed
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not args else decorator(args[0])

from ..config.models import SSLCertTargetConfig
from ..utils.status import HealthStatus
from ..utils.metrics import CollectorResult
from ..utils.sanitize import sanitize_error
from .base import BaseCollector, safe_collect


# Cap concurrent probes. Every collector shares the default thread executor
# (default size min(32, cpu+4)), so an unbounded fan-out here would starve the
# SSH collectors -- indirectly corrupting the VPS load measurement that
# host_lock.py exists to protect.
_MAX_CONCURRENT_PROBES = 8

# OpenSSL verify result codes we classify specifically.
_CODE_CERT_NOT_YET_VALID = 9
_CODE_HOSTNAME_MISMATCH = 62
# "cannot build a trusted chain" -- the classic nginx missing-intermediate case.
_CODES_UNTRUSTED_CHAIN = frozenset({
    2,   # unable to get issuer certificate
    18,  # self-signed certificate
    19,  # self-signed certificate in certificate chain
    20,  # unable to get local issuer certificate
    21,  # unable to verify the first certificate
})


@dataclasses.dataclass
class _ProbeOutcome:
    """Raw result of a TLS probe, before any health judgement."""
    der: Optional[bytes] = None
    tls_version: Optional[str] = None
    verify_code: Optional[int] = None
    verify_message: Optional[str] = None


class SSLCollector(BaseCollector):
    """Collector for TLS certificate expiry and chain validity."""

    def __init__(
        self,
        config: List[SSLCertTargetConfig],
        thresholds: dict,
        logger: logging.Logger
    ):
        """
        Initialize SSL certificate collector.

        Args:
            config: List of TLS certificate targets
            thresholds: System thresholds including ssl_expiry_days_red/_yellow
            logger: Logger instance
        """
        super().__init__(config, thresholds, logger)

    @safe_collect
    async def collect(self) -> List[CollectorResult]:
        """
        Check the certificate of every configured host concurrently.

        Returns:
            List[CollectorResult]: One result per configured target
        """
        if certifi is None or x509 is None:
            missing = "certifi" if certifi is None else "cryptography"
            self.logger.warning(f"{missing} library not available")
            return [CollectorResult(
                collector_name="ssl",
                target_name="all",
                status=HealthStatus.UNKNOWN,
                metrics={},
                message=f"{missing} library not installed",
                error=f"{missing} not available"
            )]

        if not self.config:
            self.logger.info("No SSL certificate targets configured")
            return []

        self.logger.info(f"Checking {len(self.config)} TLS certificate(s)")

        # Created per run, never in __init__: an asyncio primitive binds to the
        # loop that awaits it, and the scheduler builds a fresh loop each cycle
        # (same trap host_lock.py documents).
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_PROBES)

        tasks = [self._check_target(target, semaphore) for target in self.config]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                target_name = self.config[i].name if i < len(self.config) else "unknown"
                self.logger.error(f"Certificate check failed for {target_name}: {result}")
                safe_msg = sanitize_error(result)
                final_results.append(CollectorResult(
                    collector_name="ssl",
                    target_name=target_name,
                    status=HealthStatus.UNKNOWN,
                    metrics={},
                    message=f"Check failed: {safe_msg}",
                    error=safe_msg
                ))
            else:
                final_results.append(result)

        return final_results

    @traceable(name="SSLCollector._check_target")
    async def _check_target(
        self,
        config: SSLCertTargetConfig,
        semaphore: asyncio.Semaphore
    ) -> CollectorResult:
        """
        Probe one host and judge its certificate.

        Args:
            config: Target configuration
            semaphore: Limits how many blocking probes run at once

        Returns:
            CollectorResult: Health result for this target
        """
        async with semaphore:
            try:
                # socket/ssl are blocking and collect() is gathered alongside
                # every other collector, so the probe must not run on the loop.
                #
                # The outer timeout is generous because it cannot cancel the
                # worker thread -- the socket timeout is the real bound. It
                # exists for the case the socket timeout cannot cover: a hung
                # getaddrinfo, which no socket option bounds. create_connection
                # also spends a full timeout per dead address on dual-stack
                # hosts with broken IPv6, hence 2x + slack.
                outcome = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._probe_sync,
                        config.host,
                        config.port,
                        config.timeout_s,
                    ),
                    timeout=config.timeout_s * 2 + 5,
                )

            except socket.gaierror:
                # Deterministic and non-transient: the configured name does not
                # resolve. That is a real outage, not a blip.
                return self._failure(
                    config, HealthStatus.RED, "DNS resolution failed", "gaierror"
                )

            except ConnectionRefusedError:
                return self._failure(
                    config,
                    HealthStatus.RED,
                    f"Connection refused on port {config.port}",
                    "ConnectionRefusedError",
                )

            except ConnectionResetError:
                return self._failure(
                    config, HealthStatus.RED, "Connection reset", "ConnectionResetError"
                )

            except (asyncio.TimeoutError, TimeoutError):
                # No answer at all is indistinguishable from a blip on the
                # monitoring container's own network. RED here would make cert
                # alerts flap on our problems rather than the target's.
                return self._failure(
                    config,
                    HealthStatus.UNKNOWN,
                    f"Connection timeout after {config.timeout_s:.0f}s",
                    "TimeoutError",
                )

            except ssl.SSLError as e:
                # Not a verification failure (those are caught in the probe):
                # protocol or handshake level. TLS is broken here regardless of
                # what the certificate dates say.
                safe_msg = sanitize_error(e)
                return self._failure(
                    config, HealthStatus.RED, f"TLS handshake failed: {safe_msg}", safe_msg
                )

            except OSError as e:
                # ENETUNREACH / EHOSTUNREACH and friends -- likely our side.
                safe_msg = sanitize_error(e)
                return self._failure(
                    config, HealthStatus.UNKNOWN, f"Connection failed: {safe_msg}", safe_msg
                )

        return self._judge(config, outcome)

    def _probe_sync(
        self,
        host: str,
        port: int,
        timeout: float
    ) -> _ProbeOutcome:
        """
        Blocking two-phase TLS probe.

        Phase 1 is a fully verified handshake -- exactly what a real browser or
        client sees. If and only if verification fails, phase 2 reconnects with
        verification disabled purely to retrieve the certificate, so the report
        can say *why* and *when*. That second phase is necessary because
        getpeercert() returns an empty dict once verify_mode is CERT_NONE; the
        DER has to be parsed by hand.

        Args:
            host: Hostname to probe (Unicode IDN is accepted as-is)
            port: TLS port
            timeout: Per-connection timeout in seconds

        Returns:
            _ProbeOutcome: DER bytes plus any verification error

        Raises:
            OSError, ssl.SSLError: Connection-level failures, handled by caller
        """
        # Verify against certifi, never the system trust store. A bare
        # create_default_context() has no usable CA file on python.org macOS
        # builds (every host fails with code 20, including valid ones) but works
        # in the python:3.13-slim container -- a dev/prod split that would make
        # this collector RED-flood locally. certifi also matches what httpx and
        # therefore api_collector verify against, so the two agree.
        context = ssl.create_default_context(cafile=certifi.where())

        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=host) as tls:
                    return _ProbeOutcome(
                        der=tls.getpeercert(binary_form=True),
                        tls_version=tls.version(),
                    )

        except ssl.SSLCertVerificationError as e:
            verify_code = getattr(e, "verify_code", None)
            verify_message = getattr(e, "verify_message", None) or str(e)

        # The certificate cannot be trusted, but we still want its dates.
        unverified = ssl.create_default_context(cafile=certifi.where())
        unverified.check_hostname = False
        unverified.verify_mode = ssl.CERT_NONE

        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                with unverified.wrap_socket(sock, server_hostname=host) as tls:
                    return _ProbeOutcome(
                        der=tls.getpeercert(binary_form=True),
                        tls_version=tls.version(),
                        verify_code=verify_code,
                        verify_message=verify_message,
                    )
        except Exception as e:
            # Best effort: keep the verification verdict even without the cert.
            self.logger.debug(f"Unverified re-probe of {host} failed: {e}")
            return _ProbeOutcome(
                verify_code=verify_code,
                verify_message=verify_message,
            )

    def _judge(
        self,
        config: SSLCertTargetConfig,
        outcome: _ProbeOutcome
    ) -> CollectorResult:
        """
        Turn a probe outcome into a health result.

        Args:
            config: Target configuration
            outcome: Result of the TLS probe

        Returns:
            CollectorResult: Judged result
        """
        cert = None
        if outcome.der:
            try:
                cert = x509.load_der_x509_certificate(outcome.der)
            except Exception as e:
                self.logger.warning(f"Could not parse certificate for {config.host}: {e}")

        if cert is None:
            # Verification failed and the cert could not be retrieved or parsed.
            detail = outcome.verify_message or "certificate unavailable"
            return self._failure(
                config, HealthStatus.RED, f"Certificate check failed: {detail}", detail
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        not_after = cert.not_valid_after_utc
        not_before = cert.not_valid_before_utc
        # Floor, so a cert two hours past expiry reads -1 rather than 0 and we
        # never over-report the time remaining.
        days = int((not_after - now).total_seconds() // 86400)
        expiry_date = not_after.date().isoformat()

        metrics = self._build_metrics(config, cert, outcome, days, not_after)

        # Date first, deliberately. OpenSSL reports only the first verify error
        # it hits, so an expired certificate that also has a chain problem
        # surfaces as code 20, not 10. The parsed date is authoritative.
        if days < 0:
            return self._result(
                config, HealthStatus.RED, metrics,
                f"EXPIRED {abs(days)}d ago ({expiry_date})"
            )

        if not_before > now or outcome.verify_code == _CODE_CERT_NOT_YET_VALID:
            return self._result(
                config, HealthStatus.RED, metrics,
                f"Not valid until {not_before.date().isoformat()}"
            )

        if outcome.verify_code == _CODE_HOSTNAME_MISMATCH:
            return self._result(
                config, HealthStatus.RED, metrics,
                "Certificate does not cover this hostname"
            )

        if outcome.verify_code in _CODES_UNTRUSTED_CHAIN:
            # The leaf can be perfectly valid while a missing intermediate
            # breaks every non-browser client. Quote the leaf's remaining days
            # so nobody reads this as an expiry problem.
            return self._result(
                config, HealthStatus.RED, metrics,
                f"Certificate chain not trusted: {outcome.verify_message} "
                f"(leaf valid {days}d)"
            )

        if outcome.verify_code is not None:
            return self._result(
                config, HealthStatus.RED, metrics,
                f"Certificate verification failed: {outcome.verify_message}"
            )

        # Verified cleanly -- now it is purely a question of time remaining.
        status = self._determine_status("ssl_expiry_days", days, higher_is_worse=False)

        if status == HealthStatus.GREEN:
            message = f"Valid for {days}d (expires {expiry_date})"
        elif status == HealthStatus.YELLOW:
            message = f"Expires in {days}d ({expiry_date}) - renewal overdue"
        else:
            message = f"Expires in {days}d ({expiry_date}) - renew now"

        return self._result(config, status, metrics, message)

    def _build_metrics(
        self,
        config: SSLCertTargetConfig,
        cert,
        outcome: _ProbeOutcome,
        days: int,
        not_after: datetime.datetime
    ) -> dict:
        """
        Build the metrics dict.

        Insertion order is load-bearing: the Telegram report renders only the
        first 3 (report_agent._format_metrics max_items) and the LLM prompt only
        the first 5 (analysis_agent). days_until_expiry is the alert itself,
        not_after saves the reader doing date arithmetic, and host identifies
        which certificate -- target_name is only a friendly label, and every
        host here has its own certificate with its own expiry.

        Args:
            config: Target configuration
            cert: Parsed x509 certificate
            outcome: Probe outcome
            days: Days until expiry (floored)
            not_after: Certificate expiry timestamp

        Returns:
            dict: Ordered metrics
        """
        metrics = {
            "days_until_expiry": days,
            "not_after": not_after.date().isoformat(),
            "host": config.host,
            "verified": outcome.verify_code is None,
            "issuer": self._name_attr(cert.issuer, "issuer"),
            "port": config.port,
            "subject_cn": self._name_attr(cert.subject, "subject"),
        }

        if outcome.tls_version:
            metrics["tls_version"] = outcome.tls_version

        if outcome.verify_code is not None:
            metrics["verify_error"] = outcome.verify_message
            metrics["verify_code"] = outcome.verify_code

        return metrics

    def _name_attr(self, name, kind: str) -> str:
        """
        Extract a human-readable label from an x509 Name.

        Args:
            name: x509.Name to read
            kind: "issuer" (prefers organization) or "subject" (prefers CN)

        Returns:
            str: Best available label, or "unknown"
        """
        oids = (
            [x509.oid.NameOID.ORGANIZATION_NAME, x509.oid.NameOID.COMMON_NAME]
            if kind == "issuer"
            else [x509.oid.NameOID.COMMON_NAME, x509.oid.NameOID.ORGANIZATION_NAME]
        )

        for oid in oids:
            try:
                attrs = name.get_attributes_for_oid(oid)
                if attrs:
                    return str(attrs[0].value)
            except Exception:
                continue

        return "unknown"

    def _result(
        self,
        config: SSLCertTargetConfig,
        status: HealthStatus,
        metrics: dict,
        message: str
    ) -> CollectorResult:
        """
        Build a result for a target whose certificate we successfully read.

        `error` stays None on purpose: MetricHistoryStore treats a non-None
        error as "binary failure, never dampen", so it is a semantic flag rather
        than a free-text field. These are certificate *states*, not exceptions.

        Args:
            config: Target configuration
            status: Health status
            metrics: Metrics dict
            message: Human-readable summary

        Returns:
            CollectorResult: Assembled result
        """
        return CollectorResult(
            collector_name="ssl",
            target_name=config.name,
            status=status,
            metrics=metrics,
            message=message,
            error=None
        )

    def _failure(
        self,
        config: SSLCertTargetConfig,
        status: HealthStatus,
        message: str,
        error: str
    ) -> CollectorResult:
        """
        Build a result for a target we could not reach or verify at all.

        Args:
            config: Target configuration
            status: Health status
            message: Human-readable summary
            error: Sanitized error detail

        Returns:
            CollectorResult: Assembled result
        """
        return CollectorResult(
            collector_name="ssl",
            target_name=config.name,
            status=status,
            metrics={"host": config.host, "port": config.port},
            message=message,
            error=error
        )
