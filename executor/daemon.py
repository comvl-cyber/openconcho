#!/usr/bin/env python3
"""OpenConcho Executor Daemon.

Polls /var/lib/openconcho/requests for queued requests and applies them via GitHub MCP + GitOps.
"""
import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path

import yaml

from executor.github import GitHubMCP
from executor.queue import scan_queue, lock_queue, unlock_queue, Request
from executor.executor import process_request

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('executor')

REQUESTS_DIR = Path(os.environ.get('OPENCONCHO_REQUESTS_DIR', '/var/lib/openconcho/requests'))
POLL_INTERVAL = float(os.environ.get('OPENCONCHO_POLL_INTERVAL', '5'))
GITHUB_CONFIG = Path(os.environ.get('HERMES_CONFIG', '/root/.hermes/config.yaml'))


class ExecutorDaemon:
    def __init__(self):
        self.running = False
        self.session = None
        self.github = None

    async def start(self):
        log.info('Starting OpenConcho executor daemon')
        log.info('Queue directory: %s', REQUESTS_DIR)
        log.info('Poll interval: %.1fs', POLL_INTERVAL)

        # Verify queue directory exists and has correct permissions
        if not REQUESTS_DIR.exists():
            log.error('Queue directory does not exist: %s', REQUESTS_DIR)
            return False
        if REQUESTS_DIR.stat().st_mode & 0o777 != 0o700:
            log.error('Queue directory must be mode 0700: %s', REQUESTS_DIR)
            return False

        # Initialize GitHub MCP session
        try:
            config = yaml.safe_load(GITHUB_CONFIG.read_text())
            gh_config = config['mcp_servers']['github']
            # The real session will be created per-request to avoid long-lived connections
            # For now, we create a fresh session for each request in process_request
            # But we need a way to create sessions - we'll pass a factory
            self._gh_config = gh_config
            log.info('GitHub MCP configured: %s', gh_config['url'])
        except Exception as e:
            log.error('Failed to load GitHub MCP config: %s', e)
            return False

        self.running = True
        return True

    def _create_github_session(self):
        """Create a fresh GitHub MCP session for a request."""
        import re
        from dotenv import dotenv_values
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client, create_mcp_http_client

        env = {**dotenv_values("/root/.hermes/.env"), **os.environ}
        headers = {k: re.sub(r"\$\{([A-Za-z_][A-Za-z_0-9]*)\}", lambda m: env.get(m[1]) or "", v)
                   for k, v in self._gh_config['headers'].items()}

        class SessionContext:
            def __init__(self, url, headers):
                self.url = url
                self.headers = headers
                self.session = None
                self.http = None
                self.streams = None

            async def __aenter__(self):
                self.http = await create_mcp_http_client(headers=self.headers).__aenter__()
                self.streams = await streamable_http_client(self.url, http_client=self.http).__aenter__()
                self.session = ClientSession(*self.streams)
                await self.session.initialize()
                return GitHubMCP(self.session)

            async def __aexit__(self, *args):
                if self.session:
                    await self.session.__aexit__(*args)
                if self.streams:
                    await self.streams.__aexit__(*args)
                if self.http:
                    await self.http.__aexit__(*args)

        return SessionContext(self._gh_config['url'], headers)

    async def run_once(self):
        """Process one batch of requests."""
        # Acquire queue lock
        fd = lock_queue(REQUESTS_DIR)
        if fd is None:
            log.debug('Queue locked by another process, skipping')
            return

        try:
            requests = scan_queue(REQUESTS_DIR)
            queued = [r for r in requests if r.status == 'queued']

            for req in queued:
                log.info('Processing request %s (%s)', req.id[:8], req.kind)

                # Create fresh GitHub session for this request
                async with self._create_github_session() as github:
                    # Get K8s revision for validation
                    async def get_revision(path):
                        # In production, this would query the Kubernetes API
                        # For now, we read from GitHub to get the yaml, and use a mock revision
                        blob = await github.read(path)
                        return 'live-' + blob.commit[:8], blob.text

                    async def flux_reconcile():
                        # In production: flux reconcile + kubectl rollout restart + wait for health
                        log.info('Flux reconcile triggered for request %s', req.id[:8])
                        # Simulate: kubectl -n honcho rollout restart deployment/honcho-api deployment/honcho-deriver
                        # kubectl -n honcho wait --for=condition=available deployment/honcho-api deployment/honcho-deriver
                        # curl -f https://honcho.example.com/health
                        pass

                    processed = await process_request(req, github, get_revision, flux_reconcile)
                    processed.save(REQUESTS_DIR)
                    log.info('Request %s -> %s', req.id[:8], processed.status)

        finally:
            unlock_queue(fd)

    async def run(self):
        while self.running:
            try:
                await self.run_once()
            except Exception as e:
                log.exception('Error in executor loop: %s', e)
            await asyncio.sleep(POLL_INTERVAL)

    def stop(self):
        log.info('Stopping executor daemon')
        self.running = False


async def main():
    daemon = ExecutorDaemon()
    if not await daemon.start():
        return 1

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, daemon.stop)

    await daemon.run()
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))