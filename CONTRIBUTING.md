# Contributing to XReader

Thank you for your interest in contributing to XReader! This guide will help you get started with the contribution process. XReader is an asynchronous CLI tool for scraping tweet data from Nitter instances, enhancing it with AI-generated metadata, and saving it for analysis. We welcome contributions from the community to improve functionality, fix bugs, and enhance documentation.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Code Contributions](#code-contributions)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Coding Guidelines](#coding-guidelines)
- [Documentation](#documentation)
- [Community](#community)

## Code of Conduct

In the interest of fostering an open and welcoming environment, we expect all contributors to be respectful and considerate of others. By participating in this project, you agree to:

- Be respectful of different viewpoints and experiences.
- Gracefully accept constructive criticism.
- Focus on what is best for the community.
- Show empathy towards other community members.

Examples of unacceptable behavior include harassment, derogatory comments, personal attacks, or any form of discrimination. If you encounter or witness such behavior, please report it to the project maintainers.

## How Can I Contribute?

There are many ways to contribute to XReader, and we appreciate all forms of help. Here are some primary avenues for contribution:

### Reporting Bugs

If you find a bug in XReader, please help us by reporting it. Before creating a bug report, check the existing issues to see if it has already been reported. When filing a bug report:

- Use a clear and descriptive title.
- Describe the exact steps to reproduce the issue.
- Include details about your environment (OS, Python version, XReader version).
- Attach relevant logs, screenshots, or sample data if applicable.
- Specify the expected behavior and what actually happened.

File bug reports by opening an issue on our repository with the label "bug".

### Suggesting Enhancements

We welcome ideas for new features or improvements to existing functionality. To suggest an enhancement:

- Open an issue with the label "enhancement".
- Clearly describe the enhancement and its benefits.
- If possible, provide examples or mockups of how it would work.
- Mention any potential challenges or considerations.

### Code Contributions

If you'd like to contribute code to fix a bug or implement a feature:

1. **Fork the Repository**: Create your own fork of the XReader repository.
2. **Clone the Fork**: Clone your fork to your local machine.
3. **Create a Branch**: Create a branch with a descriptive name related to the issue or feature (e.g., `fix-scraper-timeout` or `add-custom-model-support`).
4. **Make Changes**: Implement your changes, adhering to the coding guidelines below.
5. **Test Your Changes**: Ensure your changes work as expected and do not break existing functionality.
6. **Commit Your Changes**: Write clear, concise commit messages following conventional commit format if possible (e.g., `feat: add retry logic for API calls` or `fix: correct URL normalization`).
7. **Push to Your Fork**: Push your branch to your forked repository.
8. **Submit a Pull Request**: Open a pull request (PR) from your branch to the main XReader repository's `main` branch. Reference the related issue(s) in your PR description.

## Development Setup

To set up XReader for development:

1. **Clone the Repository** (or your fork):
   ```bash
   git clone <repository-url>
   cd xreader
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set Up Environment**:
   Copy `.env.example` to `.env` and configure it with necessary API keys or custom settings:
   ```bash
   cp .env.example .env
   ```

4. **Run Tests** (if applicable):
   Currently, XReader may not have a formal test suite. Manually test your changes by running the tool with sample data:
   ```bash
   python xread.py
   ```

5. **Debugging**:
   Enable detailed logging or use debug tools as needed to troubleshoot your changes. Check the `debug_output` directory for failed parses if relevant.

## Pull Request Process

1. **Ensure Your PR is Complete**:
   - Update documentation if your changes affect usage or configuration.
   - Include a clear description of what your PR does and why it's needed.
   - Reference related issues (e.g., "Fixes #123" or "Addresses #456").

2. **Code Review**:
   - Maintainers will review your PR for code quality, functionality, and alignment with project goals.
   - Be prepared to make revisions based on feedback. Respond to comments and update your PR as needed.

3. **Merge**:
   - Once approved, your PR will be merged into the main branch. If you're not a maintainer, a project member will handle the merge.

We aim to review PRs promptly, but please be patient if there are delays. Feel free to follow up on your PR if it hasn't been reviewed after a reasonable time.

## Coding Guidelines

We strive to maintain a consistent and readable codebase. Please follow these guidelines when contributing code:

- **Python Style**: Adhere to PEP 8 for Python code. Use tools like `flake8` or `pylint` to check style if possible.
- **Type Hints**: Include type hints where feasible to improve code clarity and IDE support.
- **Documentation**: Add docstrings to functions, classes, and modules. Comment complex logic for clarity.
- **Modularity**: Keep code modular and reusable. Avoid large, monolithic functions or files.
- **Error Handling**: Implement robust error handling, especially for network or API interactions. Log errors appropriately.
- **Dependencies**: Avoid adding unnecessary dependencies. If a new library is needed, justify its inclusion in your PR.

## Documentation

Documentation is crucial for XReader's usability. If your contribution affects how the tool is used or configured:

- Update relevant files like `README.md`, `USAGE.md`, or `CONFIGURATION.md` with your changes.
- If adding a new feature, provide usage examples or configuration details in the appropriate documentation file.
- For significant changes, consider updating the `CHANGELOG.md` with a summary under the "Unreleased" section.

## Community

Join our community for discussions or to seek help:

- **Issues**: Use GitHub Issues for bug reports, feature requests, or general questions.
- **Discussions**: If available, participate in GitHub Discussions for broader topics or brainstorming.
- **Contact**: For direct inquiries, reach out to the maintainers via email or other provided channels (if any).

Your contributions help make XReader a better tool for everyone. We appreciate your time and effort in improving this project!

For an overview of the project, refer to [README.md](README.md). For usage instructions, see [USAGE.md](USAGE.md).
