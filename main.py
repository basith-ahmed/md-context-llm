import requests
from bs4 import BeautifulSoup, Comment
import argparse
import logging
from urllib.parse import urljoin, urlparse
import re
from datetime import datetime
import os
import html2text
import unicodedata
import json
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

class MarkdownFormatter:
    def __init__(self, url):
        self.url = url
        self.domain = urlparse(url).netloc
        self.date = datetime.now().strftime("%Y-%m-%d")
        self.metadata = {"url": url, "domain": self.domain, "capture_date": self.date, "word_count": 0, "sections": []}
        
    def create_header(self, title, author=None, date_published=None):
        header = f"---\ntitle: {title}\nurl: {self.url}\ndomain: {self.domain}\ncapture_date: {self.date}\n"
        if author:
            header += f"author: {author}\n"
        if date_published:
            header += f"date_published: {date_published}\n"
        header += "---\n\n"
        return header

    def create_toc(self, content):
        headers = re.findall(r'^(#{2,4})\s+(.+)$', content, re.MULTILINE)
        if not headers:
            return ""
        toc = ["## Contents\n"]
        for hashes, title in headers:
            level = len(hashes) - 2
            indent = "  " * level
            link = re.sub(r'[^\w\s-]', '', title.lower())
            link = re.sub(r'[\s]+', '-', link.strip())
            toc.append(f"{indent}* [{title}](#{link})")
            self.metadata["sections"].append({"level": level + 1, "title": title, "link": link})
        return "\n".join(toc) + "\n\n---\n\n"

    def format_markdown(self, content):
        content = unicodedata.normalize('NFKC', content)
        replacements = [
            (r'^(#+)\s*', r'\1 ', re.MULTILINE),
            (r'\n(#+\s.*?)\n', r'\n\n\1\n\n'),
            (r'^\s*[-*+]\s', '* ', re.MULTILINE),
            (r'^\s{2,}[-*+]\s', '  * ', re.MULTILINE),
            (r'^\s*>\s*', '> ', re.MULTILINE),
            (r'\n([^>\n])', r'\n\n\1'),
            (r'```(\w+)?\n', r'\n```\1\n'),
            (r'\n```\n', r'\n\n```\n\n'),
            (r'\n(\|[^|\n]+\|)\n', r'\n\n\1\n'),
            (r'\n{3,}', '\n\n'),
            (r'\n---\n', r'\n\n---\n\n')
        ]
        for pattern, repl, *flags in replacements:
            content = re.sub(pattern, repl, content, flags=flags[0] if flags else 0)
        return content

    def count_words(self, content):
        text_only = re.sub(r'#|\*|_|\[.*?\]|\(.*?\)|```[\s\S]*?```|`.*?`', '', content)
        return len(re.findall(r'\w+', text_only))

def clean_soup(soup, base_url):
    for tag in ['script', 'style', 'noscript', 'iframe', 'svg', 'canvas', 'advertisement', 'header', 'footer', 'nav', 'aside', 'form']:
        for element in soup.find_all(tag):
            element.decompose()

    for pattern in ['advertisement', 'social', 'comment', 'related', 'sidebar', 'footer', 'header', 'nav', 'menu', 'cookie', 'popup', 'newsletter', 'ad-', 'banner']:
        for element in soup.find_all(class_=re.compile(pattern, re.I)):
            element.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in soup.find_all(['a', 'img']):
        attr = 'href' if tag.name == 'a' else 'src'
        if tag.has_attr(attr):
            tag[attr] = urljoin(base_url, tag[attr])

    for img in soup.find_all('img'):
        img['alt'] = img.get('alt', '').strip() or 'Image'

    for tag in soup.find_all():
        if not tag.get_text(strip=True) and tag.name not in ['img', 'br', 'hr']:
            tag.decompose()

    return soup

def extract_metadata(soup):
    metadata = {}
    author = soup.find('meta', attrs={'name': re.compile(r'author', re.I)})
    if author:
        metadata['author'] = author.get('content')
    
    date = soup.find('meta', attrs={'name': re.compile(r'(published_time|publication_date|date)', re.I)})
    if date:
        metadata['date_published'] = date.get('content')
    
    return metadata

def extract_markdown(html_content, base_url):
    soup = BeautifulSoup(html_content, 'html.parser')
    metadata = extract_metadata(soup)
    soup = clean_soup(soup, base_url)
    
    title = soup.title.string if soup.title else urlparse(base_url).path.split('/')[-1]
    formatter = MarkdownFormatter(base_url)
    
    h = html2text.HTML2Text()
    h.body_width = 0
    h.unicode_snob = True
    h.bypass_tables = False
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_emphasis = False
    h.mark_code = True
    h.escape_snob = True
    h.pad_tables = True
    
    for pre in soup.find_all('pre'):
        if 'class' in pre.attrs:
            lang = pre['class'][0] if pre['class'] else ''
            pre.string = f'\n```{lang}\n{pre.get_text()}\n```\n'

    markdown = h.handle(str(soup))
    formatted_content = formatter.format_markdown(markdown)
    header = formatter.create_header(title, author=metadata.get('author'), date_published=metadata.get('date_published'))
    toc = formatter.create_toc(formatted_content)
    
    final_content = header + toc + formatted_content
    formatter.metadata.update(metadata)
    formatter.metadata['word_count'] = formatter.count_words(formatted_content)
    formatter.metadata['title'] = title
    
    return final_content, formatter.metadata

def save_to_file(content, metadata, file_path):
    directory = os.path.dirname(file_path) if os.path.dirname(file_path) else '.'
    os.makedirs(directory, exist_ok=True)
    
    content = content.encode('utf-8', errors='ignore').decode('utf-8')
    
    with open(file_path, 'w', encoding='utf-8-sig') as file:
        file.write(content)
    
    metadata_path = os.path.splitext(file_path)[0] + '_metadata.json'
    with open(metadata_path, 'w', encoding='utf-8-sig') as file:
        json.dump(metadata, file, indent=2, ensure_ascii=False)

def fetch_webpage_content(url, max_retries=3, timeout=30):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1'
    }
    
    session = requests.Session()
    
    for attempt in range(max_retries):
        try:
            response = session.get(url, headers=headers, timeout=timeout, allow_redirects=True, verify=True)
            response.raise_for_status()
            
            if response.encoding is None:
                response.encoding = response.apparent_encoding
                
            content = response.text
            
            if not content or len(content.strip()) < 50:
                raise ValueError('Retrieved content appears to be empty or too short')
            
            return content
            
        except requests.exceptions.HTTPError as e:
            if response.status_code in [404, 403]:
                raise ValueError(f"Access error {response.status_code}: {url}")
            elif response.status_code == 429 and attempt < max_retries - 1:
                time.sleep(int(response.headers.get('Retry-After', 60)))
                continue
            raise
            
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < max_retries - 1:
                time.sleep((attempt + 1) * 5)
                continue
            raise ValueError(f"Connection failed: {str(e)}")
            
        except Exception as e:
            if attempt < max_retries - 1:
                continue
            raise ValueError(f"Failed to fetch {url}: {str(e)}")
    
    raise ValueError(f"Failed to fetch {url} after {max_retries} attempts")

def main():
    parser = argparse.ArgumentParser(description="Extract webpage content into clean Markdown with metadata.")
    parser.add_argument("url", help="Webpage URL")
    parser.add_argument("-o", metavar="OUTPUT", help="Output file path")
    args = parser.parse_args()

    try:
        html_content = fetch_webpage_content(args.url)
        markdown_content, metadata = extract_markdown(html_content, args.url)
        
        if args.o:
            save_to_file(markdown_content, metadata, args.o)
        else:
            print(markdown_content)
            print("\nMetadata:")
            print(json.dumps(metadata, indent=2))
            
    except Exception as e:
        logging.error(f"Error: {e}")
        raise

if __name__ == "__main__":
    main()
