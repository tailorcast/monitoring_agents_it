#!/usr/bin/env python3
"""
Script to generate visual representation of the monitoring workflow graph.

Usage:
    python scripts/visualize_workflow.py [output_path]

Requirements:
    pip install pygraphviz  # or pip install grandalf
"""

import sys
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.loader import ConfigLoader
from src.workflow import MonitoringWorkflow
from src.utils.logger import setup_logger


def main():
    """Generate workflow graph visualization."""
    # Setup logging
    logger = setup_logger("visualize")

    # Parse arguments
    output_path = sys.argv[1] if len(sys.argv) > 1 else "workflow_graph.png"
    config_path = sys.argv[2] if len(sys.argv) > 2 else "config/config.yaml"

    try:
        logger.info(f"Loading configuration from {config_path}")
        config = ConfigLoader.load_from_file(config_path)

        logger.info("Initializing workflow")
        workflow = MonitoringWorkflow(config, logger)

        logger.info(f"Generating graph visualization: {output_path}")
        success = workflow.visualize_graph(output_path)

        if success:
            logger.info(f"✓ Graph visualization saved to: {output_path}")
            print(f"\nGraph saved to: {output_path}")
            print("\nWorkflow structure:")
            print("  aggregate (data collection)")
            print("      ↓")
            print("  analyze (AI analysis)")
            print("      ↓")
            print("  generate_report (format report)")
            print("      ↓")
            print("  send_telegram (deliver report)")
            print("      ↓")
            print("  END")
            return 0
        else:
            logger.error("Failed to generate visualization")
            print("\nTo install required dependencies:")
            print("  pip install pygraphviz")
            print("  # or")
            print("  pip install grandalf")
            return 1

    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        print(f"\nError: Configuration file not found: {config_path}")
        print("Create it from template: cp config/config.example.yaml config/config.yaml")
        return 1

    except Exception as e:
        logger.error(f"Visualization failed: {e}", exc_info=True)
        print(f"\nError: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
