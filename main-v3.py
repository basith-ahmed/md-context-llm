import requests
from bs4 import BeautifulSoup, Comment
import argparse
import logging
from urllib.parse import urljoin, urlparse
from markdownify import markdownify as md
import re
from datetime import datetime
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

class MarkdownFormatter:
    def __init__(self, url):
        self.url = url
        self.domain = urlparse(url).netloc
        self.date = datetime.now().strftime("%Y-%m-%d")
        
    def create_header(self, title):
        return f"""# {title}

> Original URL: [{self.url}]({self.url})  
> Captured on: {self.date}  
> Source: {self.domain}

---

"""

    @staticmethod
    def format_markdown(content):
        content = re.sub(r'^(#+)\s*', r'\1 ', content, flags=re.MULTILINE)
        
        content = re.sub(r'\n(#+\s.*?)\n', r'\n\n\1\n\n', content)
        
        content = re.sub(r'^\s*[-*+]\s', '* ', content, flags=re.MULTILINE)
        
        content = re.sub(r'\n\n\*\s', '\n* ', content)
        
        content = re.sub(r'^\s*>\s*', '> ', content, flags=re.MULTILINE)
        
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        content = re.sub(r'```(\w+)?\n', r'\n```\1\n', content)
        content = re.sub(r'\n```\n', r'\n\n```\n\n', content)
        
        return content

def fetch_webpage_content(url):
    try:
        logging.info(f"Fetching URL: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch webpage content: {e}")
        raise

def clean_soup(soup, base_url):
    unwanted_tags = [
        "script", "style", "noscript", "iframe", "svg", "canvas", "advertisement"
    ]
    unwanted_classes = [
        "advertisement", "social-share", "comment", "related-posts"
    ]
    unwanted_ids = [
        "comments", "social-media", "advertisement"
    ]

    for tag in soup.find_all(unwanted_tags):
        tag.decompose()

    for class_name in unwanted_classes:
        for element in soup.find_all(class_=re.compile(class_name, re.I)):
            element.decompose()

    for id_name in unwanted_ids:
        for element in soup.find_all(id=re.compile(id_name, re.I)):
            element.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in soup.find_all(["a", "img", "source"]):
        attr = "href" if tag.name == "a" else "src"
        if tag.has_attr(attr):
            tag[attr] = urljoin(base_url, tag[attr])

    for tag in soup.find_all():
        if len(tag.get_text(strip=True)) == 0 and tag.name not in ['img', 'br', 'hr']:
            tag.decompose()

    return soup

def extract_markdown(html_content, base_url):
    soup = BeautifulSoup(html_content, "html.parser")
    soup = clean_soup(soup, base_url)
    
    title = soup.title.string if soup.title else urlparse(base_url).path.split('/')[-1]
    title = title.strip()
    
    for table in soup.find_all("table"):
        markdown_table = md(str(table), heading_style="ATX", bullets="*")
        table.replace_with(markdown_table)
    
    markdown = md(
        str(soup),
        heading_style="ATX",
        bullets="*",
        strip=['script', 'style'],
        wrap=True
    )
    
    formatter = MarkdownFormatter(base_url)
    formatted_content = formatter.create_header(title) + formatter.format_markdown(markdown)
    
    return formatted_content

def save_to_file(content, file_path):
    try:
        os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else '.', exist_ok=True)
        
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(content)
        logging.info(f"Content successfully saved to {file_path}")
    except Exception as e:
        logging.error(f"Failed to save content to file: {e}")
        raise

def main():
    parser = argparse.ArgumentParser(
        description="Extract webpage content into clean, well-formatted Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python script.py https://basithahmed.me
  python script.py https://basithahmed.me -o output.md
        """
    )
    parser.add_argument("url", help="The URL of the webpage to process")
    parser.add_argument("-o", metavar="OUTPUT", type=str, help="Output file path (default: print to stdout)")
    args = parser.parse_args()

    try:
        html_content = fetch_webpage_content(args.url)
        markdown_content = extract_markdown(html_content, args.url)
        
        if args.o:
            save_to_file(markdown_content, args.o)
        else:
            print(markdown_content)
            
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        raise

if __name__ == "__main__":
    main()
