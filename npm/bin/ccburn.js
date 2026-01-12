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
