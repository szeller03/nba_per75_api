#!/usr/bin/env bash
set -euo pipefail
npm install
npm run build
echo "Production build complete: dist/"
