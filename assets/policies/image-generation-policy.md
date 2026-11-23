---
description: Image generation precedence and restriction on pollinations.ai
mode: always
scope: global
updated: 2026-11-21T01:39:59Z
agent: agy
source: history/antigem-27597ce3/2026-11-21_bbf08e12_github-vector-image-generation-skills.md
---
- Never use https://image.pollinations.ai/prompt/... for generating or showing images.
- When asked to generate or display an image:
  1. First try regular/native image generation.
  2. If that fails or is unavailable, use Claude and the `svg-generator` skill to create an SVG/vector graphic instead.
