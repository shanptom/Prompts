import os
import re
import requests
import shutil
from PyPDF2 import PdfReader
from tqdm import tqdm
import logging
from bs4 import BeautifulSoup

# Setup logging
LOG_FILE = os.path.join(os.getcwd(), "article_classifier.log")
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define input/output folder variables based on current working directory
RAW_PDF_DIR = os.getcwd()  # Look for PDFs directly in the working directory
RENAMED_PDF_DIR = os.path.join(os.getcwd(), "renamed_pdfs")
os.makedirs(RENAMED_PDF_DIR, exist_ok=True)

# Extract text from first page of PDF (no longer used for DOI extraction)
def extract_first_page_text(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        return reader.pages[0].extract_text()
    except Exception as e:
        logging.error(f"Failed to extract text from {pdf_path}: {e}")
        return ""

# Extract DOI by prioritizing lines with 'doi:'
def extract_doi(text):
    # This function is no longer used as we rely solely on Grobid for DOI extraction
    return None


# Use Grobid to extract metadata
def extract_metadata_with_grobid(pdf_path):
    try:
        url = "http://localhost:8070/api/processHeaderDocument"
        with open(pdf_path, 'rb') as f:
            files = {'input': (pdf_path, f, 'application/pdf')}
            response = requests.post(url, files=files)
        if response.status_code == 200:
            return response.text
        else:
            logging.error(f"GROBID error: {response.status_code} for {pdf_path}")
    except Exception as e:
        logging.error(f"Error calling Grobid for {pdf_path}: {e}")
    return None

# Parse Grobid XML to extract title and DOI
def parse_grobid_metadata(xml_text):
    try:
        soup = BeautifulSoup(xml_text, 'lxml')
        title = soup.find('title').text if soup.find('title') else None
        doi_tag = soup.find('idno', {'type': 'DOI'})
        doi = doi_tag.text if doi_tag else None
        return title, doi
    except Exception as e:
        logging.error(f"Error parsing Grobid response: {e}")
    return None, None

# Removed Crossref API usage as per user request; relying solely on Grobid metadata
def get_metadata_from_doi(doi):
    return None

# Process PDFs and rename
results = []

pdf_files = [f for f in os.listdir(RAW_PDF_DIR) if f.lower().endswith(".pdf")]

for filename in tqdm(pdf_files, desc="Processing PDFs"):
    pdf_path = os.path.join(RAW_PDF_DIR, filename)
    try:
        # Always parse Grobid first
        xml = extract_metadata_with_grobid(pdf_path)
        title_from_grobid, doi_from_grobid = parse_grobid_metadata(xml) if xml else (None, None)

        # Prioritize Grobid metadata for title and year
        title = "Untitled"
        year = "Unknown"
        if xml:
            try:
                # Log a snippet of the raw response for debugging
                logging.debug(f"Raw Grobid response for {filename}: {xml[:500]}...")

                soup = BeautifulSoup(xml, 'lxml')
                # Try different possible tags for title
                title_tag = soup.find('title') or soup.find('tei:title') or soup.find('teiheader:title')
                if title_tag and title_tag.text:
                    title = title_tag.text.strip()
                    logging.info(f"Extracted title from Grobid for {filename}: {title}")
                else:
                    # Fallback to searching raw text for title pattern
                    title_match = re.search(r'title\s*=\s*{([^}]+)}', xml, re.I)
                    if title_match:
                        title = title_match.group(1).strip()
                        logging.info(f"Extracted title from raw Grobid text for {filename}: {title}")
                    else:
                        logging.warning(f"No title found in Grobid metadata for {filename}")

                # Try different possible tags and attributes for date
                date_tag = soup.find('date') or soup.find('tei:date') or soup.find('publicationstmt:date')
                if date_tag:
                    if 'when' in date_tag.attrs and date_tag['when']:
                        date_str = date_tag['when']
                        if date_str:
                            year = date_str.split('-')[0]
                            logging.info(f"Extracted year from Grobid 'when' attribute for {filename}: {year}")
                    elif 'value' in date_tag.attrs and date_tag['value']:
                        date_str = date_tag['value']
                        if date_str:
                            year = date_str.split('-')[0]
                            logging.info(f"Extracted year from Grobid 'value' attribute for {filename}: {year}")
                    elif date_tag.text:
                        match = re.search(r'\b(19\d{2}|20\d{2})\b', date_tag.text)
                        if match:
                            year = match.group(0)
                            logging.info(f"Extracted year from Grobid date text for {filename}: {year}")
                    else:
                        logging.warning(f"No usable date information found in Grobid metadata for {filename}")
                else:
                    # Fallback to searching raw text for year pattern
                    year_match = re.search(r'(?:date|year)\s*=\s*{?(19\d{2}|20\d{2})', xml, re.I)
                    if year_match:
                        year = year_match.group(1)
                        logging.info(f"Extracted year from raw Grobid text for {filename}: {year}")
                    else:
                        logging.warning(f"No date tag or year found in Grobid metadata for {filename}")
            except Exception as e:
                logging.error(f"Error extracting metadata from Grobid for {filename}: {e}")

        # Use only Grobid DOI
        doi = doi_from_grobid

        if title == "Untitled":
            # Fallback to extracting a potential title from the first page text
            try:
                first_page_text = extract_first_page_text(pdf_path)
                title_lines = first_page_text.splitlines()
                title = "Unknown_Title"
                for line in title_lines[:5]:  # Check first few lines for a potential title
                    line = line.strip()
                    if line and len(line) > 10 and len(line) < 100 and line[0].isupper():
                        title = line
                        break
                logging.info(f"Using fallback title from first page for {filename}: {title}")
            except Exception as e:
                logging.error(f"Error extracting fallback title from first page for {filename}: {e}")
                title = "Unknown_Title"
            if year == "Unknown":
                year = "Unknown"

        # If year is still Unknown, try to extract it from title or first page text
        if year == "Unknown":
            if title and title != "Unknown_Title" and title != "Untitled":
                # Look for a 4-digit number that could be a year in the title
                match = re.search(r'\b(19\d{2}|20\d{2})\b', title)
                if match:
                    year = match.group(0)
            if year == "Unknown":
                first_page_text = extract_first_page_text(pdf_path) if 'first_page_text' not in locals() else first_page_text
                for line in first_page_text.splitlines()[:10]:  # Check first few lines for a year
                    match = re.search(r'\b(19\d{2}|20\d{2})\b', line)
                    if match:
                        year = match.group(0)
                        break

        safe_title = re.sub(r'[\\/*?:"<>|]', "", title[:80]).replace(" ", "_")
        new_filename = f"{year}_{safe_title}.pdf"
        dest_path = os.path.join(RENAMED_PDF_DIR, new_filename)

        shutil.copy(pdf_path, dest_path)

        # Remove the original file from raw_pdfs after successful copy
        try:
            os.remove(pdf_path)
            logging.info(f"Removed original file {filename} from raw_pdfs after successful copy.")
        except Exception as e:
            logging.error(f"Failed to remove original file {filename} from raw_pdfs: {e}")

        if title_from_grobid or doi_from_grobid:
            logging.info(f"Processed with Grobid metadata for {filename}")
        else:
            logging.warning(f"Processed with missing or invalid metadata for {filename}")

        results.append({
            "original": filename,
            "new_name": new_filename,
            "doi": doi or "Not found"
        })
        logging.info(f"Processed {filename} -> {new_filename}")

    except Exception as e:
        logging.error(f"Error processing {filename}: {e}")
        continue

# Output result as a DataFrame (optional, if running interactively)
import pandas as pd
results_df = pd.DataFrame(results)
print(results_df.head())
