"""
Finnish Wikipedia Wordlist Generator
Processes Finnish Wikipedia dump to create a compressed wordlist for sanity checking.

Usage:
    python fiwiki_wordlist_generator.py fiwiki-20251001-pages-meta-current.xml.bz2
"""

import bz2
import gzip
import re
import sys
from xml.etree import ElementTree as ET


def extract_text_from_dump(dump_path):
    """
    Parse Wikipedia XML dump and extract all text content.
    
    Args:
        dump_path: Path to the bz2-compressed Wikipedia dump
        
    Yields:
        Text content from each page
    """
    print(f"Opening dump file: {dump_path}")
    
    # Open bz2-compressed file correctly
    with bz2.open(dump_path, 'rt', encoding='utf-8') as f:
        # Parse XML iteratively to handle large files
        context = ET.iterparse(f, events=('end',))
        
        page_count = 0
        for event, elem in context:
            # Look for text elements (Wikipedia page content)
            # Tag will be like {http://www.mediawiki.org/xml/export-0.10/}text
            if elem.tag.endswith('text'):
                if elem.text:
                    yield elem.text
                    page_count += 1
                    
                    if page_count % 10000 == 0:
                        print(f"Processed {page_count} pages...", file=sys.stderr)
                
                # Clear element to free memory
                elem.clear()
            
            # Also clear parent elements periodically
            if elem.tag.endswith('page'):
                elem.clear()
        
        print(f"Total pages processed: {page_count}", file=sys.stderr)


def process_text_to_words(text_generator):
    """
    Process text content into individual words.
    
    Args:
        text_generator: Generator yielding text strings
        
    Yields:
        Individual words (3+ characters, must contain at least one letter)
    """
    # Compile regex patterns
    non_alnum_pattern = re.compile(r'[^a-zA-ZäöåÄÖÅ0-9]+')
    has_letter_pattern = re.compile(r'[a-zA-ZäöåÄÖÅ]')
    
    for text in text_generator:
        # Replace non-alphanumeric with spaces
        text = non_alnum_pattern.sub(' ', text)
        
        # Split on spaces and filter
        for word in text.split():
            # Must be 3+ chars AND contain at least one letter
            if len(word) >= 3 and has_letter_pattern.search(word):
                yield word.lower()  # Normalize to lowercase


def create_wordlist(dump_path, output_path):
    """
    Create compressed wordlist from Wikipedia dump.
    
    Args:
        dump_path: Path to Wikipedia dump file
        output_path: Path for output gzip file
    """
    print("Step 1-3: Extracting and parsing wikitext...")
    text_gen = extract_text_from_dump(dump_path)
    
    print("Step 4-6: Processing text into words (3+ chars, must contain letters)...")
    words = process_text_to_words(text_gen)
    
    print("Step 7: Collecting unique words...")
    unique_words = set()
    word_count = 0
    
    for word in words:
        unique_words.add(word)
        word_count += 1
        
        if word_count % 100000 == 0:
            print(f"Processed {word_count} words, {len(unique_words)} unique...", file=sys.stderr)
    
    print(f"Total words: {word_count}", file=sys.stderr)
    print(f"Unique words: {len(unique_words)}", file=sys.stderr)
    
    print("Sorting words...")
    sorted_words = sorted(unique_words)
    
    print(f"Step 8: Writing compressed output to {output_path}...")
    with gzip.open(output_path, 'wt', encoding='utf-8') as f:
        f.writelines(f"{word}\n" for word in sorted_words)
            f.write(word + '\n')
    
    print(f"Done! Wordlist saved to {output_path}")
    print(f"Final count: {len(sorted_words)} unique words")


def main():
    if len(sys.argv) != 2:
        print("Usage: python fiwiki_wordlist_generator.py <dump_file.xml.bz2>")
        print("\nExample:")
        print("  python fiwiki_wordlist_generator.py fiwiki-20251001-pages-meta-current.xml.bz2")
        sys.exit(1)
    
    dump_path = sys.argv[1]
    output_path = "fiwiki_wordlist.txt.gz"
    
    try:
        create_wordlist(dump_path, output_path)
    except FileNotFoundError:
        print(f"Error: File not found: {dump_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()