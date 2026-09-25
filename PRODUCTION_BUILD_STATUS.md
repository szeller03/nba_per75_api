# Website240 Production Bundle Pass

This package contains the current Website240 frontend plus the production Vite configuration for the static-asset optimization pass.

## Optimizations enabled
- Production minification with esbuild
- ES2020 output target
- CSS code splitting
- No inline asset inflation (`assetsInlineLimit: 0`)
- No production source maps
- Vendor chunk separation for React, React Router, and Lucide icons
- Existing Website240 frontend performance layer retained

## Build command
`npm run build`

## Important environment note
The supplied `node_modules` was installed on Windows and contains Windows-native Rollup binaries. The build environment used to prepare this package is Linux, so Vite cannot execute that native Rollup binary here. The source/configuration is ready for the production build on the Windows environment where the supplied dependencies were installed.
