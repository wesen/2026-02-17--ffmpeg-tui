"""Entry point for ffmpeg-tui."""

from ffmpeg_tui.app import FFmpegTUI


def main():
    app = FFmpegTUI()
    app.run()


if __name__ == "__main__":
    main()
