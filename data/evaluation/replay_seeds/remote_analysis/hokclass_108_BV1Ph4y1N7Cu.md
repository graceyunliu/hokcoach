Starting video analysis...
Submitting video analysis task...
Error: failed to submit analysis task: SubmitVideoAnalysis RPC failed: invalid_argument: unsupported media URL: only video/audio files (3gp, 3gpp, aac, flac, flv, m4a, mov, mp3, mp4, mpeg, mpegs, mpg, mpga, ogg, pcm, wav, webm, wmv) and YouTube URLs are supported
Usage:
  manus-analyze-video <video_url_or_path> <prompt> [flags]

Examples:
  manus-analyze-video "https://www.youtube.com/watch?v=xxx" "summarize the key points"
  manus-analyze-video "/path/to/video.mp4" "describe what happens in this video"

Flags:
  -h, --help      help for manus-analyze-video
  -v, --version   version for manus-analyze-video

