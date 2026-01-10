# ccburn Packaging Specification

## Overview

This specification defines the packaging and distribution strategy for ccburn, a terminal-based Claude Code usage limit visualizer. The goal is to make ccburn easily installable via PyPI while maintaining automated CI/CD for quality assurance.

---

## Pre-requisites (Human Required)

These steps require manual intervention and must be completed BEFORE Claude Code implements this spec:

### 1. PyPI Account Setup

- [x] Create account at https://pypi.org (if not exists)
- [x] Create the ccburn project on PyPI BEFORE first release:
  - Go to https://pypi.org/manage/account/publishing/
  - Under "Add a new pending publisher", fill in:
    - PyPI Project Name: `ccburn`
    - Owner: `JuanjoFuchs`
    - Repository: `ccburn`
    - Workflow name: `release.yml`
    - Environment name: `release`
  - Click "Add"
  - This creates a "pending" trusted publisher that activates on first upload

> **Why this order?** Trusted publishing requires the project to exist OR a "pending publisher"
> to be configured. By creating a pending publisher first, the release workflow can publish
> the first release without manual intervention.

### 2. GitHub Repository Setup

- [x] Ensure repository exists at `github.com/JuanjoFuchs/ccburn`
- [x] Create GitHub environment named `release` (Settings > Environments)

### 3. WinGet Token Setup

- [x] Create GitHub Personal Access Token:
  - Go to GitHub Settings > Developer Settings > Personal Access Tokens > Tokens (classic)
  - Create new token with `public_repo` scope
  - Set expiration (recommend 1 year)
- [x] Add repository secret:
  - Go to repository Settings > Secrets and variables > Actions
  - Create secret named `WINGET_TOKEN` with the token value

### 4. Initial WinGet Submission (After First Release)

After the first GitHub Release with Windows EXE is created, Claude Code triggers the initial submission:

```bash
# Claude Code runs this after first release exists
gh workflow run winget-init.yml -f version=0.1.0
```

The workflow automatically:
- Generates manifests from the release
- Adds `UpgradeBehavior: uninstallPrevious` to the installer manifest
- Submits PR to microsoft/winget-pkgs

**No manual editing required!**

- [ ] Wait for Microsoft approval (24-48 hours)
- [ ] After approval, the `winget-publish.yml` workflow handles all future updates automatically

---

## Implementation Tasks (Claude Code)

Claude Code should implement ALL of the following in one shot.

> **IMPORTANT DISTINCTION**:
> - Claude Code **creates the workflow files** (`.yml` files) - it does NOT run them
> - The workflows run automatically in GitHub Actions when triggered by events (push, tag, release)
> - Claude Code **does run** the validation commands locally (ruff, pytest, build, twine)
> - Claude Code **can trigger** workflows via `gh workflow run` command
>
> **BEST PRACTICE**: All publishing (PyPI, GitHub Releases, WinGet) happens in CI/CD pipelines,
> never locally. This ensures reproducible builds, audit trails, and secure secret management.
> Claude Code only triggers the pipelines - it does not publish directly.

### Files to Create
- [ ] `.github/workflows/ci.yml` - CI workflow
- [ ] `.github/workflows/release.yml` - Release workflow
- [ ] `.github/workflows/winget-publish.yml` - WinGet auto-publish (for updates)
- [ ] `.github/workflows/winget-init.yml` - WinGet initial submission (manual trigger, one-time use)
- [ ] `LICENSE` - MIT license file

> **Note on WinGet Manifests**: WinGet manifests are NOT stored in this repository. The `wingetcreate`
> tool generates them automatically from the installer URL and submits them directly to microsoft/winget-pkgs.
> The manifest examples in this spec are for documentation purposes only - they show what wingetcreate
> will generate. See [WinGet Manifest Handling](#winget-manifest-handling) for details.

### Files to Update
- [ ] `pyproject.toml` - Add missing fields, dev dependencies
- [ ] `src/ccburn/__init__.py` - Add version export (if not exists)

### LICENSE File Content

Create `LICENSE` with standard MIT license:

```
MIT License

Copyright (c) 2025 JuanjoFuchs

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Validation
- [ ] Run `ruff check src/ tests/` - passes
- [ ] Run `pytest` - all tests pass
- [ ] Run `python -m build` - builds successfully
- [ ] Run `twine check dist/*` - validates package

---

## Distribution Channels

### 1. PyPI (Primary)

**Package Name:** `ccburn`

```bash
pip install ccburn
```

**Target Audience:** Claude Code users who want to monitor their usage limits.

**Requirements:**
- Python 3.10+ (matches Claude Code's typical environment)
- Cross-platform support (Linux, macOS, Windows)

### 2. Windows Executable

**Standalone EXE** for Windows users who prefer not to install Python.

Built with PyInstaller, distributed via:
- GitHub Releases (direct download)
- Windows Package Manager (winget)

```powershell
# Via winget
winget install JuanjoFuchs.ccburn

# Direct download from GitHub Releases
# ccburn-X.Y.Z-windows-x64.exe
```

### 3. WinGet (Windows Package Manager)

**Package Identifier:** `JuanjoFuchs.ccburn`

```powershell
winget install ccburn
winget upgrade ccburn
```

### 4. GitHub Releases

Direct source distribution for users who prefer installing from source or need specific versions.

```bash
pip install git+https://github.com/JuanjoFuchs/ccburn.git
```

## Package Configuration

### pyproject.toml Updates

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ccburn"
version = "0.1.0"
description = "Terminal-based Claude Code usage limit visualizer with real-time burn-up charts"
authors = [{name = "JuanjoFuchs"}]
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
keywords = ["claude", "anthropic", "usage", "monitoring", "tui", "visualization", "cli"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Utilities",
    "Topic :: System :: Monitoring",
]
dependencies = [
    "typer[all]>=0.9.0",
    "rich>=13.0.0",
    "plotext>=5.2.0",
    "httpx>=0.25.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
    "build>=1.0.0",
    "twine>=4.0.0",
    "pyinstaller>=6.0.0",
]

[project.scripts]
ccburn = "ccburn.main:app"

[project.urls]
Homepage = "https://github.com/JuanjoFuchs/ccburn"
Repository = "https://github.com/JuanjoFuchs/ccburn.git"
Issues = "https://github.com/JuanjoFuchs/ccburn/issues"
Documentation = "https://github.com/JuanjoFuchs/ccburn#readme"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-dir]
"" = "src"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
ignore = [
    "E501",  # line too long, handled by formatter
    "B008",  # do not perform function calls in argument defaults (typer uses this)
]

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
check_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
strict_equality = true

[[tool.mypy.overrides]]
module = ["plotext", "httpx"]
ignore_missing_imports = true

[tool.pytest.ini_options]
minversion = "7.0"
addopts = "-ra -q --strict-markers"
testpaths = ["tests"]
```

## CI/CD Pipeline

### GitHub Actions Workflows

> **When Workflows Run** (automatic, in GitHub Actions - NOT during Claude Code implementation):
> | Workflow | Trigger | Purpose |
> |----------|---------|---------|
> | `ci.yml` | Push to main, PRs | Lint, test, build validation |
> | `release.yml` | Git tag `v*` pushed | Build packages, EXE, publish to PyPI, create release |
> | `winget-init.yml` | Manual trigger (one-time) | Initial WinGet package submission |
> | `winget-publish.yml` | GitHub Release published | Auto-update WinGet package |

#### 1. CI Workflow (`.github/workflows/ci.yml`)

Runs on every push and pull request to ensure code quality.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - name: Install dependencies
        run: pip install ruff
      - name: Run linter
        run: ruff check src/ tests/

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      - name: Run tests
        run: pytest --cov=ccburn --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        if: matrix.python-version == '3.10'

  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - name: Install build tools
        run: pip install build twine
      - name: Build package
        run: python -m build
      - name: Validate package
        run: twine check dist/*
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
```

#### 2. Release Workflow (`.github/workflows/release.yml`)

Triggers on version tags to build packages, Windows executable, publish to PyPI, and create GitHub releases.

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  # Job 1: Build and publish Python packages
  build-packages:
    runs-on: ubuntu-latest
    environment: release
    permissions:
      id-token: write  # For trusted publishing
    outputs:
      version: ${{ steps.version.outputs.version }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install build tools
        run: pip install build twine

      - name: Get version
        id: version
        run: |
          VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")
          echo "version=$VERSION" >> $GITHUB_OUTPUT

      - name: Verify version matches tag
        run: |
          TAG_VERSION=${GITHUB_REF#refs/tags/v}
          if [ "$TAG_VERSION" != "${{ steps.version.outputs.version }}" ]; then
            echo "Tag version ($TAG_VERSION) doesn't match package version (${{ steps.version.outputs.version }})"
            exit 1
          fi

      - name: Build package
        run: python -m build

      - name: Validate package
        run: twine check dist/*

      - name: Upload package artifacts
        uses: actions/upload-artifact@v4
        with:
          name: python-packages
          path: dist/

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1

  # Job 2: Build Windows executable
  build-executable:
    runs-on: windows-latest
    needs: build-packages
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Build executable
        run: |
          pyinstaller --onefile --name ccburn --console src/ccburn/main.py

      - name: Rename executable with version
        run: |
          mv dist/ccburn.exe dist/ccburn-${{ needs.build-packages.outputs.version }}-windows-x64.exe

      - name: Test executable
        run: |
          dist/ccburn-${{ needs.build-packages.outputs.version }}-windows-x64.exe --version

      - name: Upload executable artifact
        uses: actions/upload-artifact@v4
        with:
          name: windows-executable
          path: dist/*.exe

  # Job 3: Create GitHub Release with all artifacts
  create-release:
    runs-on: ubuntu-latest
    needs: [build-packages, build-executable]
    permissions:
      contents: write
    steps:
      - name: Download all artifacts
        uses: actions/download-artifact@v4
        with:
          path: artifacts

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            artifacts/python-packages/*
            artifacts/windows-executable/*
          generate_release_notes: true
```

#### 3. WinGet Initial Submission Workflow (`.github/workflows/winget-init.yml`)

One-time workflow for submitting a NEW package to WinGet. Fully automated - no manual editing needed.

```yaml
name: WinGet Initial Submission

on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Version to submit (e.g., 1.0.0)'
        required: true

jobs:
  submit:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Get release asset URL
        id: asset
        run: |
          $release = Invoke-RestMethod -Uri "https://api.github.com/repos/${{ github.repository }}/releases/tags/v${{ github.event.inputs.version }}"
          $asset = $release.assets | Where-Object { $_.name -like "*windows-x64.exe" }
          if (-not $asset) {
            Write-Error "Windows executable not found in release v${{ github.event.inputs.version }}"
            exit 1
          }
          echo "url=$($asset.browser_download_url)" >> $env:GITHUB_OUTPUT

      - name: Download wingetcreate
        run: |
          Invoke-WebRequest -Uri "https://aka.ms/wingetcreate/latest" -OutFile wingetcreate.exe

      - name: Generate manifests (without submitting)
        run: |
          .\wingetcreate.exe new ${{ steps.asset.outputs.url }} `
            --out ./generated-manifests

      - name: Add UpgradeBehavior to installer manifest
        run: |
          $installerFile = Get-ChildItem -Path ./generated-manifests -Filter "*.installer.yaml" -Recurse | Select-Object -First 1
          $content = Get-Content $installerFile.FullName -Raw
          # Add UpgradeBehavior after InstallerType line
          $content = $content -replace '(InstallerType: portable)', "`$1`nUpgradeBehavior: uninstallPrevious"
          Set-Content -Path $installerFile.FullName -Value $content
          Write-Host "Updated manifest:"
          Get-Content $installerFile.FullName

      - name: Submit manifests to WinGet
        run: |
          $manifestDir = Get-ChildItem -Path ./generated-manifests -Directory | Select-Object -First 1
          .\wingetcreate.exe submit $manifestDir.FullName `
            --token ${{ secrets.WINGET_TOKEN }}
```

> **Note**: This workflow automatically adds `UpgradeBehavior: uninstallPrevious` to the manifest
> before submitting, so no manual PR editing is needed.

#### 4. WinGet Publish Workflow (`.github/workflows/winget-publish.yml`)

Automatically submits package updates to Windows Package Manager after a release.

```yaml
name: Publish to WinGet

on:
  release:
    types: [released]
  workflow_dispatch:
    inputs:
      version:
        description: 'Version to publish (e.g., 1.0.0)'
        required: true

jobs:
  publish:
    runs-on: windows-latest
    steps:
      - name: Get version from release or input
        id: version
        run: |
          if ("${{ github.event_name }}" -eq "release") {
            $version = "${{ github.event.release.tag_name }}".TrimStart('v')
          } else {
            $version = "${{ github.event.inputs.version }}"
          }
          echo "version=$version" >> $env:GITHUB_OUTPUT

      - name: Get release asset URL
        id: asset
        run: |
          $release = Invoke-RestMethod -Uri "https://api.github.com/repos/${{ github.repository }}/releases/tags/v${{ steps.version.outputs.version }}"
          $asset = $release.assets | Where-Object { $_.name -like "*windows-x64.exe" }
          echo "url=$($asset.browser_download_url)" >> $env:GITHUB_OUTPUT

      - name: Download wingetcreate
        run: |
          Invoke-WebRequest -Uri "https://aka.ms/wingetcreate/latest" -OutFile wingetcreate.exe

      - name: Submit to WinGet
        run: |
          .\wingetcreate.exe update JuanjoFuchs.ccburn `
            --version ${{ steps.version.outputs.version }} `
            --urls ${{ steps.asset.outputs.url }} `
            --submit `
            --token ${{ secrets.WINGET_TOKEN }}
```

## Versioning Strategy

### Single Source of Truth

Version is defined only in `pyproject.toml`:

```toml
[project]
version = "0.1.0"
```

### Semantic Versioning

Follow [SemVer](https://semver.org/):
- **MAJOR**: Breaking changes to CLI interface or output format
- **MINOR**: New features, new display options
- **PATCH**: Bug fixes, performance improvements

### Initial Release Strategy

Start with **0.1.0** (not 1.0.0) to allow iteration:

```
0.1.0  → First public release (PyPI + GitHub)
0.1.1  → Bug fixes, packaging issues
0.1.x  → Iterate until stable and WinGet approved
1.0.0  → First "stable" release after validation
```

**Why 0.x.x first?**
- Signals "beta" status to users
- Allows fixing packaging/distribution issues without "breaking" semver
- WinGet approval can take 24-48 hours per submission
- Gives time to validate all distribution channels work correctly

### Version Access in Code

```python
# In ccburn/__init__.py or via importlib.metadata
try:
    from importlib.metadata import version
    __version__ = version("ccburn")
except Exception:
    __version__ = "0.0.0"
```

## Release Process

### 1. Prepare Release

```bash
# Update version in pyproject.toml
# Update CHANGELOG.md (if exists)
# Commit changes
git add pyproject.toml
git commit -m "Bump version to X.Y.Z"
```

### 2. Create Tag

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main --tags
```

### 3. Automated Release

GitHub Actions will automatically:
1. Run CI checks
2. Build sdist and wheel
3. Publish to PyPI
4. Create GitHub Release with artifacts

## Package Contents

### Included Files

```
dist/
  ccburn-X.Y.Z.tar.gz      # Source distribution
  ccburn-X.Y.Z-py3-none-any.whl  # Wheel (pure Python)
```

### Source Distribution Contains

```
ccburn-X.Y.Z/
  src/
    ccburn/
      __init__.py
      main.py
      cli.py
      app.py
      data/
      display/
      utils/
  tests/
  pyproject.toml
  README.md
  LICENSE
```

## Installation Methods

### End Users

```bash
# From PyPI (recommended)
pip install ccburn

# From GitHub
pip install git+https://github.com/JuanjoFuchs/ccburn.git

# Specific version
pip install ccburn==0.1.0
```

### Developers

```bash
# Clone and install in editable mode
git clone https://github.com/JuanjoFuchs/ccburn.git
cd ccburn
pip install -e ".[dev]"
```

## Quality Gates

Before any release, the following must pass:

1. **Linting**: `ruff check src/ tests/`
2. **Tests**: `pytest` with all tests passing
3. **Build**: `python -m build` succeeds
4. **Package Validation**: `twine check dist/*` passes

## PyPI Trusted Publishing Setup

See [Pre-requisites: PyPI Account Setup](#1-pypi-account-setup) for configuration steps.

**How it works**: Trusted Publishing uses OpenID Connect (OIDC) to authenticate GitHub Actions
workflows to PyPI without storing API tokens. The release workflow requests a short-lived token
from PyPI, which validates the request against the configured trusted publisher rules.

## WinGet Manifest Handling

### Key Concept: Manifests Live in microsoft/winget-pkgs, Not This Repo

WinGet manifests are stored exclusively in the [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs)
repository, NOT in the ccburn repository. The `wingetcreate` tool handles everything:

| Scenario | Command | What Happens |
|----------|---------|--------------|
| **Initial submission** | `wingetcreate new <url>` | Downloads installer, extracts metadata, generates manifests, submits PR to winget-pkgs |
| **Updates** | `wingetcreate update <id> --urls <url>` | Fetches existing manifest from winget-pkgs, updates version/URL/hash, submits PR |

**Why no local manifests?**
- `wingetcreate` generates manifests dynamically from installer URLs
- The `update` command automatically fetches existing manifests from winget-pkgs
- Storing manifests locally would create duplication and sync issues
- Real-world projects (PowerToys, Windows Terminal, k6) all use this approach

**Note**: The manifest examples below are for documentation only - they show what wingetcreate
will generate. Claude Code does NOT create these files.

### Reference: Manifest Structure in winget-pkgs

After submission, manifests will exist at `microsoft/winget-pkgs/manifests/j/JuanjoFuchs/ccburn/<version>/`:

```
manifests/
  j/
    JuanjoFuchs/
      ccburn/
        0.1.0/
          JuanjoFuchs.ccburn.yaml
          JuanjoFuchs.ccburn.installer.yaml
          JuanjoFuchs.ccburn.locale.en-US.yaml
```

### Reference: Main Manifest (`JuanjoFuchs.ccburn.yaml`)

```yaml
PackageIdentifier: JuanjoFuchs.ccburn
PackageVersion: 0.1.0
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.10.0
```

### Reference: Installer Manifest (`JuanjoFuchs.ccburn.installer.yaml`)

```yaml
PackageIdentifier: JuanjoFuchs.ccburn
PackageVersion: 0.1.0
InstallerType: portable
UpgradeBehavior: uninstallPrevious  # IMPORTANT: Prevents duplicate entries after upgrades
Commands:
  - ccburn
Installers:
  - Architecture: x64
    InstallerUrl: https://github.com/JuanjoFuchs/ccburn/releases/download/v0.1.0/ccburn-0.1.0-windows-x64.exe
    InstallerSha256: <SHA256_HASH>
ManifestType: installer
ManifestVersion: 1.10.0
ReleaseDate: 2026-01-09
```

> **IMPORTANT**: The `UpgradeBehavior: uninstallPrevious` field is critical for portable apps.
> Without it, WinGet leaves duplicate entries in the Apps list after each upgrade.
> This must be manually added once in the initial submission; `wingetcreate` will
> preserve it automatically in subsequent updates.

### Reference: Locale Manifest (`JuanjoFuchs.ccburn.locale.en-US.yaml`)

```yaml
PackageIdentifier: JuanjoFuchs.ccburn
PackageVersion: 0.1.0
PackageLocale: en-US
Publisher: JuanjoFuchs
PublisherUrl: https://github.com/JuanjoFuchs
PublisherSupportUrl: https://github.com/JuanjoFuchs/ccburn/issues
PackageName: ccburn
PackageUrl: https://github.com/JuanjoFuchs/ccburn
License: MIT
ShortDescription: Terminal-based Claude Code usage limit visualizer
Description: A terminal visualization tool for monitoring Claude Code usage limits with real-time burn-up charts. Shows session and weekly limits with pace indicators.
ReleaseNotesUrl: https://github.com/JuanjoFuchs/ccburn/releases/tag/v0.1.0
Tags:
  - cli
  - monitoring
  - terminal
  - tui
  - visualization
  - claude
  - anthropic
  - usage
Documentations:
  - DocumentLabel: README
    DocumentUrl: https://github.com/JuanjoFuchs/ccburn#readme
ManifestType: defaultLocale
ManifestVersion: 1.10.0
```

## WinGet Setup

### One-Time Configuration

1. **Create GitHub Personal Access Token**:
   - Go to GitHub Settings > Developer Settings > Personal Access Tokens > Tokens (classic)
   - Create new token with `public_repo` scope
   - Copy the token (you won't see it again)

2. **Add Repository Secret**:
   - Go to repository Settings > Secrets and variables > Actions
   - Create new secret named `WINGET_TOKEN`
   - Paste the token value

3. **Initial Submission to microsoft/winget-pkgs**:
   - Fork https://github.com/microsoft/winget-pkgs
   - Create manifest files in `manifests/j/JuanjoFuchs/ccburn/0.1.0/`
   - **IMPORTANT**: Include `UpgradeBehavior: uninstallPrevious` in installer manifest
   - Submit PR following their contribution guidelines
   - Wait for Microsoft validation and merge (usually 24-48 hours)
   - After approval, automated updates will work

### How WinGet Updates Work

1. Release workflow creates GitHub Release with Windows EXE
2. WinGet publish workflow triggers on release
3. `wingetcreate` automatically:
   - Downloads the EXE
   - Calculates SHA256 hash
   - Creates updated manifests (preserves `UpgradeBehavior` field)
   - Submits PR to microsoft/winget-pkgs
4. Microsoft validates and merges (usually within 24-48 hours)

### Local Testing

Test the WinGet submission locally before relying on automation:

```powershell
# Download wingetcreate
Invoke-WebRequest -Uri "https://aka.ms/wingetcreate/latest" -OutFile wingetcreate.exe

# Test without submitting (generates manifests only)
.\wingetcreate.exe update JuanjoFuchs.ccburn `
    --version 0.1.0 `
    --urls https://github.com/JuanjoFuchs/ccburn/releases/download/v0.1.0/ccburn-0.1.0-windows-x64.exe `
    --out ./manifests

# Review generated manifests
cat ./manifests/JuanjoFuchs.ccburn.installer.yaml

# Submit for real (requires token)
.\wingetcreate.exe update JuanjoFuchs.ccburn `
    --version 0.1.0 `
    --urls https://github.com/JuanjoFuchs/ccburn/releases/download/v0.1.0/ccburn-0.1.0-windows-x64.exe `
    --submit `
    --token $env:WINGET_TOKEN
```

### Troubleshooting

#### Missing Windows Executable in Release

**Symptom**: WinGet workflow fails with "asset not found"

**Solution**: Ensure release workflow completed successfully and includes `ccburn-X.Y.Z-windows-x64.exe`

#### Authentication Failure

**Symptom**: `wingetcreate` fails with 401/403 error

**Solutions**:
- Verify `WINGET_TOKEN` secret is set correctly
- Ensure token has `public_repo` scope
- Check if token has expired

#### PR Rejected by Microsoft

**Symptom**: PR to winget-pkgs is closed with validation errors

**Common causes**:
- SHA256 hash mismatch (re-upload release asset)
- Invalid manifest schema (check ManifestVersion)
- Missing required fields
- Version already exists (bump version)

#### Duplicate Entries After Upgrade

**Symptom**: Multiple ccburn entries appear in Windows Apps list

**Solution**: Ensure `UpgradeBehavior: uninstallPrevious` is in installer manifest

**User workaround** (if already affected):
```powershell
# Uninstall all versions
winget uninstall ccburn --all-versions
# Reinstall latest
winget install ccburn
```

#### Fork Out of Sync

**Symptom**: PR has merge conflicts

**Solution**: Sync your fork of microsoft/winget-pkgs:
```bash
gh repo sync JuanjoFuchs/winget-pkgs --source microsoft/winget-pkgs
```

## Future Considerations

### Possible Additions

- **Homebrew Formula**: Could be added if there's demand from macOS users.
- **Conda Package**: Could be added if there's demand from data science community.
- **Documentation Site**: If the project grows, consider ReadTheDocs or GitHub Pages.
- **Pre-release Versions**: Publish to TestPyPI for beta testing before major releases.

---

## Acceptance Criteria

### Automated by Claude Code (verify after implementation)

- [ ] `pyproject.toml` updated with all required fields
- [ ] `LICENSE` file exists with MIT license
- [ ] `.github/workflows/ci.yml` exists and is valid YAML
- [ ] `.github/workflows/release.yml` exists and is valid YAML
- [ ] `.github/workflows/winget-init.yml` exists and is valid YAML
- [ ] `.github/workflows/winget-publish.yml` exists and is valid YAML
- [ ] `ruff check src/ tests/` passes
- [ ] `pytest` passes
- [ ] `python -m build` succeeds
- [ ] `twine check dist/*` passes
- [ ] `ccburn --version` shows correct version

### Verified After First Release (requires human pre-requisites)

- [ ] CI workflow runs on PRs (after push to GitHub)
- [ ] Release workflow publishes to PyPI (after tag push + PyPI trusted publishing setup)
- [ ] Release workflow builds Windows executable (after tag push)
- [ ] WinGet workflow submits package updates (after WINGET_TOKEN secret + initial WinGet approval)
- [ ] Package installable via `pip install ccburn` (after PyPI publish)
- [ ] Package installable via `winget install ccburn` (after WinGet approval)

---

## Release Checklist

When ready to release:

```bash
# 1. Ensure all pre-requisites are complete (see top of spec)

# 2. Update version in pyproject.toml
#    Edit: version = "0.1.0"

# 3. Commit the version bump
git add pyproject.toml
git commit -m "Bump version to 0.1.0"
git push origin main

# 4. Create and push tag (triggers release workflow)
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0

# 5. Monitor GitHub Actions for:
#    - build-packages job (PyPI publish)
#    - build-executable job (Windows EXE)
#    - create-release job (GitHub Release)
#    - winget-publish workflow (WinGet PR)

# 6. First release only (Claude Code runs this):
gh workflow run winget-init.yml -f version=0.1.0
# Workflow auto-adds UpgradeBehavior - no manual editing needed!

# 7. Wait for Microsoft to approve WinGet PR (24-48 hours)
```
