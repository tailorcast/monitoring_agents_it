"""Shared SSH utilities for VPS and Docker collectors."""

import logging
from typing import Optional

try:
    import paramiko
except ImportError:
    paramiko = None

from ..config.models import VPSServerConfig


class SSHHelper:
    """Helper class for SSH operations."""

    @staticmethod
    def create_client(config: VPSServerConfig, logger: logging.Logger) -> Optional[object]:
        """
        Create SSH client with key authentication.

        Args:
            config: VPS server configuration
            logger: Logger instance

        Returns:
            paramiko.SSHClient or None if paramiko not installed

        Raises:
            Exception: If connection fails
        """
        if paramiko is None:
            logger.error("paramiko library not installed")
            raise ImportError("paramiko library required for SSH connections")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            logger.debug(f"Connecting to {config.host}:{config.port} as {config.username}")

            client.connect(
                hostname=config.host,
                port=config.port,
                username=config.username,
                key_filename=config.ssh_key_path,
                timeout=10,
                banner_timeout=10
            )

            logger.debug(f"Successfully connected to {config.host}")
            return client

        except paramiko.AuthenticationException as e:
            logger.error(f"Authentication failed for {config.host}: {e}")
            raise

        except paramiko.SSHException as e:
            logger.error(f"SSH error connecting to {config.host}: {e}")
            raise

        except Exception as e:
            logger.error(f"Failed to connect to {config.host}: {e}")
            raise

    @staticmethod
    def exec_command(
        client: object,
        command: str,
        timeout: int = 30,
        logger: Optional[logging.Logger] = None
    ) -> str:
        """
        Execute command on SSH client and return stdout.

        Args:
            client: paramiko.SSHClient instance
            command: Command to execute
            timeout: Command timeout in seconds
            logger: Optional logger instance

        Returns:
            str: Command stdout

        Raises:
            RuntimeError: If command fails (non-zero exit code)
            TimeoutError: If command times out
        """
        if logger:
            logger.debug(f"Executing command: {command}")

        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

            # Wait for command to complete
            exit_code = stdout.channel.recv_exit_status()

            # Read outputs
            stdout_data = stdout.read().decode('utf-8', errors='replace')
            stderr_data = stderr.read().decode('utf-8', errors='replace')

            if exit_code != 0:
                error_msg = f"Command failed with exit code {exit_code}: {stderr_data.strip()}"
                if logger:
                    logger.error(error_msg)
                raise RuntimeError(error_msg)

            if logger:
                logger.debug(f"Command completed successfully ({len(stdout_data)} bytes)")

            return stdout_data

        except Exception as e:
            if logger:
                logger.error(f"Command execution failed: {e}")
            raise

    @staticmethod
    def close_client(client: object, logger: Optional[logging.Logger] = None) -> None:
        """
        Close SSH client connection.

        Args:
            client: paramiko.SSHClient instance
            logger: Optional logger instance
        """
        try:
            if client:
                client.close()
                if logger:
                    logger.debug("SSH connection closed")
        except Exception as e:
            if logger:
                logger.warning(f"Error closing SSH connection: {e}")

    @staticmethod
    def is_available() -> bool:
        """
        Check if paramiko is available.

        Returns:
            bool: True if paramiko is installed
        """
        return paramiko is not None
