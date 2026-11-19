# 🎬 Autonomous Pinterest Video Engine

Autonomous short-form video extraction, transcoding, and publishing pipeline for Pinterest accounts.

## Architecture
- **Public Runner**: Executes on GitHub Actions with **unlimited free minutes** (zero minutes deducted from account quota).
- **Private Zero-Trust Vault**: All account tokens, credentials, and video queues are stored in `hamouda1/pinterest-video-vault` encrypted at rest with 256-bit AES Fernet.
- **In-Memory Streaming**: Videos are downloaded via `yt-dlp` without watermarks, uploaded directly to Pinterest S3, transcoded, and published as native Video Pins.
- **Zero Temporary Storage**: Temporary MP4 files are purged immediately upon upload completion.
