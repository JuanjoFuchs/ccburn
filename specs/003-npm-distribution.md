# ccburn npm Distribution Specification

## Overview

This specification defines how to distribute ccburn via npm, enabling users to run `npx ccburn` without needing Python installed. The approach downloads pre-built platform-specific binaries from GitHub releases.

**Goal:** `npx ccburn` just works on Windows, Linux, and macOS.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  npm install    │────▶│  postinstall.js  │────▶│ GitHub Releases │
│  or npx ccburn  │     │  detects platform│     │ downloads binary│
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │  bin/ccburn.js   │
                        │  executes binary │
                        └──────────────────┘
```

### How It Works

1. User runs `npx ccburn` or `npm install -g ccburn`
2. npm triggers `postinstall` script
3. `postinstall.js` detects OS (win32/linux/darwin) and arch (x64/arm64)
4. Downloads the correct binary from GitHub releases to `bin/` folder
5. `bin/ccburn.js` (the npm bin entry) spawns the downloaded binary with all arguments

---

## Pre-requisites

### 1. npm Account Setup

- [ ] Create account at https://www.npmjs.com (if not exists)
- [ ] Verify the package name `ccburn` is available
- [ ] Generate npm access token:
  - Go to npmjs.com > Access Tokens > Generate New Token
  - Select "Automation" type (for CI/CD)
  - Copy the token

### 2. GitHub Repository Setup

- [ ] Add repository secret `NPM_TOKEN` with the npm access token
  - Go to repository Settings > Secrets and variables > Actions
  - Create secret named `NPM_TOKEN`

---

## Platform Binary Matrix

The release workflow must build binaries for all supported platforms:

| Platform | Architecture | Binary Name | Runner |
|----------|--------------|-------------|--------|
| Windows | x64 | `ccburn-{version}-windows-x64.exe` | `windows-latest` |
| Linux | x64 | `ccburn-{version}-linux-x64` | `ubuntu-latest` |
| macOS | x64 | `ccburn-{version}-darwin-x64` | `macos-13` |
| macOS | arm64 | `ccburn-{version}-darwin-arm64` | `macos-latest` (M1) |

---

## Implementation Tasks

### Files to Create

- [ ] `npm/package.json` - npm package configuration
- [ ] `npm/bin/ccburn.js` - Wrapper script (npm bin entry)
- [ ] `npm/scripts/postinstall.js` - Binary downloader
- [ ] `npm/README.md` - npm package README
- [ ] `npm/.npmignore` - Files to exclude from npm package
- [ ] `.github/workflows/npm-publish.yml` - npm publish workflow

### Files to Update

- [ ] `.github/workflows/release.yml` - Add Linux and macOS builds

---

## Updated Release Workflow

Update `.github/workflows/release.yml` to build binaries for all platforms:

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  # Job 1: Build and publish Python packages (unchanged)
  build-packages:
    runs-on: ubuntu-latest
    environment: release
    permissions:
      id-token: write
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

  # Job 2: Build platform-specific executables
  build-executables:
    needs: build-packages
    strategy:
      matrix:
        include:
          - os: windows-latest
            platform: windows
            arch: x64
            ext: .exe
          - os: ubuntu-latest
            platform: linux
            arch: x64
            ext: ""
          - os: macos-13
            platform: darwin
            arch: x64
            ext: ""
          - os: macos-latest
            platform: darwin
            arch: arm64
            ext: ""
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Build executable
        run: |
          pyinstaller --onefile --name ccburn --console src/ccburn/main.py

      - name: Rename executable
        shell: bash
        run: |
          mv dist/ccburn${{ matrix.ext }} dist/ccburn-${{ needs.build-packages.outputs.version }}-${{ matrix.platform }}-${{ matrix.arch }}${{ matrix.ext }}

      - name: Make executable (Unix)
        if: matrix.platform != 'windows'
        run: chmod +x dist/ccburn-*

      - name: Test executable
        shell: bash
        run: |
          ./dist/ccburn-${{ needs.build-packages.outputs.version }}-${{ matrix.platform }}-${{ matrix.arch }}${{ matrix.ext }} --version

      - name: Upload executable artifact
        uses: actions/upload-artifact@v4
        with:
          name: executable-${{ matrix.platform }}-${{ matrix.arch }}
          path: dist/ccburn-*

  # Job 3: Create GitHub Release with all artifacts
  create-release:
    runs-on: ubuntu-latest
    needs: [build-packages, build-executables]
    permissions:
      contents: write
    steps:
      - name: Download all artifacts
        uses: actions/download-artifact@v4
        with:
          path: artifacts

      - name: Flatten artifacts
        run: |
          mkdir -p release-files
          find artifacts -type f \( -name "*.whl" -o -name "*.tar.gz" -o -name "ccburn-*" \) -exec cp {} release-files/ \;
          ls -la release-files/

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          files: release-files/*
          generate_release_notes: true
```

---

## npm Package Structure

Create the npm package in a `npm/` subdirectory:

```
npm/
├── package.json
├── bin/
│   └── ccburn.js
├── scripts/
│   └── postinstall.js
├── README.md
└── .npmignore
```

### package.json

```json
{
  "name": "ccburn",
  "version": "0.1.0",
  "description": "Terminal-based Claude Code usage limit visualizer with real-time burn-up charts",
  "author": "JuanjoFuchs",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/JuanjoFuchs/ccburn.git"
  },
  "homepage": "https://github.com/JuanjoFuchs/ccburn#readme",
  "bugs": {
    "url": "https://github.com/JuanjoFuchs/ccburn/issues"
  },
  "keywords": [
    "claude",
    "anthropic",
    "usage",
    "monitoring",
    "tui",
    "cli",
    "terminal",
    "burn-up",
    "chart"
  ],
  "bin": {
    "ccburn": "./bin/ccburn.js"
  },
  "scripts": {
    "postinstall": "node scripts/postinstall.js"
  },
  "files": [
    "bin/",
    "scripts/",
    "README.md",
    "LICENSE"
  ],
  "engines": {
    "node": ">=16.0.0"
  },
  "os": [
    "darwin",
    "linux",
    "win32"
  ],
  "cpu": [
    "x64",
    "arm64"
  ]
}
```

### bin/ccburn.js

```javascript
#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const binDir = path.join(__dirname);
const platform = process.platform;
const ext = platform === 'win32' ? '.exe' : '';

// Find the binary
const binaryName = fs.readdirSync(binDir).find(f =>
  f.startsWith('ccburn-') && f.endsWith(ext) && !f.endsWith('.js')
);

if (!binaryName) {
  console.error('Error: ccburn binary not found. Try reinstalling: npm install -g ccburn');
  process.exit(1);
}

const binaryPath = path.join(binDir, binaryName);

// Spawn the binary with all arguments
const child = spawn(binaryPath, process.argv.slice(2), {
  stdio: 'inherit',
  windowsHide: true
});

child.on('error', (err) => {
  console.error(`Error executing ccburn: ${err.message}`);
  process.exit(1);
});

child.on('close', (code) => {
  process.exit(code || 0);
});
```

### scripts/postinstall.js

```javascript
const https = require('https');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO = 'JuanjoFuchs/ccburn';
const PACKAGE_VERSION = require('../package.json').version;

const PLATFORM_MAP = {
  'win32-x64': 'windows-x64.exe',
  'linux-x64': 'linux-x64',
  'darwin-x64': 'darwin-x64',
  'darwin-arm64': 'darwin-arm64'
};

async function main() {
  const platform = process.platform;
  const arch = process.arch;
  const key = `${platform}-${arch}`;

  const suffix = PLATFORM_MAP[key];
  if (!suffix) {
    console.error(`Unsupported platform: ${platform}-${arch}`);
    console.error('Supported platforms: win32-x64, linux-x64, darwin-x64, darwin-arm64');
    console.error('');
    console.error('You can still use ccburn via pip: pip install ccburn');
    process.exit(1);
  }

  const binaryName = `ccburn-${PACKAGE_VERSION}-${suffix}`;
  const url = `https://github.com/${REPO}/releases/download/v${PACKAGE_VERSION}/${binaryName}`;
  const binDir = path.join(__dirname, '..', 'bin');
  const binaryPath = path.join(binDir, binaryName);

  // Skip if binary already exists
  if (fs.existsSync(binaryPath)) {
    console.log(`ccburn binary already exists at ${binaryPath}`);
    return;
  }

  console.log(`Downloading ccburn ${PACKAGE_VERSION} for ${platform}-${arch}...`);
  console.log(`URL: ${url}`);

  try {
    await downloadFile(url, binaryPath);

    // Make executable on Unix
    if (platform !== 'win32') {
      fs.chmodSync(binaryPath, 0o755);
    }

    console.log(`Successfully installed ccburn to ${binaryPath}`);
  } catch (err) {
    console.error(`Failed to download ccburn: ${err.message}`);
    console.error('');
    console.error('You can still use ccburn via pip: pip install ccburn');
    process.exit(1);
  }
}

function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);

    const request = (url) => {
      https.get(url, (response) => {
        // Handle redirects (GitHub releases use redirects)
        if (response.statusCode === 301 || response.statusCode === 302) {
          request(response.headers.location);
          return;
        }

        if (response.statusCode !== 200) {
          fs.unlinkSync(dest);
          reject(new Error(`HTTP ${response.statusCode}: ${response.statusMessage}`));
          return;
        }

        const totalBytes = parseInt(response.headers['content-length'], 10);
        let downloadedBytes = 0;

        response.on('data', (chunk) => {
          downloadedBytes += chunk.length;
          if (totalBytes) {
            const percent = Math.round((downloadedBytes / totalBytes) * 100);
            process.stdout.write(`\rDownloading: ${percent}%`);
          }
        });

        response.pipe(file);

        file.on('finish', () => {
          file.close();
          console.log(''); // New line after progress
          resolve();
        });
      }).on('error', (err) => {
        fs.unlinkSync(dest);
        reject(err);
      });
    };

    request(url);
  });
}

main().catch(console.error);
```

### npm/README.md

```markdown
# ccburn

Terminal-based Claude Code usage limit visualizer with real-time burn-up charts.

## Installation

```bash
# Run directly with npx
npx ccburn

# Or install globally
npm install -g ccburn
```

## Usage

```bash
ccburn              # Session limit TUI
ccburn weekly       # Weekly limit
ccburn --compact    # Single line for status bars
ccburn --json       # JSON output for automation
```

## Features

- **Real-time burn-up charts** with budget pace line
- **Pace indicators**: 🧊 behind pace, 🔥 on pace, 🚨 burning too hot
- **Session, Weekly, and Weekly-Sonnet limits**
- **Compact mode** for tmux/status bars
- **JSON output** for scripting

## Requirements

- Claude Code installed with valid credentials

## Alternative Installation

If npm installation fails, you can install via pip:

```bash
pip install ccburn
```

## Links

- [GitHub](https://github.com/JuanjoFuchs/ccburn)
- [PyPI](https://pypi.org/project/ccburn/)

## License

MIT
```

### npm/.npmignore

```
# Source files
*.ts
tsconfig.json

# Development
.github/
tests/
specs/
docs/

# Build artifacts
*.tsbuildinfo

# Environment
.env*

# Logs
*.log
npm-debug.log*

# OS files
.DS_Store
Thumbs.db
```

---

## npm Publish Workflow

Create `.github/workflows/npm-publish.yml`:

```yaml
name: Publish to npm

on:
  release:
    types: [released]
  workflow_dispatch:
    inputs:
      version:
        description: 'Version to publish (must match existing GitHub release)'
        required: true

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          registry-url: 'https://registry.npmjs.org'

      - name: Get version
        id: version
        run: |
          if [ "${{ github.event_name }}" = "release" ]; then
            VERSION="${{ github.event.release.tag_name }}"
            VERSION="${VERSION#v}"
          else
            VERSION="${{ github.event.inputs.version }}"
          fi
          echo "version=$VERSION" >> $GITHUB_OUTPUT

      - name: Verify GitHub release exists with all binaries
        run: |
          VERSION="${{ steps.version.outputs.version }}"
          echo "Checking release v$VERSION..."

          # Get release assets
          ASSETS=$(gh release view "v$VERSION" --json assets -q '.assets[].name')

          # Check all required binaries exist
          for binary in "ccburn-$VERSION-windows-x64.exe" "ccburn-$VERSION-linux-x64" "ccburn-$VERSION-darwin-x64" "ccburn-$VERSION-darwin-arm64"; do
            if ! echo "$ASSETS" | grep -q "$binary"; then
              echo "Error: Missing binary $binary in release v$VERSION"
              exit 1
            fi
          done

          echo "All binaries found in release v$VERSION"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Update npm package version
        working-directory: npm
        run: |
          npm version ${{ steps.version.outputs.version }} --no-git-tag-version

      - name: Publish to npm
        working-directory: npm
        run: npm publish --access public
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}

      - name: Verify npm publication
        run: |
          sleep 10  # Wait for npm registry to update
          npm view ccburn@${{ steps.version.outputs.version }} version
```

---

## Version Synchronization

The npm package version must match the Python package version. The workflow handles this automatically by:

1. Reading the version from the GitHub release tag
2. Updating `npm/package.json` before publishing
3. Verifying all platform binaries exist in the release

**Important:** Don't manually edit the version in `npm/package.json`. The workflow updates it automatically.

---

## Testing

### Local Testing (Before First Publish)

```bash
# Build all platform binaries locally (or download from a test release)
cd npm

# Test postinstall
node scripts/postinstall.js

# Test bin wrapper
node bin/ccburn.js --version

# Test npm pack (creates tarball without publishing)
npm pack

# Test local install
npm install -g ./ccburn-0.1.0.tgz
ccburn --version
```

### CI Testing

The npm-publish workflow verifies:
1. All platform binaries exist in the GitHub release
2. npm publish succeeds
3. Package is accessible via `npm view`

---

## Rollout Strategy

### Phase 1: Update Release Workflow
1. Update `.github/workflows/release.yml` with cross-platform builds
2. Create a test release to verify all binaries are built correctly
3. Verify binaries work on each platform

### Phase 2: Create npm Package
1. Create `npm/` directory with all files
2. Test locally with `npm pack` and local install
3. Verify postinstall downloads correct binary

### Phase 3: Publish to npm
1. Add `NPM_TOKEN` secret to repository
2. Create `.github/workflows/npm-publish.yml`
3. Trigger workflow manually for first publish
4. Verify `npx ccburn` works

### Phase 4: Automate
1. Future releases automatically publish to npm
2. Monitor for platform-specific issues

---

## Troubleshooting

### "Unsupported platform" Error

**Symptom:** postinstall fails with unsupported platform message

**Solution:** Use pip installation instead:
```bash
pip install ccburn
```

Currently supported npm platforms:
- Windows x64
- Linux x64
- macOS x64 (Intel)
- macOS arm64 (Apple Silicon)

### Binary Download Fails

**Symptom:** postinstall fails to download binary

**Possible causes:**
- Network issues
- GitHub release doesn't exist for this version
- Binary not included in release

**Solutions:**
1. Check GitHub releases page for the version
2. Retry installation: `npm install -g ccburn`
3. Use pip as fallback: `pip install ccburn`

### Permission Denied (Unix)

**Symptom:** `permission denied` when running ccburn

**Solution:**
```bash
chmod +x $(npm root -g)/ccburn/bin/ccburn-*
```

### Wrong Binary Downloaded

**Symptom:** Binary crashes or shows wrong architecture error

**Solution:**
1. Remove existing installation: `npm uninstall -g ccburn`
2. Clear npm cache: `npm cache clean --force`
3. Reinstall: `npm install -g ccburn`

---

## Acceptance Criteria

### Pre-publish Verification
- [ ] All platform binaries build successfully in release workflow
- [ ] `npm pack` creates valid tarball
- [ ] Local install works on test machine
- [ ] postinstall downloads correct binary for platform

### Post-publish Verification
- [ ] `npm view ccburn` shows correct version
- [ ] `npx ccburn --version` works on Windows
- [ ] `npx ccburn --version` works on Linux
- [ ] `npx ccburn --version` works on macOS (Intel)
- [ ] `npx ccburn --version` works on macOS (Apple Silicon)
- [ ] `npm install -g ccburn && ccburn --version` works

---

## Future Considerations

### Platform-Specific Packages (Like esbuild)

For better install performance, consider splitting into platform-specific packages:

```
@ccburn/cli           # Main package, depends on platform package
@ccburn/windows-x64   # Windows binary
@ccburn/linux-x64     # Linux binary
@ccburn/darwin-x64    # macOS Intel binary
@ccburn/darwin-arm64  # macOS ARM binary
```

This avoids downloading binaries for other platforms but adds complexity.

### Linux arm64 Support

If there's demand, add Linux arm64 builds:
- Runner: `ubuntu-latest` with QEMU or self-hosted ARM runner
- Binary: `ccburn-{version}-linux-arm64`

### Homebrew Distribution

For macOS users who prefer Homebrew:
```bash
brew install ccburn
```

This would require a Homebrew formula in homebrew-core or a tap.
