const https = require('https');
const fs = require('fs');
const path = require('path');

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
