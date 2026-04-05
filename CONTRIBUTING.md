# Contributing to ButterClaw

First off, thank you for helping us secure the future of agentic AI! 🕶️🦞

## How to Contribute
We are looking for help in the following areas:
- **Behavioral Signatures:** Adding new JSON-native reasoning patterns for catching MCP poisoning.
- **Log Watcher Optimization:** Improving the `watcher.py` to handle even more massive context windows (128K+).
- **Integration:** Testing ButterClaw alongside platforms like OpenClaw, Obot, and GStack.

## Pull Request Process
1. **Open an Issue:** Before starting a major change, please open an issue to discuss the approach.
2. **Branching:** Create a feature branch from `main`.
3. **Tests:** Ensure your changes do not break the core inode tracking or retry queue logic.
4. **Submit:** Open a PR with a clear description of the "behavioral gap" your code addresses.

## Security Policy
**Do not report security vulnerabilities via public issues.** If you find a vulnerability in ButterClaw itself, please email [security@butterclaw.tech] to follow a coordinated disclosure process.

## Code of Conduct
ButterClaw follows the standard Linux Foundation/AAIF Code of Conduct. Be excellent to each other.