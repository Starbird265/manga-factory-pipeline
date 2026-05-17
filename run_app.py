
import argparse
from manga_pipeline.manga_factory_enhanced import EnhancedMangaFactory

def main():
    parser = argparse.ArgumentParser(description='Manga Factory Enhanced')
    parser.add_argument('url', help='The URL of the manga chapter to process')
    parser.add_argument('--output', default='manga_output', help='The output directory for the processed manga')
    parser.add_argument('--mode', default='manga', choices=['manga', 'webtoon'], help='The processing mode (manga or webtoon)')
    args = parser.parse_args()

    factory = EnhancedMangaFactory(args.output, mode=args.mode)
    factory.download_chapter(args.url)
    factory.cleanup()

if __name__ == '__main__':
    main()
